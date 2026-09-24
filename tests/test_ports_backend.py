"""Read-only socket collection and its resource bounds."""
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from components.apps.atlas_ports.backend import Collector, MAX_CGROUP, MAX_PASSWD


FIXTURE = '''udp UNCONN 0 0 127.0.0.53%lo:53 0.0.0.0:* users:(("systemd-resolve",pid=101,fd=12))
tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=200,fd=3),("systemd",pid=1,fd=45))
tcp LISTEN 0 511 [::1]:3000 [::]:* users:(("node",pid=300,fd=19))
tcp LISTEN 0 4096 [::]:443 [::]:*
udp UNCONN 0 0 [fe80::1%eth0]:5353 [::]:*
tcp LISTEN 0 128 *:8080 *:*
'''


class PortsBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas ports ')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def script(self, body):
        executable = self.root / 'fake-ss'
        executable.write_text('#!/usr/bin/env python3\n' + body)
        executable.chmod(0o700)
        return executable

    def collect(self, text=FIXTURE, **kwargs):
        with patch.object(Collector, '_run', return_value=(text, [], True)):
            return Collector(proc_root=self.root, **kwargs).collect()

    def cgroup(self, pid, content):
        directory = self.root / str(pid)
        directory.mkdir(exist_ok=True)
        (directory / 'cgroup').write_text(content)

    def test_real_ss_records_ipv4_ipv6_udp_and_multiple_owners(self):
        self.cgroup(101, '0::/system.slice/systemd-resolved.service\n')
        self.cgroup(200, '0::/system.slice/sshd.service\n')
        self.cgroup(300, f'0::/user.slice/user-1000.slice/user@{1000}.service/app.slice/dev.service\n')
        result = self.collect()
        self.assertTrue(result['available'])
        self.assertFalse(result['partial'])
        rows = {row['port']: row for row in result['listeners']}
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[22]['owners'][0], dict(name='sshd', pid=200, service='sshd.service'))
        self.assertEqual(len(rows[22]['owners']), 2)
        self.assertEqual(rows[3000]['endpoint'], '[::1]:3000')
        self.assertEqual(rows[3000]['service'], 'dev.service')
        self.assertEqual(rows[53]['scope'], 'loopback')
        self.assertEqual(rows[443]['scope'], 'wildcard')
        self.assertEqual(rows[5353]['scope'], 'interface')
        self.assertEqual(rows[8080]['scope'], 'wildcard')
        self.assertEqual(rows[443]['owners'], [])
        self.assertEqual(result, self.collect())

    def test_malformed_endpoints_and_non_listener_records_are_omitted(self):
        invalid = ['garbage', 'tcp ESTAB 0 0 127.0.0.1:80 *:*',
                   'tcp LISTEN 0 0 localhost:80 *:*', 'tcp LISTEN 0 0 :80 *:*',
                   'tcp LISTEN 0 0 127.0.0.1:65536 *:*',
                   'tcp LISTEN 0 0 [::1]:* *:*']
        result = self.collect('\n'.join(invalid) + '\n' + FIXTURE)
        self.assertEqual(result['omitted'], len(invalid))
        self.assertTrue(result['partial'])
        self.assertEqual(len(result['listeners']), 6)

    def test_cgroup_legacy_hierarchy_missing_and_size_limit(self):
        self.cgroup(10, '4:cpu:/wrong.service\n1:name=systemd:/system.slice/right.service\n')
        self.cgroup(11, '0::/' + 'a' * MAX_CGROUP + '.service')
        collector = Collector(proc_root=self.root)
        self.assertEqual(collector._service(10), 'right.service')
        self.assertIsNone(collector._service(11))
        self.assertIsNone(collector._service(12))
        with patch.object(Path, 'open', side_effect=PermissionError):
            self.assertIsNone(collector._service(10))
        self.cgroup(13, f'0::/user.slice/user@{1000}.service/app.slice/app-terminal.scope\n')
        self.assertIsNone(collector._service(13))

    def test_duplicate_socket_rows_have_distinct_stable_ids(self):
        fixture = 'tcp LISTEN 0 128 127.0.0.1:3000 *:*\n' * 2
        rows = self.collect(fixture)['listeners']
        self.assertEqual(len({row['id'] for row in rows}), 2)
        self.assertEqual(rows, self.collect(fixture)['listeners'])

    def test_read_only_numeric_listening_argv(self):
        executable = self.script('import sys\nassert sys.argv[1:] == ["-H", "-l", "-n", "-t", "-u", "-p", "-e"]\nprint(' + repr(FIXTURE) + ')\n')
        result = Collector(ss=executable, proc_root=self.root).collect()
        self.assertTrue(result['available'], result['errors'])
        self.assertEqual(len(result['listeners']), 6)

    def test_missing_ss_permission_failure_and_valid_empty_results(self):
        self.assertFalse(Collector(ss=self.root / 'missing').collect()['available'])
        executable = self.script('pass\n')
        executable.chmod(0o600)
        self.assertFalse(Collector(ss=executable).collect()['available'])
        self.assertTrue(self.collect('')['available'])
        self.assertEqual(self.collect('')['errors'], [])
        executable = self.script('import sys\nsys.stderr.write("Permission denied\\n")\nsys.exit(1)\n')
        result = Collector(ss=executable).collect()
        self.assertFalse(result['available'])
        self.assertIn('Permission denied', result['errors'])
        executable = self.script('import sys\nsys.stderr.write("Cannot open netlink socket: Operation not permitted\\n")\n')
        result = Collector(ss=executable).collect()
        self.assertFalse(result['available'])

    def test_partial_stderr_and_row_limit(self):
        executable = self.script('import sys\nprint(' + repr(FIXTURE) + ')\nsys.stderr.write("Some owners unavailable\\n")\n')
        result = Collector(ss=executable, max_listeners=2).collect()
        self.assertTrue(result['available'])
        self.assertTrue(result['partial'])
        self.assertEqual(result['omitted'], 4)
        self.assertEqual(len(result['listeners']), 2)

    def test_timeout_output_limit_and_cancellation(self):
        executable = self.script('import time\ntime.sleep(5)\n')
        start = time.monotonic()
        result = Collector(ss=executable, timeout=.1).collect()
        self.assertLess(time.monotonic() - start, 2)
        self.assertFalse(result['available'])
        self.assertIn('exceeded', result['errors'][0])
        executable = self.script('print("x" * 10000)\n')
        result = Collector(ss=executable, max_output=1024).collect()
        self.assertIn('output exceeded', result['errors'][0])
        executable = self.script('import time\ntime.sleep(5)\n')
        collector = Collector(ss=executable)
        results = []
        worker = threading.Thread(target=lambda: results.append(collector.collect()))
        worker.start()
        time.sleep(.05)
        collector.cancel()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertFalse(results[0]['available'])
        self.assertFalse(collector.collect()['available'])

    def test_accounts_with_hidden_pids_explicit_uid_and_implicit_root(self):
        passwd = self.root / 'passwd'
        passwd.write_text('root:x:0:0:root:/root:/bin/sh\nalice:x:1000:1000:Alice:/nonexistent:/bin/sh\n')
        collector = Collector(proc_root=self.root, passwd_path=passwd)
        raw = ('tcp LISTEN 0 128 127.0.0.1:80 *:* ino:123 sk:1\n'
               'tcp LISTEN 0 128 127.0.0.1:81 *:* uid:1000 ino:124 sk:2\n'
               'tcp LISTEN 0 128 127.0.0.1:82 *:* uid:12345 ino:125 sk:3\n'
               'tcp LISTEN 0 128 127.0.0.1:83 *:*\n')
        rows = collector.parse_output(raw)['listeners']
        self.assertEqual([(row['uid'], row['account']) for row in rows],
                         [(0, 'root'), (1000, 'alice'), (12345, None), (None, None)])
        self.assertTrue(all(not row['owners'] for row in rows))

    def test_uid_metadata_ignores_process_names_and_rejects_malformed_uids(self):
        self.assertEqual(Collector._uid('users:(("fake uid:0 ino:999",pid=10,fd=3)) uid:1000 ino:123'), 1000)
        self.assertIsNone(Collector._uid('users:(("fake uid:0 ino:999",pid=10,fd=3))'))
        self.assertEqual(Collector._uid('users:(("fake \\" uid:999",pid=10,fd=3)) ino:123'), 0)
        for metadata in ('uid:no ino:123', 'uid:-1 ino:123', 'uid:4294967295 ino:123',
                         'uid:1000 uid:0 ino:123', 'ino:invalid',
                         'users:(("unfinished uid:0 ino:123', 'uid: ino:123'):
            with self.subTest(metadata=metadata):
                self.assertIsNone(Collector._uid(metadata))

    def test_passwd_reads_are_local_bounded_and_permission_tolerant(self):
        passwd = self.root / 'passwd'
        passwd.write_text('bad:x:not-a-uid:0::/:/bin/sh\nroot:x:0:0::/:/bin/sh\n' +
                          'x' * MAX_PASSWD + '\nalice:x:1000:1000::/:/bin/sh\n')
        collector = Collector(passwd_path=passwd)
        accounts = collector._accounts(time.monotonic() + 2)
        self.assertEqual(accounts, {0: 'root'})
        with patch.object(Path, 'open', side_effect=PermissionError):
            row = collector.parse_output('tcp LISTEN 0 128 *:80 *:* uid:1000 ino:123\n')['listeners'][0]
        self.assertEqual(row['uid'], 1000)
        self.assertIsNone(row['account'])

    def test_public_parser_enforces_limits_errors_and_cancellation(self):
        collector = Collector(max_output=1024, max_listeners=2, passwd_path=self.root / 'missing')
        result = collector.parse_output(FIXTURE, errors=['Some metadata inaccessible'])
        self.assertTrue(result['available'])
        self.assertTrue(result['partial'])
        self.assertEqual(result['omitted'], 4)
        self.assertEqual(len(result['listeners']), 2)
        result = collector.parse_output(FIXTURE + 'x' * 2000)
        self.assertIn('Socket output exceeded 1024 bytes', result['errors'])
        result = collector.parse_output('', errors=['Permission denied'], success=False)
        self.assertFalse(result['available'])
        collector.cancel()
        self.assertFalse(collector.parse_output(FIXTURE)['available'])


if __name__ == '__main__':
    unittest.main()
