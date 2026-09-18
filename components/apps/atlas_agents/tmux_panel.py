"""Detached tmux panels owned by one originating Codex pane."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess

from atlas_panel import sidebar_width


def _private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise OSError(f'ATLAS agents runtime directory must be owned and private: {path}')
    return path


def runtime_directory():
    """Return a validated user-private directory, without following its symlink."""
    runtime = os.environ.get('XDG_RUNTIME_DIR', '')
    if runtime and Path(runtime).is_absolute():
        try:
            info = Path(runtime).lstat()
        except OSError:
            pass
        else:
            if (stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o700):
                return _private_directory(Path(runtime) / 'atlas-agents')
    return _private_directory(Path('/tmp') / f'atlas-agents-{os.getuid()}')


class Panels:
    """Manage only panes carrying this exact origin's ATLAS ownership tag.

    ``command`` is the viewer argv prefix. ``open`` appends ``--snapshot PATH``.
    The tmux socket is selected normally by the inherited TMUX environment.
    """

    def __init__(self, origin: str, command: list[str], *, runtime_dir=None):
        if not re.fullmatch(r'%\d+', origin):
            raise ValueError('A tmux origin pane ID is required')
        if not command or any(not isinstance(arg, str) or '\0' in arg for arg in command):
            raise ValueError('A viewer command argv is required')
        self.origin = origin
        self.command = list(command)
        self.runtime_dir = (_private_directory(runtime_dir) if runtime_dir is not None
                            else runtime_directory())
        # The socket path distinguishes identical pane IDs on separate servers.
        socket = os.environ.get('TMUX', '').rsplit(',', 2)[0]
        key = hashlib.sha256((socket + '\0' + origin).encode()).hexdigest()[:24]
        self.lock_name = f'panel-{key}.lock'

    @contextmanager
    def _lock(self):
        directory = os.open(self.runtime_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptor = None
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise OSError('ATLAS agents runtime directory is no longer private')
            descriptor = os.open(self.lock_name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise OSError('ATLAS agents panel lock must be owned and private')
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)

    def _tmux(self, *args):
        return subprocess.check_output(['tmux', *args], text=True,
                                       stderr=subprocess.PIPE, timeout=5).rstrip('\r\n')

    def _owned(self):
        try:
            rows = self._tmux('list-panes', '-a', '-F',
                              '#{pane_id}\t#{@atlas_agents_origin}\t#{@atlas_agents_thread}')
        except subprocess.CalledProcessError:
            return []
        result = []
        for row in rows.splitlines():
            parts = row.split('\t')
            if len(parts) == 3 and parts[1] == self.origin and parts[0] != self.origin:
                result.append((parts[0], parts[2]))
        return result

    def existing(self) -> list[str]:
        return [pane for pane, _ in self._owned()]

    def _kill(self, pane):
        try:
            self._tmux('kill-pane', '-t', pane)
        except subprocess.CalledProcessError:
            # The user can close the same pane between discovery and this call.
            if pane in self.existing():
                raise

    def open(self, thread_id: str, snapshot_path: str) -> str:
        if not thread_id or any(char in thread_id for char in '\0\r\n\t'):
            raise ValueError('A thread ID is required')
        with self._lock():
            owned = self._owned()
            matching = next((pane for pane, thread in owned if thread == thread_id), None)
            if matching:
                for pane, _ in owned:
                    if pane != matching:
                        self._kill(pane)
                return matching
            # Resolve the exact origin before replacing a panel from an older thread.
            actual, session, width = self._tmux(
                'display-message', '-p', '-t', self.origin,
                '#{pane_id}\t#{session_id}\t#{pane_width}').split('\t')
            if actual != self.origin:
                raise ValueError('The originating tmux pane is unavailable')
            for pane, _ in owned:
                self._kill(pane)
            if owned:
                # Removing the old side panel gives its columns back to the origin.
                width = self._tmux('display-message', '-p', '-t', self.origin, '#{pane_width}')
            command = [*self.command, '--snapshot', str(snapshot_path)]
            # Multiple command arguments make tmux exec directly; paths containing
            # shell syntax or #{formats} are passed literally to the viewer.
            panel_columns = sidebar_width(int(width))
            if panel_columns is not None:
                pane = self._tmux('split-window', '-d', '-h', '-l', str(panel_columns), '-t', self.origin,
                                  '-P', '-F', '#{pane_id}', '--', *command)
            else:
                pane = self._tmux('new-window', '-d', '-t', session + ':', '-n', 'agents',
                                  '-P', '-F', '#{pane_id}', '--', *command)
            try:
                self._tmux('set-option', '-p', '-t', pane, '@atlas_agents_origin', self.origin)
                self._tmux('set-option', '-p', '-t', pane, '@atlas_agents_thread', thread_id)
            except (OSError, subprocess.SubprocessError):
                self._kill(pane)
                raise
            return pane

    def close(self) -> bool:
        with self._lock():
            panes = self.existing()
            for pane in panes:
                self._kill(pane)
            return bool(panes)

    def dismiss(self) -> bool:
        return self.close()
