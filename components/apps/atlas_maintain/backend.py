"""Bounded, read-only collection of local maintenance evidence.

The collector never refreshes package databases, invokes sudo, or changes unit
state.  Package updates therefore describe only the already-local pacman sync
database and are deliberately labelled as such by both the data and the UI.
"""
from dataclasses import dataclass
import itertools
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import time


MAX_COMMAND_OUTPUT = 256 * 1024
MAX_LOG_TAIL = 256 * 1024
MAX_ITEMS = 200
LOCAL_UPGRADE_NOTE = 'Local sync database only · no network refresh'


@dataclass(frozen=True)
class CommandResult:
    output: str = ''
    status: str = 'ok'
    returncode: int | None = 0


class CommandRunner:
    """Run a fixed argv with hard time and retained-output bounds."""

    def run(self, argv, *, timeout=3.0, max_output=MAX_COMMAND_OUTPUT):
        if (not isinstance(argv, (list, tuple)) or not argv
                or any(not isinstance(value, str) or '\0' in value for value in argv)):
            raise ValueError('command must be a non-empty string argv')
        timeout = max(0.1, min(float(timeout), 10.0))
        max_output = max(1024, min(int(max_output), MAX_COMMAND_OUTPUT))
        environment = os.environ.copy()
        environment.update({'LC_ALL': 'C', 'LANG': 'C', 'SYSTEMD_COLORS': '0'})
        try:
            process = subprocess.Popen(
                list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, env=environment, start_new_session=True,
                close_fds=True,
            )
        except FileNotFoundError:
            return CommandResult(status='missing', returncode=None)
        except OSError as error:
            return CommandResult(str(error), 'unavailable', None)

        chunks = []
        size = 0
        state = 'ok'
        deadline = time.monotonic() + timeout
        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)

        def stop():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    state = 'timeout'
                    stop()
                    break
                events = selector.select(min(remaining, 0.1))
                if not events:
                    if process.poll() is not None:
                        break
                    continue
                block = os.read(process.stdout.fileno(), min(8192, max_output - size + 1))
                if not block:
                    break
                room = max_output - size
                if room > 0:
                    chunks.append(block[:room])
                    size += min(len(block), room)
                if len(block) > room:
                    state = 'truncated'
                    stop()
                    break
        finally:
            selector.close()
            process.stdout.close()
        try:
            returncode = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            stop()
            returncode = process.wait()
        output = b''.join(chunks).decode('utf-8', errors='replace')
        if state == 'ok' and returncode:
            state = 'error'
        return CommandResult(output, state, returncode)


def _natural_version(value):
    return tuple((0, int(part)) if part.isdigit() else (1, part.lower())
                 for part in re.findall(r'\d+|[^\d]+', value))


def latest_installed_kernel(modules='/usr/lib/modules'):
    """Return the newest real modules directory, ignoring links and odd names."""
    candidates = []
    try:
        entries = list(itertools.islice(Path(modules).iterdir(), 512))
    except OSError:
        return None
    for entry in entries:
        try:
            info = entry.lstat()
        except OSError:
            continue
        name = entry.name
        if (stat.S_ISDIR(info.st_mode) and 0 < len(name) <= 128
                and re.fullmatch(r'[A-Za-z0-9._+~-]+', name)):
            candidates.append(name)
    return max(candidates, key=_natural_version) if candidates else None


def _tail(path, limit=MAX_LOG_TAIL):
    """Read at most ``limit`` final bytes of a regular log without following links."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError:
        return ''
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return ''
        start = max(0, info.st_size - limit)
        raw = os.pread(descriptor, limit, start)
    except OSError:
        return ''
    finally:
        os.close(descriptor)
    if start:
        raw = raw.partition(b'\n')[2]
    return raw.decode('utf-8', errors='replace')


def parse_transaction(text):
    """Parse the most recent ALPM transaction in a bounded pacman log tail."""
    current = None
    last = None
    action = re.compile(r'\[ALPM\] (installed|upgraded|downgraded|removed|reinstalled) ([^\s(]+)')
    for line in text.splitlines()[-4096:]:
        timestamp = line[1:line.find(']')] if line.startswith('[') and ']' in line else ''
        if '[ALPM] transaction started' in line:
            current = {'timestamp': timestamp, 'status': 'in progress', 'changes': []}
            continue
        if current is None:
            continue
        match = action.search(line)
        if match and len(current['changes']) < MAX_ITEMS:
            current['changes'].append({'action': match.group(1), 'package': match.group(2)[:256]})
        if '[ALPM] transaction completed' in line:
            current['status'] = 'completed'
            current['completed_at'] = timestamp
            last, current = current, None
    transaction = current or last
    if transaction is None:
        return None
    transaction['count'] = len(transaction['changes'])
    return transaction


def parse_failed_units(text):
    units = []
    for line in text.splitlines()[:1024]:
        fields = line.lstrip(' \t●').split()
        if fields and re.fullmatch(r'[A-Za-z0-9_.@:+\\-]{1,256}', fields[0]):
            units.append(fields[0])
            if len(units) >= MAX_ITEMS:
                break
    return units


def parse_timers(text):
    timers = []
    timer_name = re.compile(r'(?P<unit>[A-Za-z0-9_.@:+\\-]+\.timer)\s+(?P<activates>\S+)\s*$')
    for line in text.splitlines()[:2048]:
        clean = line.strip()
        match = timer_name.search(clean)
        if not match:
            continue
        schedule = clean[:match.start()].rstrip()
        timers.append({'unit': match.group('unit')[:256],
                       'activates': match.group('activates')[:256],
                       'schedule': schedule[:1024]})
        if len(timers) >= MAX_ITEMS:
            break
    return timers


def parse_upgrades(text):
    upgrades = []
    pattern = re.compile(r'^(\S+)\s+(\S+)\s+->\s+(\S+)\s*$')
    for line in text.splitlines()[:2048]:
        match = pattern.match(line)
        if not match:
            continue
        upgrades.append({'package': match.group(1)[:256], 'current': match.group(2)[:128],
                         'available': match.group(3)[:128]})
        if len(upgrades) >= MAX_ITEMS:
            break
    return upgrades


class Collector:
    def __init__(self, runner=None, *, modules='/usr/lib/modules',
                 pacman_log='/var/log/pacman.log', clock=time.time):
        self.runner = runner or CommandRunner()
        self.modules = modules
        self.pacman_log = pacman_log
        self.clock = clock

    def _command(self, argv, timeout):
        try:
            result = self.runner.run(argv, timeout=timeout, max_output=MAX_COMMAND_OUTPUT)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return CommandResult(str(error), 'unavailable', None)
        if isinstance(result, CommandResult):
            return result
        if isinstance(result, str):
            return CommandResult(result)
        if isinstance(result, subprocess.CompletedProcess):
            output = result.stdout if isinstance(result.stdout, str) else ''
            return CommandResult(output, 'ok' if result.returncode == 0 else 'error', result.returncode)
        raise ValueError('runner returned an unsupported command result')

    def _units(self, scope):
        result = self._command([
            'systemctl', scope, '--no-pager', '--plain', '--no-legend',
            'list-units', '--all', '--state=failed',
        ], 2.5)
        return {'status': result.status,
                'units': parse_failed_units(result.output) if result.status == 'ok' else []}

    def _timers(self, scope):
        result = self._command([
            'systemctl', scope, '--no-pager', '--plain', '--no-legend',
            'list-timers', '--all',
        ], 2.5)
        return {'status': result.status,
                'items': parse_timers(result.output) if result.status == 'ok' else []}

    def collect(self):
        running = platform.release()
        installed = latest_installed_kernel(self.modules)
        system_units = self._units('--system')
        user_units = self._units('--user')
        system_timers = self._timers('--system')
        user_timers = self._timers('--user')
        pending = self._command(['pacman', '-Qu'], 4.0)
        upgrades = parse_upgrades(pending.output) if pending.status == 'ok' else []
        # pacman -Qu exits successfully with no updates.  Any non-zero exit is
        # kept as unavailable rather than being mistaken for a healthy zero.
        pending_status = pending.status
        return {
            'running_kernel': running,
            'installed_kernel': installed,
            'kernel_current': installed == running if installed else None,
            'failed': {'system': system_units, 'user': user_units},
            'timers': {'system': system_timers, 'user': user_timers},
            'transaction': parse_transaction(_tail(self.pacman_log)),
            'upgrades': {'status': pending_status, 'items': upgrades,
                         'count': len(upgrades), 'note': LOCAL_UPGRADE_NOTE},
            'sampled_at': self.clock(),
        }
