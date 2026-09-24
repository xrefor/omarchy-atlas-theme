"""Graphical Polkit authorization for a bounded, fixed local socket reader."""
import os
from pathlib import Path
import selectors
import stat
import subprocess
import threading
import time

from .backend import Collector, MAX_OUTPUT


PKEXEC = '/usr/bin/pkexec'
PYTHON = '/usr/bin/python3'
SS = '/usr/bin/ss'
SS_ARGUMENTS = ('-H', '-l', '-n', '-t', '-u', '-p', '-e')
AUTH_TIMEOUT = 120
REFRESH_TIMEOUT = 4

# This complete root program is a literal, never assembled from user data. It
# imports only isolated system Python stdlib and executes only fixed numeric ss.
ROOT_READER = r'''
import os, selectors, signal, struct, subprocess, sys, time
LIMIT = 1048576
QUERY_TIMEOUT = 3
IDLE_TIMEOUT = 10
LIFETIME = 300
child = None

def expired(signum, frame):
    raise TimeoutError('Reader lifetime expired')

signal.signal(signal.SIGALRM, expired)
signal.alarm(LIFETIME)
end = time.monotonic() + LIFETIME

def snapshot():
    global child
    output, diagnostic = bytearray(), bytearray()
    child = subprocess.Popen(['/usr/bin/ss', '-H', '-l', '-n', '-t', '-u', '-p', '-e'],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, close_fds=True)
    deadline = min(end, time.monotonic() + QUERY_TIMEOUT)
    total = 0
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ, output)
            selector.register(child.stderr, selectors.EVENT_READ, diagnostic)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Socket query timed out')
                for key, _ in selector.select(remaining):
                    block = os.read(key.fd, min(65536, LIMIT + 1 - total))
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(block)
                    if total > LIMIT:
                        raise ValueError('Socket output exceeded size limit')
                    key.data.extend(block)
            code = child.wait(timeout=max(.001, deadline - time.monotonic()))
        if code or diagnostic:
            return 1, b'Socket inspection failed'
        return 0, bytes(output)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        child.stdout.close()
        child.stderr.close()
        child = None

try:
    with selectors.DefaultSelector() as controls:
        controls.register(sys.stdin.buffer, selectors.EVENT_READ)
        while time.monotonic() < end:
            if not controls.select(min(IDLE_TIMEOUT, max(0, end - time.monotonic()))):
                break
            token = os.read(0, 1)
            if token == b'Q' or not token:
                break
            if token != b'S':
                break
            try:
                status, payload = snapshot()
            except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired):
                status, payload = 1, b'Socket inspection failed or exceeded its limit'
            sys.stdout.buffer.write(struct.pack('!BI', status, len(payload)) + payload)
            sys.stdout.buffer.flush()
            if status:
                break
except (BrokenPipeError, OSError, TimeoutError):
    pass
finally:
    if child is not None:
        if child.poll() is None:
            child.kill()
        child.wait()
'''


def _trusted_executable(name):
    """Only root-owned executables below protected, root-owned directories."""
    path = Path(name).resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111:
        raise ValueError('The system inspection command is not executable')
    for item in (path, *path.parents):
        info = item.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('The system inspection command must be root-owned and protected')
    return str(path)


def _stop(process):
    # EOF stops an authorized reader. Before exec, pkexec still has our real
    # uid, so best-effort SIGTERM can dismiss a pending graphical prompt. The
    # root reader may reject that signal; its EOF and lifetime bounds still work.
    if process.stdin is not None:
        try:
            process.stdin.close()
        except OSError:
            pass
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    try:
        process.wait(timeout=.2)
    except subprocess.TimeoutExpired:
        def reap():
            try:
                process.wait(timeout=AUTH_TIMEOUT + 310)
            except subprocess.TimeoutExpired:
                pass
        threading.Thread(target=reap, daemon=True).start()


def _failure(message):
    return dict(available=False, listeners=[], errors=[message], omitted=0,
                partial=False, elevated=False)


class SessionCollector:
    """One graphical authorization retains a fixed reader for at most 5 minutes."""

    def __init__(self, collector=None):
        self.normal = collector if collector is not None else Collector()
        self._lock = threading.Lock()
        self._query_lock = threading.Lock()
        self._generation = 0
        self._enabled = False
        self._closed = False
        self._interrupted = threading.Event()
        self._process = None

    @property
    def enabled(self):
        with self._lock:
            return self._enabled

    def _disable(self, close=False):
        with self._lock:
            self._enabled = False
            self._closed |= close
            self._generation += 1
            self._interrupted.set()
            process, self._process = self._process, None
        if process is not None:
            _stop(process)

    def disable(self):
        self._disable()

    def cancel(self):
        self._disable(close=True)
        self.normal.cancel()

    def authenticate(self):
        self.disable()
        with self._lock:
            if self._closed:
                return _failure('Panel closed.')
            generation = self._generation
            interrupted = self._interrupted = threading.Event()
        with self._query_lock:
            result = self._query(True, generation, interrupted)
        with self._lock:
            if generation != self._generation or self._closed:
                return _failure('Admin request cancelled.')
            self._enabled = bool(result.get('available') and result.get('elevated'))
        return result

    def collect(self):
        with self._lock:
            if self._closed:
                return _failure('Panel closed.')
            enabled, generation = self._enabled, self._generation
            interrupted = self._interrupted
        if not enabled:
            return self.normal.collect()
        with self._query_lock:
            result = self._query(False, generation, interrupted)
        notice = None
        with self._lock:
            if self._closed:
                return _failure('Panel closed.')
            if generation == self._generation and self._enabled:
                if result.get('available') and result.get('elevated'):
                    return result
                self._enabled = False
                self._generation += 1
                self._interrupted.set()
                notice = 'Admin live ended: authorization expired or inspection failed. Press a to retry.'
        result = dict(self.normal.collect(), elevated=False)
        if notice:
            result['notices'] = [*result.get('notices', []), notice]
        return result

    def _current(self, generation, interactive):
        with self._lock:
            return (not self._closed and generation == self._generation
                    and (interactive or self._enabled))

    def _query(self, interactive, generation, interrupted):
        process = None
        retain = False
        try:
            if not self._current(generation, interactive):
                return _failure('Admin request cancelled.')
            if interactive:
                for executable in (PKEXEC, PYTHON, SS):
                    _trusted_executable(executable)
                command = [PKEXEC, '--disable-internal-agent', PYTHON, '-I', '-S', '-u', '-c', ROOT_READER]
                with self._lock:
                    if self._closed or generation != self._generation:
                        return _failure('Admin request cancelled.')
                    process = subprocess.Popen(command, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
                        env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, bufsize=0)
                    self._process = process
            else:
                with self._lock:
                    process = self._process
                if process is None:
                    return _failure('Admin authorization ended.')
            os.write(process.stdin.fileno(), b'S')
            deadline = time.monotonic() + (AUTH_TIMEOUT if interactive else REFRESH_TIMEOUT)
            output = bytearray()
            diagnostic = bytearray()
            expected = None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, 'out')
                selector.register(process.stderr, selectors.EVENT_READ, 'err')
                while True:
                    if interrupted.is_set() or not self._current(generation, interactive):
                        return _failure('Admin request cancelled.')
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return _failure('Admin inspection timed out.')
                    for key, _ in selector.select(min(remaining, .1)):
                        chunk = os.read(key.fd, min(65536, MAX_OUTPUT + 6 - len(output)) if key.data == 'out' else 4096)
                        if not chunk:
                            if key.data == 'err':
                                selector.unregister(key.fileobj)
                                continue
                            try:
                                code = process.wait(timeout=.2)
                            except subprocess.TimeoutExpired:
                                code = None
                            if code == 126:
                                return _failure('Authentication cancelled.')
                            if code == 127:
                                return _failure('Graphical authorization is unavailable or was denied.')
                            return _failure('Admin reader ended or returned an incomplete response.')
                        if key.data == 'err':
                            diagnostic.extend(chunk)
                            if len(diagnostic) > 16384:
                                return _failure('Authorization diagnostics exceeded their size limit.')
                            continue
                        output.extend(chunk)
                        if len(output) > MAX_OUTPUT + 5:
                            return _failure('Admin socket output exceeded its size limit.')
                        if expected is None and len(output) >= 5:
                            if output[0] not in (0, 1):
                                return _failure('Invalid admin reader response.')
                            expected = 5 + int.from_bytes(output[1:5], 'big')
                            if expected > MAX_OUTPUT + 5:
                                return _failure('Admin socket output exceeded its size limit.')
                        if expected is not None and len(output) >= expected:
                            if len(output) != expected or output[0]:
                                return _failure('Admin inspection failed; partial output discarded.')
                            if not self._current(generation, interactive):
                                return _failure('Admin request cancelled.')
                            result = self.normal.parse_output(output[5:].decode('utf-8', errors='replace'))
                            if not result.get('available'):
                                return _failure('Admin inspection returned incomplete socket data.')
                            result.update(elevated=True, captured_at=time.time())
                            retain = True
                            return result
        except KeyboardInterrupt:
            return _failure('Admin inspection cancelled.')
        except (OSError, ValueError):
            return _failure('Unable to run the trusted graphical inspection commands.')
        finally:
            if process is not None and not retain:
                with self._lock:
                    if self._process is process:
                        self._process = None
                _stop(process)
