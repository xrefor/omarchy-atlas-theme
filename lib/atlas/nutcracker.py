#!/usr/bin/env python3
"""Opt-in, user-scoped installation of the ATLAS Nutcracker interface."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import Request, urlopen
import zipfile

if __package__:
    from . import state
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from atlas import state

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = ROOT / 'components/nutcracker'
UPSTREAM_URL = 'https://github.com/drneox/nutcracker.git'
UPSTREAM_COMMIT = 'c0980227fabd910ce4e4597937a5b88be39527f2'

EXPECTED = {
    'androguard': '4.1.4', 'APScheduler': '3.11.3', 'click': '8.5.0',
    'fpdf2': '2.8.8', 'frida-dexdump': '2.0.1', 'frida-tools': '14.10.4',
    'loguru': '0.7.3', 'PyYAML': '6.0.3', 'requests': '2.34.2',
    'rich': '15.0.0', 'textual': '8.2.8', 'nutcracker': '0.2.0',
    'atlas-nutcracker': '0.2.0',
}

JADX = {
    'version': '1.5.6',
    'url': 'https://github.com/skylot/jadx/releases/download/v1.5.6/jadx-1.5.6.zip',
    'sha256': '545ea2be9c242511bc145755cf4bda2485ade42966e096f8b4d3da2a230e8974',
}
JRE = {
    'x86_64': {
        'version': '21.0.12.1+1',
        'url': 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz',
        'sha256': '2413149700df0f7d440500a84a8f764c535f21e5a5e87d38328b64eec2c5b500',
    },
    'aarch64': {
        'version': '21.0.12.1+1',
        'url': 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_aarch64_linux_hotspot_21.0.12.1_1.tar.gz',
        'sha256': '14be1f35ebdbd1f6e8d57eb911a3ffb74d6d9aa255abc5daf2b1302002cf2cf2',
    },
}


class Paths:
    def __init__(self, home=None):
        self.home = Path(home or Path.home()).expanduser().resolve()
        if home is None:
            data_home = Path(os.environ.get('XDG_DATA_HOME', self.home / '.local/share')).expanduser().resolve()
            config_home = Path(os.environ.get('XDG_CONFIG_HOME', self.home / '.config')).expanduser().resolve()
        else:
            data_home, config_home = self.home / '.local/share', self.home / '.config'
        self.base = data_home / 'atlas-nutcracker'
        self.source = self.base / 'source'
        self.venv = self.base / 'venv'
        self.tools = self.base / 'tools'
        # Keep analysis data at the established XDG root for compatibility with
        # the prototype. Generated runtime trees use distinct known children.
        self.data = self.base
        self.marker = self.base / 'install.json'
        self.config = config_home / 'atlas/nutcracker.yaml'
        self.application = data_home / 'applications/atlas-nutcracker.desktop'
        self.bin = self.home / '.local/bin'

    def rel(self, path):
        try: return str(path.resolve().relative_to(self.home))
        except ValueError as exc:
            raise ValueError(f'ATLAS integration path must remain inside the user home: {path}') from exc


def _run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def architecture():
    if platform.system() != 'Linux':
        raise ValueError('Nutcracker packaging currently supports Linux only')
    machine = platform.machine().lower()
    aliases = {'amd64': 'x86_64', 'arm64': 'aarch64'}
    machine = aliases.get(machine, machine)
    if machine not in JRE:
        raise ValueError(f'Unsupported Nutcracker architecture: {machine}')
    return machine


def _clone_source(paths):
    if paths.base.is_symlink() or paths.source.is_symlink():
        raise ValueError('Nutcracker data root and source must not be symlinks')
    paths.base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if paths.source.exists() and not (paths.source / '.git').is_dir():
        raise ValueError(f'Preserving non-git path: {paths.source}')
    if not paths.source.exists():
        paths.source.mkdir(mode=0o700)
        _run(['git', 'init', str(paths.source)], capture_output=True, text=True)
        _run(['git', '-C', str(paths.source), 'remote', 'add', 'origin', UPSTREAM_URL])
    changes = _run(['git', '-C', str(paths.source), 'status', '--porcelain'],
                   capture_output=True, text=True).stdout.splitlines()
    # Older ATLAS builds invoked setuptools in the checkout. Accept only the
    # narrowly verified artifacts that invocation created; reject all others.
    dirty = [] if _known_source_build_artifacts(paths.source, changes) else changes
    if dirty:
        raise ValueError(f'Preserving modified Nutcracker source: {paths.source}')
    remote = _run(['git', '-C', str(paths.source), 'remote', 'get-url', 'origin'],
                  capture_output=True, text=True).stdout.strip()
    if remote != UPSTREAM_URL:
        raise ValueError(f'Unexpected Nutcracker origin: {remote}')
    _run(['git', '-C', str(paths.source), 'fetch', '--depth=1', 'origin', UPSTREAM_COMMIT])
    _run(['git', '-C', str(paths.source), 'checkout', '--detach', UPSTREAM_COMMIT])
    actual = _run(['git', '-C', str(paths.source), 'rev-parse', 'HEAD'],
                  capture_output=True, text=True).stdout.strip()
    if actual != UPSTREAM_COMMIT:
        raise ValueError(f'Nutcracker source verification failed: {actual}')


def _install_python(paths):
    if sys.version_info < (3, 11): raise ValueError('Nutcracker requires Python 3.11 or newer')
    if paths.venv.is_symlink(): raise ValueError(f'Nutcracker virtual environment must not be a symlink: {paths.venv}')
    if not (paths.venv / 'bin/python').is_file():
        _run([sys.executable, '-m', 'venv', str(paths.venv)])
    python = paths.venv / 'bin/python'
    pip = [str(python), '-m', 'pip', '--disable-pip-version-check']
    _run(pip + ['install', '--require-virtualenv', '-r', str(PAYLOAD / 'requirements.txt')])
    with tempfile.TemporaryDirectory(prefix='.python-build-', dir=paths.base) as temporary:
        temporary = Path(temporary)
        archive = temporary / 'source.tar'
        source_export = temporary / 'source'
        _run(['git', '-C', str(paths.source), 'archive', '--format=tar',
              f'--prefix={source_export.name}/', '--output', str(archive), UPSTREAM_COMMIT])
        with tarfile.open(archive, 'r:') as bundle:
            for item in bundle.getmembers():
                if not _safe_name(item.name) or item.issym() or item.islnk() or item.isdev():
                    raise ValueError(f'Unsafe pinned source archive member: {item.name}')
            bundle.extractall(temporary, filter='data')
        frontend_export = temporary / 'frontend'
        shutil.copytree(PAYLOAD, frontend_export, ignore=shutil.ignore_patterns(
            'build', '*.egg-info', '__pycache__', '.pytest_cache', 'tests'))
        _run(pip + ['install', '--require-virtualenv', '--no-deps',
                    str(source_export), str(frontend_export)])
    mismatch = _version_mismatches(python)
    if mismatch: raise ValueError(f'Installed package version verification failed: {mismatch}')


def _known_source_build_artifacts(source, changes):
    allowed = {'?? build/', '?? nutcracker.egg-info/'}
    if not changes or set(changes) - allowed: return not changes
    egg = source / 'nutcracker.egg-info'
    expected_egg = {'PKG-INFO', 'SOURCES.txt', 'dependency_links.txt',
                    'entry_points.txt', 'requires.txt', 'top_level.txt'}
    if '?? nutcracker.egg-info/' in changes:
        if egg.is_symlink() or not egg.is_dir(): return False
        files = {str(path.relative_to(egg)) for path in egg.rglob('*') if path.is_file()}
        if files != expected_egg or any(path.is_symlink() for path in egg.rglob('*')): return False
    if '?? build/' in changes:
        built = source / 'build/lib/nutcracker_core'
        original = source / 'nutcracker_core'
        if built.is_symlink() or not built.is_dir(): return False
        built_files = {str(path.relative_to(built)) for path in built.rglob('*') if path.is_file()}
        original_files = {str(path.relative_to(original)) for path in original.rglob('*')
                          if path.is_file() and '__pycache__' not in path.parts}
        # setuptools copies Python/package-data inputs, not every tracked README,
        # web asset, or toolbox file. Every output must still map byte-for-byte
        # to the pinned checkout, and the output must not be empty.
        if not built_files or built_files - original_files: return False
        for rel in built_files:
            if (built / rel).is_symlink() or (built / rel).read_bytes() != (original / rel).read_bytes():
                return False
    return True


def _version_mismatches(python):
    script = ('import json,sys;from importlib.metadata import version;'
              'print(json.dumps({name:version(name) for name in sys.argv[1:]}))')
    try:
        result = _run([str(python), '-c', script, *EXPECTED], capture_output=True, text=True)
        installed = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {name: (version, None) for name, version in EXPECTED.items()}
    return {name: (EXPECTED[name], installed.get(name)) for name in EXPECTED
            if installed.get(name) != EXPECTED[name]}


def _download(asset, destination):
    request = Request(asset['url'], headers={'User-Agent': 'ATLAS-Nutcracker/0.2'})
    digest = hashlib.sha256()
    with urlopen(request, timeout=60) as response, destination.open('xb') as output:
        while block := response.read(1024 * 1024):
            digest.update(block); output.write(block)
    if digest.hexdigest() != asset['sha256']:
        destination.unlink(missing_ok=True)
        raise ValueError(f'Checksum verification failed for {asset["url"]}')


def _safe_name(name):
    path = PurePosixPath(name)
    return bool(path.parts) and not path.is_absolute() and '..' not in path.parts


def _extract_zip(archive, destination):
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            if not _safe_name(item.filename) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f'Unsafe JADX archive member: {item.filename}')
        bundle.extractall(destination)


def _extract_tar(archive, destination):
    with tarfile.open(archive, 'r:gz') as bundle:
        for item in bundle.getmembers():
            if not _safe_name(item.name) or item.isdev():
                raise ValueError(f'Unsafe JRE archive member: {item.name}')
        try:
            # Python's data filter permits contained relative links used by the JRE,
            # while rejecting links and paths that escape the extraction directory.
            bundle.extractall(destination, filter='data')
        except tarfile.TarError as exc:
            raise ValueError(f'Unsafe JRE archive: {exc}') from exc


def _restore_jadx_modes(jadx_root):
    """zipfile does not restore Unix execute bits; set only known launchers."""
    for name in ('jadx', 'jadx-gui'):
        launcher = jadx_root / 'bin' / name
        if launcher.is_symlink() or not launcher.is_file():
            raise ValueError(f'JADX archive is missing a regular launcher: {launcher}')
        launcher.chmod(0o755)


def _install_tools(paths, machine):
    if paths.tools.is_symlink(): raise ValueError(f'Nutcracker tools path must not be a symlink: {paths.tools}')
    paths.tools.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.install-', dir=paths.base) as temporary:
        temporary = Path(temporary)
        jadx_archive = temporary / 'jadx.zip'; jre_archive = temporary / 'jre.tar.gz'
        _download(JADX, jadx_archive); _download(JRE[machine], jre_archive)
        jadx_extract = temporary / 'jadx-extract'; jre_extract = temporary / 'jre-extract'
        jadx_extract.mkdir(); jre_extract.mkdir()
        _extract_zip(jadx_archive, jadx_extract); _extract_tar(jre_archive, jre_extract)
        # The official 1.5.6 archive places bin/ and lib/ at its root. Accept
        # the historical single jadx/ wrapper as well, but no other shape.
        jadx_root = jadx_extract / 'jadx' if (jadx_extract / 'jadx').is_dir() else jadx_extract
        _restore_jadx_modes(jadx_root)
        jre_roots = [path for path in jre_extract.iterdir() if path.is_dir()]
        if not (jadx_root / 'bin/jadx').is_file() or len(jre_roots) != 1 or not (jre_roots[0] / 'bin/java').is_file():
            raise ValueError('Downloaded tool archive has an unexpected layout')
        for name, source in [('jadx', jadx_root), ('jre', jre_roots[0])]:
            destination = paths.tools / name
            if destination.exists():
                if not _marker_valid(paths):
                    raise ValueError(f'Preserving unrecognized existing tool directory: {destination}')
                shutil.rmtree(destination)
            shutil.move(str(source), destination)


def _integrate(paths, restoring=False, dry=False):
    desired = {}
    wrapper = ('#!/bin/sh\n'
               f'export NUTCRACKER_HOME={shlex.quote(str(paths.source))}\n'
               f'export ATLAS_NUTCRACKER_DATA={shlex.quote(str(paths.data))}\n'
               f'export ATLAS_NUTCRACKER_CONFIG={shlex.quote(str(paths.config))}\n'
               f'export ATLAS_NUTCRACKER_TOOLS={shlex.quote(str(paths.tools))}\n'
               f'exec {shlex.quote(str(paths.venv / "bin/python"))} -m atlas_nutcracker "$@"\n')
    desktop = ('[Desktop Entry]\nType=Application\nName=ATLAS Nutcracker\n'
               'Comment=Android APK analysis and reports\n'
               'Exec=omarchy launch tui --app-id=org.atlas.nutcracker nutcracker\n'
               'Terminal=false\nCategories=Development;Security;\n')
    for name in ('nutcracker', 'atlas-nutcracker'):
        rel = paths.rel(paths.bin / name)
        if restoring:
            record = state.load(paths.home)['files'].get(rel)
            if record: desired[rel] = record['before']
        else: desired[rel] = state.value(wrapper, 0o755)
    desktop_rel = paths.rel(paths.application)
    if restoring:
        record = state.load(paths.home)['files'].get(desktop_rel)
        if record: desired[desktop_rel] = record['before']
    else: desired[desktop_rel] = state.value(desktop)
    return state.transact(paths.home, desired, components=('nutcracker',), dry=dry)


def setup(root=ROOT, home=None, with_tools=False, dry=False):
    global ROOT, PAYLOAD
    ROOT = Path(root).resolve(); PAYLOAD = ROOT / 'components/nutcracker'
    paths = Paths(home); machine = architecture()
    if not PAYLOAD.joinpath('pyproject.toml').is_file():
        raise ValueError(f'Nutcracker payload is missing from {ROOT}')
    if dry:
        print(f'Would install Nutcracker {UPSTREAM_COMMIT} under {paths.base}')
        if with_tools: print(f'Would install checksummed JRE/JADX tools for {machine}')
        return _integrate(paths, dry=True)
    _clone_source(paths); _install_python(paths)
    if with_tools: _install_tools(paths, machine)
    paths.base.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths.marker.write_text(json.dumps({
        'version': 1, 'upstream': UPSTREAM_COMMIT, 'architecture': machine,
        'jre': JRE[machine]['version'] if with_tools else None,
        'jadx': JADX['version'] if with_tools else None,
    }, indent=2) + '\n')
    paths.marker.chmod(0o600)
    with state.lock(paths.home): _integrate(paths)
    print('ATLAS Nutcracker installed. Run: nutcracker doctor')


def doctor(home=None):
    paths = Paths(home); okay = True
    try: machine = architecture(); print(f'platform: supported ({machine})')
    except ValueError as exc: print(f'platform: {exc}'); okay = False
    if (paths.source / '.git').is_dir():
        result = subprocess.run(['git', '-C', str(paths.source), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        commit = result.stdout.strip() if result.returncode == 0 else ''
        print('source:', 'verified' if commit == UPSTREAM_COMMIT else f'unexpected commit {commit or "unreadable"}')
        okay &= commit == UPSTREAM_COMMIT
    else: print('source: not installed'); okay = False
    python = paths.venv / 'bin/python'
    print('python:', python if python.is_file() else 'not installed'); okay &= python.is_file()
    if python.is_file():
        mismatch = _version_mismatches(python)
        print('packages:', 'verified' if not mismatch else f'version mismatch {mismatch}')
        okay &= not mismatch
    for name, path in [('java', paths.tools / 'jre/bin/java'), ('jadx', paths.tools / 'jadx/bin/jadx')]:
        found = path if path.is_file() else shutil.which(name)
        print(f'{name}:', found or 'optional tool not installed')
    print('config:', paths.config)
    print('data:', paths.data)
    return 0 if okay else 1


def _remove_generated(paths):
    if not paths.marker.is_file():
        raise ValueError(f'Nutcracker install marker is missing: {paths.marker}')
    marker = json.loads(paths.marker.read_text())
    if marker.get('version') != 1 or marker.get('upstream') != UPSTREAM_COMMIT:
        raise ValueError('Nutcracker install marker is not recognized; preserving runtime files')
    base = paths.base.resolve()
    for path in (paths.source, paths.venv, paths.tools):
        if path.parent.resolve() != base or path.name not in ('source', 'venv', 'tools'):
            raise ValueError(f'Refusing unsafe removal target: {path}')
        if path.is_symlink(): path.unlink()
        elif path.exists(): shutil.rmtree(path)
    paths.marker.unlink()


def _marker_valid(paths):
    try: marker = json.loads(paths.marker.read_text())
    except (OSError, json.JSONDecodeError): return False
    return marker.get('version') == 1 and marker.get('upstream') == UPSTREAM_COMMIT


def restore(home=None, dry=False):
    paths = Paths(home)
    with state.lock(paths.home):
        changes = _integrate(paths, restoring=True, dry=dry)
        if not dry: _remove_generated(paths)
    print(f'Nutcracker integration restored; reports and config remain under {paths.base} and {paths.config}')
    return changes


def parse(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'doctor', 'restore'))
    parser.add_argument('--home', type=Path)
    parser.add_argument('--with-tools', action='store_true', help='Download checksummed JRE and JADX releases')
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    if args.action == 'doctor': return doctor(args.home)
    if args.action == 'restore': return restore(args.home, args.dry_run)
    return setup(home=args.home, with_tools=args.with_tools, dry=args.dry_run)


if __name__ == '__main__':
    try: raise SystemExit(main() or 0)
    except (ValueError, OSError, subprocess.SubprocessError, ImportError, json.JSONDecodeError) as error:
        print(f'ATLAS Nutcracker: {error}', file=sys.stderr); raise SystemExit(1)
