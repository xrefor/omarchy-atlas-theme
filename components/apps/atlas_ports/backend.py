"""Bounded, read-only local socket inspection without probes or elevated access."""
from __future__ import annotations

import hashlib
import ipaddress
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import threading
import time


MAX_OUTPUT = 1024 * 1024
MAX_LISTENERS = 500
MAX_CGROUP = 16384
MAX_PASSWD = 1024 * 1024
OWNER = re.compile(r'\("((?:[^"\\]|\\.)*)",pid=(\d+),fd=\d+\)')


class Collector:
    """Inspect listeners visible to the current user in the current namespace.

    Owner/service absence means unknown, not that a socket has no owner. Scope
    describes bind addresses only; it cannot establish firewall reachability.
    Cancellation permanently closes this collector.
    """

    def __init__(self, *, ss='ss', timeout=2.0, max_output=MAX_OUTPUT,
                 max_listeners=MAX_LISTENERS, proc_root='/proc', passwd_path='/etc/passwd'):
        self.ss = os.fspath(ss)
        self.timeout = max(.1, min(float(timeout), 10.0))
        self.max_output = max(1024, min(int(max_output), MAX_OUTPUT))
        self.max_listeners = max(1, min(int(max_listeners), MAX_LISTENERS))
        self.proc_root = Path(proc_root)
        self.passwd_path = Path(passwd_path)
        self._cancelled = threading.Event()
        self._process_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._process = None

    @staticmethod
    def _kill(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()

    def cancel(self):
        self._cancelled.set()
        with self._process_lock:
            if self._process is not None:
                self._kill(self._process)

    def _run(self, deadline):
        environment = os.environ.copy()
        environment['LC_ALL'] = 'C'
        with self._process_lock:
            if self._cancelled.is_set():
                return '', ['Collector closed'], False
            process = subprocess.Popen(
                [self.ss, '-H', '-l', '-n', '-t', '-u', '-p', '-e'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=environment, close_fds=True, start_new_session=True)
            self._process = process
        streams = {'out': bytearray(), 'err': bytearray()}
        errors = []
        total = 0
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, 'out')
        selector.register(process.stderr, selectors.EVENT_READ, 'err')
        try:
            while selector.get_map():
                if self._cancelled.is_set():
                    errors.append('Collector closed')
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    errors.append(f'Socket query exceeded {self.timeout:g}s')
                    break
                events = selector.select(min(remaining, .1))
                for key, _ in events:
                    chunk = os.read(key.fd, min(65536, self.max_output + 1 - total))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = self.max_output - total
                    streams[key.data].extend(chunk[:available])
                    total += len(chunk)
                    if total > self.max_output:
                        errors.append(f'Socket output exceeded {self.max_output} bytes')
                        break
                if errors:
                    break
            if not errors:
                try:
                    code = process.wait(timeout=max(.001, deadline - time.monotonic()))
                    if code:
                        errors.append(f'ss exited with status {code}')
                except subprocess.TimeoutExpired:
                    errors.append(f'Socket query exceeded {self.timeout:g}s')
        finally:
            selector.close()
            self._kill(process)
            with self._process_lock:
                self._process = None
            process.stdout.close()
            process.stderr.close()
        output = streams['out'].decode('utf-8', errors='replace')
        # A terminated/truncated final record must never become a fake listener.
        if errors and output and not output.endswith('\n'):
            output = output.rpartition('\n')[0]
        diagnostic = streams['err'].decode('utf-8', errors='replace').strip()
        success = not errors
        if diagnostic:
            errors.append(diagnostic[:300])
        return output, errors, success

    @staticmethod
    def _endpoint(value):
        address, separator, raw_port = value.rpartition(':')
        if not separator or not raw_port.isascii() or not raw_port.isdigit():
            raise ValueError('Invalid endpoint')
        port = int(raw_port)
        if not 0 <= port <= 65535:
            raise ValueError('Invalid port')
        if address.startswith('[') and address.endswith(']'):
            address = address[1:-1]
        host = address.split('%', 1)[0]
        if host == '*':
            scope = 'wildcard'
        else:
            ip = ipaddress.ip_address(host)
            scope = 'loopback' if ip.is_loopback else 'wildcard' if ip.is_unspecified else 'interface'
        return address, port, scope

    def _service(self, pid):
        try:
            with (self.proc_root / str(pid) / 'cgroup').open('rb') as stream:
                data = stream.read(MAX_CGROUP + 1)
            if len(data) > MAX_CGROUP:
                return None
        except OSError:
            return None
        for line in data.decode('utf-8', errors='replace').splitlines():
            fields = line.split(':', 2)
            if len(fields) != 3:
                continue
            # cgroup v2 or the legacy systemd hierarchy, never other controllers.
            if fields[0:2] != ['0', ''] and 'name=systemd' not in fields[1].split(','):
                continue
            units = [part for part in fields[2].split('/') if part.endswith(('.service', '.scope'))]
            if units and units[-1].endswith('.service'):
                return units[-1][:256]
        return None

    def collect(self):
        with self._run_lock:
            return self._collect()

    @staticmethod
    def _uid(metadata):
        """Read ss top-level metadata, ignoring quoted names and nested groups."""
        outside = []
        depth = 0
        quoted = escaped = False
        for character in metadata:
            if escaped:
                escaped = False
                continue
            if quoted and character == '\\':
                escaped = True
                continue
            if character == '"':
                quoted = not quoted
                continue
            if quoted:
                continue
            if character == '(':
                depth += 1
                outside.append(' ')
            elif character == ')':
                if not depth:
                    return None
                depth -= 1
                outside.append(' ')
            elif not depth:
                outside.append(character)
        if quoted or depth:
            return None
        tokens = ''.join(outside).split()
        uid_tokens = [token[4:] for token in tokens if token.startswith('uid:')]
        if uid_tokens:
            if len(uid_tokens) != 1 or not re.fullmatch(r'[0-9]{1,10}', uid_tokens[0]):
                return None
            uid = int(uid_tokens[0])
            return uid if uid < 2 ** 32 - 1 else None
        # ss suppresses uid:0. Plain/non-extended records must remain unknown.
        return 0 if any(re.fullmatch(r'ino:[0-9]{1,20}', token) for token in tokens) else None

    def _accounts(self, deadline):
        """Use only the bounded local passwd file; never trigger NSS lookups."""
        try:
            with self.passwd_path.open('rb') as stream:
                raw = stream.read(MAX_PASSWD + 1)
        except OSError:
            return {}
        if len(raw) > MAX_PASSWD:
            raw = raw[:MAX_PASSWD].rpartition(b'\n')[0]
        accounts = {}
        for line in raw.decode('utf-8', errors='replace').splitlines():
            if self._cancelled.is_set() or time.monotonic() > deadline:
                break
            fields = line.split(':')
            if len(fields) != 7 or not fields[0] or not re.fullmatch(r'[0-9]{1,10}', fields[2]):
                continue
            uid = int(fields[2])
            if uid < 2 ** 32 - 1:
                accounts.setdefault(uid, fields[0][:256])
        return accounts

    def parse_output(self, raw, errors=(), success=True):
        """Parse a captured numeric ss -e snapshot under the normal bounds."""
        with self._run_lock:
            return self._parse_output(raw, errors, success, time.monotonic() + self.timeout)

    def _collect(self):
        value = dict(available=False, listeners=[], errors=[], omitted=0, partial=False)
        deadline = time.monotonic() + self.timeout
        try:
            raw, errors, success = self._run(deadline)
        except OSError as error:
            value['errors'] = [f'Cannot inspect sockets: {error}'[:300]]
            return value
        return self._parse_output(raw, errors, success, deadline)

    def _parse_output(self, raw, errors, success, deadline):
        value = dict(available=False, listeners=[], errors=list(errors)[:8], omitted=0, partial=False)
        # Bound both characters and bytes before splitting untrusted captured output.
        truncated = len(raw) > self.max_output
        encoded = raw[:self.max_output].encode('utf-8', errors='replace')
        if truncated or len(encoded) > self.max_output:
            raw = encoded[:self.max_output].decode('utf-8', errors='ignore').rpartition('\n')[0]
            value['errors'].append(f'Socket output exceeded {self.max_output} bytes')
            success = False
        if self._cancelled.is_set():
            value['errors'].append('Collector closed')
            value['partial'] = True
            return value
        accounts = self._accounts(deadline)
        services = {}
        identities = {}
        malformed = 0
        for line in raw.splitlines():
            if not line.strip():
                continue
            if self._cancelled.is_set() or time.monotonic() > deadline:
                value['errors'].append('Socket collection interrupted or exceeded its time limit')
                break
            fields = line.split(None, 6)
            if len(fields) < 6 or (fields[0], fields[1]) not in (('tcp', 'LISTEN'), ('udp', 'UNCONN')):
                malformed += 1
                continue
            try:
                address, port, scope = self._endpoint(fields[4])
            except ValueError:
                malformed += 1
                continue
            if len(value['listeners']) >= self.max_listeners:
                value['omitted'] += 1
                continue
            owners = []
            metadata = fields[6] if len(fields) > 6 else ''
            uid = self._uid(metadata)
            for name, raw_pid in OWNER.findall(metadata):
                if self._cancelled.is_set() or time.monotonic() > deadline:
                    value['errors'].append('Socket collection interrupted or exceeded its time limit')
                    break
                if len(owners) >= 64:
                    value['errors'].append('Additional socket owners omitted')
                    break
                if len(raw_pid) > 10:
                    continue
                pid = int(raw_pid)
                if pid <= 0 or pid > 2 ** 31 - 1:
                    continue
                if pid not in services:
                    services[pid] = self._service(pid)
                owner = dict(name=name[:256], pid=pid, service=services[pid])
                if owner not in owners:
                    owners.append(owner)
            unit_names = {owner['service'] for owner in owners if owner['service']}
            endpoint = f'[{address}]:{port}' if ':' in address else f'{address}:{port}'
            identity = f'{fields[0]}:{endpoint}:' + ','.join(str(owner['pid']) for owner in owners)
            ordinal = identities.get(identity, 0)
            identities[identity] = ordinal + 1
            value['listeners'].append(dict(
                id=hashlib.sha256(f'{identity}:{ordinal}'.encode()).hexdigest()[:24], protocol=fields[0],
                address=address, port=port, endpoint=endpoint, scope=scope, owners=owners,
                uid=uid, account=accounts.get(uid),
                service=next(iter(unit_names)) if len(unit_names) == 1 else None))
        if malformed:
            value['errors'].append(f'{malformed} unrecognized socket record(s) omitted')
            value['omitted'] += malformed
        value['errors'] = list(dict.fromkeys(value['errors']))[:8]
        value['available'] = (success and not value['errors']) or bool(value['listeners'])
        value['partial'] = bool(value['errors'] or value['omitted'])
        value['listeners'].sort(key=lambda item: (item['port'], item['protocol'], item['address'], item['id']))
        return value
