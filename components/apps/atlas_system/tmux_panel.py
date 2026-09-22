"""Detached tmux panel owned by one originating workspace pane."""
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
        raise OSError(f'ATLAS System runtime directory must be owned and private: {path}')
    return path


def runtime_directory():
    runtime = os.environ.get('XDG_RUNTIME_DIR', '')
    if runtime and Path(runtime).is_absolute():
        try:
            info = Path(runtime).lstat()
        except OSError:
            pass
        else:
            if (stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o700):
                return _private_directory(Path(runtime) / 'atlas-system')
    return _private_directory(Path('/tmp') / f'atlas-system-{os.getuid()}')


class Panel:
    def __init__(self, origin, command, *, runtime_dir=None):
        if not re.fullmatch(r'%\d+', origin):
            raise ValueError('A tmux origin pane ID is required')
        if not command or any(not isinstance(arg, str) or '\0' in arg for arg in command):
            raise ValueError('A panel command argv is required')
        self.origin = origin
        self.command = list(command)
        self.runtime_dir = (_private_directory(runtime_dir) if runtime_dir is not None
                            else runtime_directory())
        socket_name = os.environ.get('TMUX', '').rsplit(',', 2)[0]
        key = hashlib.sha256((socket_name + '\0' + origin).encode()).hexdigest()[:24]
        self.lock_name = f'panel-{key}.lock'

    @contextmanager
    def _lock(self):
        directory = os.open(self.runtime_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptor = None
        try:
            info = os.fstat(directory)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise OSError('ATLAS System runtime directory is no longer private')
            descriptor = os.open(self.lock_name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise OSError('ATLAS System panel lock must be owned and private')
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)

    def _tmux(self, *args):
        return subprocess.check_output(['tmux', *args], text=True,
                                       stderr=subprocess.PIPE, timeout=5).rstrip('\r\n')

    def existing(self):
        try:
            rows = self._tmux('list-panes', '-a', '-F', '#{pane_id}\t#{@atlas_system_origin}')
        except subprocess.CalledProcessError:
            return []
        return [parts[0] for row in rows.splitlines()
                if len(parts := row.split('\t')) == 2
                and parts[1] == self.origin and parts[0] != self.origin]

    def _kill(self, pane):
        try:
            self._tmux('kill-pane', '-t', pane)
        except subprocess.CalledProcessError:
            if pane in self.existing():
                raise

    def close(self):
        with self._lock():
            panes = self.existing()
            for pane in panes:
                self._kill(pane)
            return bool(panes)

    def open(self):
        with self._lock():
            panes = self.existing()
            if panes:
                for pane in panes[1:]:
                    self._kill(pane)
                return panes[0]
            actual, session, width = self._tmux(
                'display-message', '-p', '-t', self.origin,
                '#{pane_id}\t#{session_id}\t#{pane_width}').split('\t')
            if actual != self.origin:
                raise ValueError('The originating tmux pane is unavailable')
            columns = sidebar_width(int(width))
            if columns is None:
                pane = self._tmux('new-window', '-d', '-t', session + ':', '-n', 'system',
                                  '-P', '-F', '#{pane_id}', '--', *self.command)
            else:
                pane = self._tmux('split-window', '-d', '-h', '-l', str(columns), '-t', self.origin,
                                  '-P', '-F', '#{pane_id}', '--', *self.command)
            try:
                self._tmux('set-option', '-p', '-t', pane, '@atlas_system_origin', self.origin)
            except (OSError, subprocess.SubprocessError):
                self._kill(pane)
                raise
            return pane

    def toggle(self):
        return 'closed' if self.close() else ('opened' if self.open() else 'opened')
