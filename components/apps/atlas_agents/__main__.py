"""Launch, observe and display a single Codex conversation in tmux."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

from .backend import Observer, codex_home, process_root, process_start
from .tmux_panel import Panels, runtime_directory


class NoCodexProcess(ValueError):
    """The originating pane has no local Codex process to observe."""


def panel_message(origin, message):
    tmux('display-message', '-t', origin, 'ATLAS agents: ' + message)
    return 0


def launcher():
    return str(Path(__file__).resolve().parents[1] / 'bin/atlas-agents')


def command(*args):
    return [sys.executable, launcher(), *args]


def tmux(*args):
    return subprocess.check_output(['tmux', *args], text=True, stderr=subprocess.PIPE, timeout=3).rstrip('\r\n')


def origin_pane(value=None):
    pane = value or os.environ.get('TMUX_PANE', '')
    if not os.environ.get('TMUX'):
        raise ValueError('Open the agent panel from a tmux session')
    # A toggle invoked from the panel itself still addresses its originating CLI.
    actual, owner = tmux('display-message', '-p', '-t', pane,
                         '#{pane_id}\t#{@atlas_agents_origin}').split('\t', 1)
    return owner or actual


def cache_path(origin):
    socket = os.environ.get('TMUX', '').rsplit(',', 2)[0]
    key = hashlib.sha256((socket + '\0' + origin).encode()).hexdigest()[:24]
    return runtime_directory() / (key + '.json')


def read_cache(path):
    path = Path(path)
    if path.parent.resolve() != runtime_directory().resolve():
        raise ValueError('Agent snapshots must be in the private runtime directory')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > 1024 * 1024):
            raise ValueError('Agent snapshot is not a private regular file')
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError('Invalid agent snapshot')
    return value


def write_cache(path, value):
    path = Path(path)
    directory = runtime_directory()
    if path.parent != directory:
        raise ValueError('Agent snapshots must be in the private runtime directory')
    fd, temporary = tempfile.mkstemp(prefix='.agents-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output, ensure_ascii=True)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(temporary)


def dismiss(path, snapshot):
    write_cache(Path(path).with_suffix('.dismissed'), {'session_key': snapshot.get('session_key')})


def is_dismissed(path, key):
    try: return read_cache(Path(path).with_suffix('.dismissed')).get('session_key') == key
    except (OSError, ValueError): return False


def codex_process(origin):
    """Find Codex below this pane's shell using process parentage, not cwd."""
    root = int(tmux('display-message', '-p', '-t', origin, '#{pane_pid}'))
    processes = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal(): continue
        try:
            fields = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
            processes[int(path.name)] = (int(fields[1]), Path(os.readlink(path / 'exe')).name)
        except (OSError, ValueError, IndexError): continue
    found = []
    for pid, (_, name) in processes.items():
        if name != 'codex': continue
        current, seen = pid, set()
        while current not in seen:
            if current == root:
                found.append(pid); break
            seen.add(current)
            current = processes.get(current, (0, ''))[0]
            if not current: break
    if not found:
        raise NoCodexProcess('Open Codex in this pane before showing its agents')
    if len(found) != 1:
        raise ValueError('Multiple Codex processes are running in this pane')
    return found[0]


def spawn_watcher(pid, origin, thread=None):
    start = process_start(pid)
    if start is None: raise ValueError('The Codex process has ended')
    args = command('watch', '--pid', str(pid), '--start', start, '--pane', origin)
    if thread:
        args += ['--thread', thread]
        # An observer may already hold the watch lock for this process. Publish
        # explicit selection to it as well; stale launches cannot inherit it.
        write_cache(cache_path(origin).with_suffix('.thread'),
                    {'session_key': f'{pid}:{start}', 'thread': thread})
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)


def interactive_launch(args):
    # Command-line options pass through byte-for-byte. Utility/automation commands
    # and remote clients do not start a local session observer.
    utility = {'agents', 'exec', 'e', 'review', 'login', 'logout', 'mcp', 'plugin', 'app-server',
               'remote-control', 'completion', 'update', 'doctor', 'sandbox', 'debug', 'apply',
               'queue', 'archive', 'delete', 'migrate-rollouts', 'unarchive', 'cloud',
               'exec-server', 'features', 'help'}
    if any(x in ('--help', '-h', '--version', '-V', '--remote') or x.startswith('--remote=') for x in args):
        return False
    takes_value = {'-c', '--config', '-m', '--model', '-p', '--profile', '-s', '--sandbox',
                   '-C', '--cd', '--add-dir', '--enable', '--disable', '-a', '--ask-for-approval',
                   '-i', '--image', '--local-provider'}
    skip = False
    for arg in args:
        if skip: skip = False; continue
        if arg in takes_value: skip = True; continue
        if arg.startswith('-'): continue
        return arg not in utility
    return True


def launch(args):
    if args and args[0] == '--': args = args[1:]
    if not args: raise ValueError('launch requires the Codex executable')
    binary = args[0]
    if '/' not in binary:
        binary = shutil.which(binary)
        if binary is None:
            raise ValueError('Executable not found on PATH: ' + args[0])
    binary = str(Path(binary).resolve())
    watcher = None
    if (os.isatty(0) and os.isatty(1) and os.environ.get('TMUX')
            and os.environ.get('ATLAS_AGENTS_AUTO', '1') != '0' and interactive_launch(args[1:])):
        try: watcher = spawn_watcher(os.getpid(), origin_pane())
        except (OSError, ValueError, subprocess.SubprocessError): pass
    try:
        os.execv(binary, [binary, *args[1:]])
    finally:
        if watcher: watcher.terminate()


def watch(args):
    origin = origin_pane(args.pane)
    path = cache_path(origin)
    lock_fd = os.open(path.with_suffix('.watch.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    manager = None
    try:
        info = os.fstat(lock_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            raise ValueError('Unsafe agent watcher lock')
        key = f'{args.pid}:{args.start}'
        deadline = time.monotonic() + 4
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                # A duplicate observer for this launch can leave immediately;
                # a new CLI must let the previous launch finish its last poll.
                owner = os.pread(lock_fd, 128, 0).decode(errors='replace')
                if owner == key: return 0
                if time.monotonic() >= deadline:
                    raise ValueError('The previous Codex observer is still stopping; toggle again shortly')
                time.sleep(.1)
        os.ftruncate(lock_fd, 0)
        os.write(lock_fd, key.encode())
        manager = Panels(origin, command('view'))
        observer = None
        opened = False
        stopped = False
        started = time.time()
        def stop(*_):
            nonlocal stopped
            stopped = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        snapshot = {'root_id': args.thread or '', 'connected': False, 'error': 'Waiting for the Codex conversation',
                    'agents': [], 'updated_at': 0, 'session_key': key}
        while not stopped and process_start(args.pid) == args.start:
            try:
                try:
                    if tmux('display-message', '-p', '-t', origin, '#{pane_id}') != origin: break
                except subprocess.CalledProcessError:
                    # A removed origin/server ends panel ownership even if the
                    # CLI survives the terminal's hangup signal.
                    break
                # /new and /resume can change conversations without replacing
                # the CLI process. Explicit thread selections remain pinned.
                selected = args.thread
                try:
                    selection = read_cache(path.with_suffix('.thread'))
                    if (selection.get('session_key') == key
                            and isinstance(selection.get('thread'), str) and selection['thread']):
                        selected = selection['thread']
                except (OSError, ValueError):
                    pass
                root = selected or process_root(args.pid, codex_home())
                changed = bool(root and observer and observer.root_id != root)
                if root and (observer is None or changed):
                    observer = Observer(root)
                if root and observer:
                    snapshot = dict(observer.poll(), session_key=key, cli_pid=args.pid, cli_start=args.start)
                else:
                    # Keep the last observations across a transient closed file,
                    # but never present the previous conversation as live.
                    snapshot = dict(snapshot, connected=False,
                                    error='Waiting for the current Codex conversation')
                write_cache(path, snapshot)
                existing = manager.existing()
                if changed and existing:
                    manager.open(snapshot['root_id'], str(path))
                if existing: opened = True
                elif opened:
                    # Pane killed manually (rather than Q) also suppresses reopen.
                    dismiss(path, snapshot)
                has_activity = any(a['status'] in ('starting', 'running', 'waiting')
                                   or a.get('created_at', 0) >= started for a in snapshot['agents'])
                if (snapshot['connected'] and has_activity and not opened
                        and not is_dismissed(path, key)):
                    manager.open(snapshot['root_id'], str(path)); opened = True
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                snapshot = dict(snapshot, connected=False, error=str(error)[:240])
                with contextlib.suppress(OSError, ValueError): write_cache(path, snapshot)
            time.sleep(1)
        if observer:
            snapshot = dict(observer.poll(), session_key=key)
        snapshot = dict(snapshot, connected=False, error='Codex session ended; showing last observations')
        for row in snapshot['agents']:
            if row['status'] in ('starting', 'running', 'waiting'):
                row.update(status='unknown', activity='Session ended before a completion event')
        write_cache(path, snapshot)
        return 0
    finally:
        # Only the observer holding this origin's watch lock owns cleanup. Close
        # before releasing it so a quick relaunch cannot lose its new panel.
        # Cleanup also runs if the final observation or snapshot write fails.
        if manager is not None:
            with contextlib.suppress(OSError, ValueError, subprocess.SubprocessError):
                manager.close()
        os.close(lock_fd)


def attach(args):
    origin = origin_pane(args.pane)
    pid = codex_process(origin)
    root = args.thread or process_root(pid, codex_home())
    if not root:
        spawn_watcher(pid, origin, args.thread)
        panel_message(origin, 'Waiting for Codex to open its conversation; try again shortly')
        return None
    observer = Observer(root)
    snapshot = observer.poll()
    snapshot.update(session_key=f'{pid}:{process_start(pid)}', cli_pid=pid, cli_start=process_start(pid))
    write_cache(cache_path(origin), snapshot)
    spawn_watcher(pid, origin, args.thread)
    return root


def toggle(args):
    origin = origin_pane(args.pane)
    manager = Panels(origin, command('view'))
    path = cache_path(origin)
    if manager.existing():
        with contextlib.suppress(FileNotFoundError): dismiss(path, read_cache(path))
        manager.close(); return 0
    try:
        pid = codex_process(origin)
    except NoCodexProcess:
        try:
            snapshot = read_cache(path)  # A completed session's summary remains accessible.
        except FileNotFoundError:
            snapshot = {}
        if not snapshot.get('root_id'):
            return panel_message(origin, 'Open Codex in this pane before showing its agents')
    else:
        try: snapshot = read_cache(path)
        except FileNotFoundError: snapshot = {}
        if snapshot.get('session_key') != f'{pid}:{process_start(pid)}':
            if attach(args) is None:
                return 0
            snapshot = read_cache(path)
        else:
            spawn_watcher(pid, origin, args.thread)
        if not snapshot.get('root_id'):
            return panel_message(origin, 'Waiting for Codex to open its conversation; try again shortly')
    with contextlib.suppress(FileNotFoundError): path.with_suffix('.dismissed').unlink()
    manager.open(snapshot['root_id'], str(path))
    return 0


def view(path):
    from .ui import run
    current = read_cache(path)
    def snapshot():
        nonlocal current
        try: current = read_cache(path)
        except (OSError, ValueError): current = dict(current, connected=False, error='Agent observer is unavailable')
        if current.get('connected') and time.time() - current.get('updated_at', 0) > 10:
            return dict(current, connected=False, error='No recent observer update; last observations may be stale')
        return current
    try: run(snapshot)
    finally: dismiss(path, current)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action')
    for name in ('toggle', 'attach'):
        child = sub.add_parser(name)
        child.add_argument('--pane'); child.add_argument('--thread')
    child = sub.add_parser('launch'); child.add_argument('args', nargs=argparse.REMAINDER)
    child = sub.add_parser('watch')
    child.add_argument('--pane', required=True); child.add_argument('--pid', required=True, type=int)
    child.add_argument('--start', required=True); child.add_argument('--thread')
    child = sub.add_parser('view'); child.add_argument('--snapshot', required=True, type=Path)
    child = sub.add_parser('snapshot'); child.add_argument('--thread', default=os.environ.get('CODEX_THREAD_ID'))
    args = parser.parse_args(argv)
    try:
        if args.action is None:
            return toggle(argparse.Namespace(pane=None, thread=None))
        if args.action == 'launch': return launch(args.args)
        if args.action == 'watch': return watch(args)
        if args.action == 'view': return view(args.snapshot)
        if args.action == 'attach': attach(args); return 0
        if args.action == 'toggle': return toggle(args)
        if args.action == 'snapshot':
            if not args.thread: raise ValueError('snapshot requires --thread ID')
            observer = Observer(args.thread)
            for _ in range(32):
                data = observer.poll()
                if not any(x['activity'] == 'Loading session activity' for x in data['agents']): break
            print(json.dumps(data, indent=2)); return 0 if data['connected'] else 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('ATLAS agents: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
