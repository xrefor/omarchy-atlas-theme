"""Bounded, read-only collection from Linux kernel interfaces."""
from pathlib import Path
import os
import platform
import socket
import time


MAX_READ = 1024 * 1024


def _read(path, limit=MAX_READ):
    try:
        with Path(path).open('r', encoding='utf-8', errors='replace') as source:
            return source.read(limit)
    except OSError:
        return ''


def _number(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _cpu(text):
    line = next((line for line in text.splitlines() if line.startswith('cpu ')), '')
    values = [_number(value) for value in line.split()[1:]]
    if len(values) < 4:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def _memory(text):
    values = {}
    for line in text.splitlines():
        name, separator, value = line.partition(':')
        if separator:
            values[name] = _number(value.split()[0] if value.split() else 0) * 1024
    total = values.get('MemTotal', 0)
    available = values.get('MemAvailable', values.get('MemFree', 0))
    used = max(0, total - available)
    return {'total': total, 'used': used,
            'percent': used * 100 / total if total else None}


def _network(text):
    received = sent = 0
    for line in text.splitlines()[2:]:
        name, separator, values = line.partition(':')
        fields = values.split()
        if not separator or name.strip() == 'lo' or len(fields) < 9:
            continue
        received += _number(fields[0])
        sent += _number(fields[8])
    return received, sent


def _duration(seconds):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    return (f'{days}d {hours}h' if days else f'{hours}h {minutes}m' if hours else f'{minutes}m')


class Collector:
    def __init__(self, proc='/proc', sys='/sys', filesystem='/', clock=time.monotonic):
        self.proc = Path(proc)
        self.sys = Path(sys)
        self.filesystem = filesystem
        self.clock = clock
        self.previous_cpu = None
        self.previous_network = None
        self.previous_processes = {}
        self.previous_process_at = None

    def _filesystem(self):
        try:
            value = os.statvfs(self.filesystem)
        except OSError:
            return {'total': 0, 'used': 0, 'percent': None}
        total = value.f_blocks * value.f_frsize
        free = value.f_bfree * value.f_frsize
        available = value.f_bavail * value.f_frsize
        used = max(0, total - free)
        visible = used + available
        return {'total': total, 'used': used,
                'percent': used * 100 / visible if visible else None}

    def _thermals(self):
        readings = []
        for path in sorted((self.sys / 'class/thermal').glob('thermal_zone*/temp'))[:64]:
            raw = _read(path, 64).strip()
            try:
                value = float(raw)
            except ValueError:
                continue
            if abs(value) > 1000:
                value /= 1000
            if -50 <= value <= 250:
                readings.append(value)
        return max(readings) if readings else None

    def _battery(self):
        for directory in sorted((self.sys / 'class/power_supply').glob('*'))[:32]:
            if _read(directory / 'type', 64).strip().lower() != 'battery':
                continue
            capacity = _read(directory / 'capacity', 64).strip()
            status = _read(directory / 'status', 64).strip()
            try:
                percent = max(0, min(100, int(capacity)))
            except ValueError:
                percent = None
            return {'percent': percent, 'status': status or 'Unknown'}
        return None

    def _processes(self, uptime, now):
        ticks = os.sysconf('SC_CLK_TCK')
        page = os.sysconf('SC_PAGE_SIZE')
        rows = []
        current = {}
        elapsed = now - self.previous_process_at if self.previous_process_at is not None else None
        for directory in list(self.proc.glob('[0-9]*'))[:32768]:
            text = _read(directory / 'stat', 8192).strip()
            left, right = text.find('('), text.rfind(')')
            if left < 1 or right <= left:
                continue
            pid = _number(text[:left].strip(), -1)
            fields = text[right + 1:].split()
            if pid < 0 or len(fields) < 22:
                continue
            cpu_ticks = _number(fields[11]) + _number(fields[12])
            cpu_seconds = cpu_ticks / max(1, ticks)
            rss = max(0, _number(fields[21])) * page
            # Kernel comm omits arguments, which may contain credentials or
            # other private values that do not belong in a status panel.
            command = text[left + 1:right]
            current[pid] = cpu_ticks
            previous = self.previous_processes.get(pid)
            cpu_percent = (max(0, cpu_ticks - previous) * 100 / ticks / elapsed
                           if previous is not None and elapsed and elapsed > 0 else None)
            rows.append({'pid': pid, 'command': command[:512], 'rss': rss,
                         'cpu_seconds': cpu_seconds, 'cpu_percent': cpu_percent,
                         'age': max(0, uptime - _number(fields[19]) / max(1, ticks))})
        self.previous_processes = current
        self.previous_process_at = now
        rows.sort(key=lambda item: (-(item['cpu_percent'] or 0), -item['rss'], item['pid']))
        return rows[:100]

    def collect(self):
        now = self.clock()
        errors = []
        cpu_value = _cpu(_read(self.proc / 'stat'))
        cpu_percent = None
        if cpu_value and self.previous_cpu:
            total = cpu_value[0] - self.previous_cpu[0]
            idle = cpu_value[1] - self.previous_cpu[1]
            if total > 0:
                cpu_percent = max(0.0, min(100.0, (total - idle) * 100 / total))
        self.previous_cpu = cpu_value
        if cpu_value is None:
            errors.append('CPU counters unavailable')

        network_value = _network(_read(self.proc / 'net/dev'))
        receive_rate = send_rate = None
        if self.previous_network:
            elapsed = now - self.previous_network[0]
            if elapsed > 0:
                receive_rate = max(0, network_value[0] - self.previous_network[1]) / elapsed
                send_rate = max(0, network_value[1] - self.previous_network[2]) / elapsed
        self.previous_network = (now, *network_value)

        uptime_text = _read(self.proc / 'uptime', 128).split()
        try:
            uptime = max(0.0, float(uptime_text[0]))
        except (IndexError, ValueError):
            uptime = 0.0
            errors.append('Uptime unavailable')
        load_text = _read(self.proc / 'loadavg', 128).split()
        load = []
        for value in load_text[:3]:
            try:
                load.append(float(value))
            except ValueError:
                break
        if len(load) != 3:
            load = None

        return {
            'hostname': socket.gethostname(), 'kernel': platform.release(),
            'uptime': uptime, 'uptime_text': _duration(uptime), 'load': load,
            'cpu_percent': cpu_percent, 'memory': _memory(_read(self.proc / 'meminfo')),
            'filesystem': self._filesystem(), 'temperature': self._thermals(),
            'battery': self._battery(),
            'network': {'received': network_value[0], 'sent': network_value[1],
                        'receive_rate': receive_rate, 'send_rate': send_rate},
            'processes': self._processes(uptime, now), 'errors': errors,
            'sampled_at': time.time(),
        }
