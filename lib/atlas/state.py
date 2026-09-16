"""Journaled file transactions for user configuration, with original restoration."""
import base64
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

STATE = '.local/state/atlas-bundle'


def target(home, rel):
    home = Path(home).resolve()
    rel = Path(rel)
    if rel.is_absolute() or not rel.parts or '..' in rel.parts:
        raise ValueError(f'Unsafe relative path: {rel}')
    path = home / rel
    if not path.parent.resolve().is_relative_to(home):
        raise ValueError(f'Path escapes destination through a symlink: {rel}')
    return path


def snapshot(path):
    if path.is_symlink():
        return {'kind': 'link', 'target': os.readlink(path)}
    if path.exists():
        if not path.is_file():
            raise ValueError(f'Expected a file: {path}')
        return {'kind': 'file', 'data': base64.b64encode(path.read_bytes()).decode(),
                'mode': stat.S_IMODE(path.stat().st_mode)}
    return {'kind': 'absent'}


def value(data, mode=0o644):
    if isinstance(data, str):
        data = data.encode()
    return {'kind': 'file', 'data': base64.b64encode(data).decode(), 'mode': mode}


def text_value(item):
    return base64.b64decode(item['data']).decode()


def unlink(path):
    if not path.exists() and not path.is_symlink(): return
    path.unlink()
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write(path, item):
    path.parent.mkdir(parents=True, exist_ok=True)
    if item['kind'] == 'absent':
        unlink(path)
        return
    fd, tmpname = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    tmp = Path(tmpname)
    try:
        if item['kind'] == 'link':
            os.close(fd)
            tmp.unlink()
            tmp.symlink_to(item['target'])
        else:
            with os.fdopen(fd, 'wb') as out:
                out.write(base64.b64decode(item['data']))
                out.flush()
                os.fsync(out.fileno())
            tmp.chmod(item['mode'])
        os.replace(tmp, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        tmp.unlink(missing_ok=True)


def metadata(home, name):
    p = target(home, STATE + '/' + name)
    root = target(home, STATE)
    # Backup state must never be redirected into a public or external directory.
    if root.is_symlink() or p.is_symlink():
        raise ValueError('ATLAS state directory and metadata must not be symlinks')
    return p


def load(home):
    path = metadata(home, 'manifest.json')
    result = json.loads(path.read_text()) if path.exists() else {'version': 1, 'files': {}, 'components': [], 'directories': []}
    if result.get('version') != 1 or not isinstance(result.get('files'), dict):
        raise ValueError('Unsupported ATLAS installation manifest')
    legacy_without_directories = 'directories' not in result
    result.setdefault('directories', [])
    if not isinstance(result['directories'], list):
        raise ValueError('Unsupported ATLAS installation directory manifest')
    managed_parents = set()
    for rel in result['files']:
        if not isinstance(rel, str):
            raise ValueError('Unsafe ATLAS managed file manifest')
        target(home, rel)
        parent = Path(rel).parent
        while parent != Path('.'):
            managed_parents.add(str(parent))
            parent = parent.parent
    if legacy_without_directories:
        owned_roots = ('.config/atlas', '.local/share/atlas', '.local/lib/atlas-cli',
                       '.config/omarchy/themes/atlas', '.config/omarchy/plugins/atlas.')
        result['directories'] = sorted(
            rel for rel in managed_parents
            if any(rel == root or rel.startswith(root + '/') for root in owned_roots[:-1])
            or rel.startswith(owned_roots[-1])
        )
    for rel in result['directories']:
        if not isinstance(rel, str) or rel not in managed_parents or target(home, rel) == Path(home).resolve():
            raise ValueError('Unsafe ATLAS installation directory manifest')
    return result


def _missing_directories(home, paths):
    home = Path(home).resolve()
    result = set()
    for rel in paths:
        parent = target(home, rel).parent
        while parent != home:
            if not parent.exists() and not parent.is_symlink():
                result.add(str(parent.relative_to(home)))
            parent = parent.parent
    return result


def prune_directories(home, directories):
    removed = 0
    for rel in sorted(set(directories), key=lambda item: len(Path(item).parts), reverse=True):
        path = target(home, rel)
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            path.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


def prune_bytecode(home):
    removed = 0
    for rel in ('.local/share/atlas', '.local/lib/atlas-cli'):
        root = target(home, rel)
        if root.is_symlink() or not root.is_dir():
            continue
        caches = sorted(root.rglob('__pycache__'), key=lambda item: len(item.parts), reverse=True)
        for cache in caches:
            if cache.is_symlink() or not cache.is_dir():
                continue
            for item in cache.iterdir():
                if item.is_file() and not item.is_symlink() and item.suffix == '.pyc':
                    unlink(item)
                    removed += 1
            try:
                cache.rmdir()
            except OSError:
                pass
    return removed


@contextmanager
def lock(home):
    path = metadata(home, 'lock')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def recover(home, dry=False):
    journal = metadata(home, 'pending.json')
    if not journal.exists():
        print('No interrupted ATLAS transaction.')
        return
    pending = json.loads(journal.read_text())
    for rel, item in pending['changes'].items():
        current = snapshot(target(home, rel))
        if current not in (item['before'], item['after']):
            raise ValueError(f'Recovery preserves a later edit: {rel}')
    print(f"Recover {len(pending['changes'])} files from interrupted transaction")
    if dry:
        return
    for rel, item in reversed(list(pending['changes'].items())):
        write(target(home, rel), item['before'])
    write(metadata(home, 'manifest.json'), pending['manifest_before'])
    unlink(journal)


def transact(home, desired, components=(), dry=False, restoring=False):
    journal = metadata(home, 'pending.json')
    if journal.exists():
        raise ValueError('Interrupted installation found. Run atlas-theme recover first.')
    manifest_path = metadata(home, 'manifest.json')
    manifest_before = snapshot(manifest_path)
    manifest = load(home)
    if not restoring:
        manifest['directories'] = sorted(
            set(manifest.get('directories', [])) | _missing_directories(home, desired)
        )
    changes = {}
    for rel, item in desired.items():
        current = snapshot(target(home, rel))
        record = manifest['files'].get(rel)
        if record and current != record['installed']:
            raise ValueError(f'Preserving a later edit: {rel}. Restore your managed version or save and reconcile the edit first.')
        if current != item:
            changes[rel] = {'before': current, 'after': item}
        if not restoring:
            if record is None:
                manifest['files'][rel] = {'before': current, 'installed': item}
            else:
                record['installed'] = item
    for rel, item in changes.items():
        print(('REMOVE ' if item['after']['kind'] == 'absent' else 'WRITE  ') + rel)
    if dry:
        print(f'{len(changes)} file changes planned')
        return len(changes)
    manifest['components'] = sorted(set(manifest.get('components', [])) | set(components))
    pending = {'changes': changes, 'manifest_before': manifest_before}
    write(journal, value(json.dumps(pending), 0o600))
    attempted = []
    try:
        for rel, item in changes.items():
            path = target(home, rel)
            if snapshot(path) != item['before']:
                raise ValueError(f'File changed during installation: {rel}')
            attempted.append(rel)
            write(path, item['after'])
        if restoring:
            write(manifest_path, {'kind': 'absent'})
        else:
            write(manifest_path, value(json.dumps(manifest, indent=2) + '\n', 0o600))
    except BaseException:
        for rel in reversed(attempted):
            item = changes[rel]
            path = target(home, rel)
            if snapshot(path) not in (item['before'], item['after']):
                raise ValueError(f'Rollback preserved a concurrent edit: {rel}; journal retained for recovery')
            write(path, item['before'])
        write(manifest_path, manifest_before)
        unlink(journal)
        raise
    unlink(journal)
    if restoring:
        bytecode = prune_bytecode(home)
        removed = prune_directories(home, manifest.get('directories', []))
        print(f'{bytecode} generated Python bytecode files removed')
        print(f'{removed} empty ATLAS-created directories removed')
    print(f'{len(changes)} file changes applied')
    return len(changes)
