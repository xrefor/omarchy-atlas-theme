"""Relay an interactive Codex PTY without modifying the executable or its input."""
import contextlib
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import sys
import termios
import time
import tomllib
import tty

from atlas_agents.__main__ import interactive_launch
from .colors import Colors


def active_colors(arguments):
    if (not all(os.isatty(fd) for fd in (0, 1, 2)) or 'NO_COLOR' in os.environ
            or os.environ.get('ATLAS_CODEX_COLORS') == '0' or not interactive_launch(arguments)):
        return None
    source = Path.home() / '.local/state/omarchy/current/theme/colors.toml'
    try:
        palette = tomllib.loads(source.read_text())
        if palette.get('accent', '').lower() != '#ff5a12':
            return None
        return Colors(palette)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def relay(command, colors):
    original = termios.tcgetattr(0)
    size = fcntl.ioctl(0, termios.TIOCGWINSZ, b'\0' * 8)
    flags = {fd: fcntl.fcntl(fd, fcntl.F_GETFL) for fd in (0, 1)}
    pid, master = pty.fork()
    if pid == 0:
        try:
            fcntl.ioctl(0, termios.TIOCSWINSZ, size)
            os.execvp(command[0], command)
        except OSError as error:
            os.write(2, f'atlas-codex: {error}\n'.encode())
            os._exit(127 if error.errno == errno.ENOENT else 126)
    status = None
    deadline = None
    handlers = {}

    def forward(signum, _=None):
        nonlocal deadline
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signum)
        if signum in (signal.SIGTERM, signal.SIGHUP):
            deadline = time.monotonic() + 2

    def resize(*_):
        with contextlib.suppress(OSError):
            fcntl.ioctl(master, termios.TIOCSWINSZ,
                        fcntl.ioctl(0, termios.TIOCGWINSZ, b'\0' * 8))

    def terminal_mode(active):
        if active:
            tty.setraw(0, termios.TCSANOW)
            for fd in (0, 1, master):
                os.set_blocking(fd, False)
        else:
            for fd, value in flags.items():
                fcntl.fcntl(fd, fcntl.F_SETFL, value)
            termios.tcsetattr(0, termios.TCSANOW, original)

    def suspend(*_):
        forward(signal.SIGSTOP)
        terminal_mode(False)
        os.kill(os.getpid(), signal.SIGSTOP)
        # Execution continues here after the outer shell resumes this job.
        terminal_mode(True)
        resize()
        forward(signal.SIGCONT)

    incoming, outgoing = bytearray(), bytearray()
    stdin_open = master_open = True
    drain_deadline = None
    orphan_deadline = None
    try:
        for sig, handler in ((signal.SIGWINCH, resize), (signal.SIGTERM, forward),
                             (signal.SIGHUP, forward), (signal.SIGINT, forward),
                             (signal.SIGTSTP, suspend)):
            handlers[sig] = signal.signal(sig, handler)
        terminal_mode(True)
        while True:
            if status is None:
                waited, result = os.waitpid(pid, os.WNOHANG | os.WUNTRACED)
                if waited and os.WIFSTOPPED(result):
                    suspend()
                    continue
                if waited:
                    status = result
                    drain_deadline = time.monotonic() + 1
                    orphan_deadline = time.monotonic() + 2
            now = time.monotonic()
            if orphan_deadline is not None and now >= orphan_deadline:
                # A descendant continuously writing after Codex exits must not
                # keep this relay alive. Stop its process group, then drain all
                # queued output normally rather than dropping buffered bytes.
                forward(signal.SIGKILL)
                orphan_deadline = None
            if deadline is not None and status is None and now >= deadline:
                forward(signal.SIGKILL)
                deadline = None
            if (master_open and drain_deadline is not None and now >= drain_deadline
                    and not outgoing and not select.select([master], [], [], 0)[0]):
                # Only an idle, fully drained PTY may time out. Never discard
                # buffered output merely because its consumer is slow.
                # Descendants must not keep a completed CLI's PTY open forever.
                master_open = False
                outgoing.extend(colors.finish())
                incoming.clear()
            if not master_open and not outgoing and status is not None:
                break
            readers = []
            if master_open and len(outgoing) < 1024 * 1024:
                readers.append(master)
            if stdin_open and master_open and status is None and len(incoming) < 1024 * 1024:
                readers.append(0)
            writers = ([master] if master_open and incoming else []) + ([1] if outgoing else [])
            readable, writable, _ = select.select(readers, writers, [], 0.05)
            for fd in readable:
                try:
                    data = os.read(fd, 65536)
                except BlockingIOError:
                    continue
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    data = b''
                if fd == master:
                    if data:
                        outgoing.extend(colors.feed(data))
                        if status is not None:
                            drain_deadline = time.monotonic() + 1
                    else:
                        master_open = False
                        incoming.clear()
                        outgoing.extend(colors.finish())
                        if status is None:
                            forward(signal.SIGHUP)
                elif data:
                    incoming.extend(data)
                else:
                    stdin_open = False
                    forward(signal.SIGHUP)
            for fd in writable:
                if fd == master and not master_open:
                    continue
                buffer = incoming if fd == master else outgoing
                try:
                    count = os.write(fd, buffer)
                    del buffer[:count]
                except BlockingIOError:
                    pass
                except OSError as error:
                    if fd == master and error.errno == errno.EIO:
                        incoming.clear()
                    else:
                        raise
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        for fd, value in flags.items():
            with contextlib.suppress(OSError):
                fcntl.fcntl(fd, fcntl.F_SETFL, value)
        with contextlib.suppress(OSError):
            termios.tcsetattr(0, termios.TCSANOW, original)
        os.close(master)
        if status is None:
            # Closing a controlling PTY normally sends HUP. Bound cleanup even
            # when an application traps it or an output consumer disappears.
            forward(signal.SIGHUP)
            end = time.monotonic() + 2
            while status is None and time.monotonic() < end:
                waited, result = os.waitpid(pid, os.WNOHANG)
                if waited:
                    status = result
                else:
                    time.sleep(0.01)
            if status is None:
                forward(signal.SIGKILL)
                _, status = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(status)
    return code if code >= 0 else 128 - code


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ['--help'] or args == ['-h']:
        print('usage: atlas-codex [--observe] -- COMMAND [ARGS...]')
        return 0
    observe = bool(args and args[0] == '--observe')
    if observe:
        args.pop(0)
    if not args or args.pop(0) != '--' or not args:
        print('usage: atlas-codex [--observe] -- COMMAND [ARGS...]', file=sys.stderr)
        return 2
    colors = active_colors(args[1:])
    command = args
    if observe:
        observer = Path(__file__).resolve().parents[1] / 'bin/atlas-agents'
        command = [sys.executable, str(observer), 'launch', '--', *args]
    try:
        if colors is None:
            os.execvp(command[0], command)
        return relay(command, colors)
    except OSError as error:
        print(f'atlas-codex: {error}', file=sys.stderr)
        return 127 if error.errno == errno.ENOENT else 126


if __name__ == '__main__':
    raise SystemExit(main())
