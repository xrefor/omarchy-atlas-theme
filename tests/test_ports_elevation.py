"""Fixed Polkit reader contract, without real privilege or graphical prompts."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_ports import elevation


FRAME_READER = '''import os, struct, sys
while True:
 token = os.read(0, 1)
 if token != b'S': break
 payload = b'tcp LISTEN 0 128 127.0.0.1:3000 *:* ino:42\\n'
 sys.stdout.buffer.write(struct.pack('!BI', 0, len(payload)) + payload)
 sys.stdout.buffer.flush()
'''


class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='atlas-ports-auth-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def inspect(self, body=FRAME_READER, action=None, **limits):
        script = self.root / 'fake-pkexec'
        script.write_text('#!/usr/bin/python3\n' + body)
        script.chmod(0o700)
        real_popen = subprocess.Popen
        calls = []
        def launch(command, **kwargs):
            calls.append((command, kwargs))
            return real_popen([str(script), *command[1:]], **kwargs)
        with patch.object(elevation, '_trusted_executable', side_effect=lambda path: path), \
             patch.object(elevation.subprocess, 'Popen', side_effect=launch), \
             patch.multiple(elevation, **({'AUTH_TIMEOUT': elevation.AUTH_TIMEOUT} | limits)):
            session = elevation.SessionCollector()
            try:
                result = action(session) if action else session.authenticate()
            finally:
                session.cancel()
        return result, calls

    def test_fixed_command_environment_and_one_graphical_auth_for_live(self):
        def action(session):
            self.assertTrue(session.authenticate()['elevated'])
            self.assertTrue(session.collect()['elevated'])
            self.assertTrue(session.collect()['elevated'])
            self.assertTrue(session.enabled)
            return session.collect()
        result, calls = self.inspect(action=action)
        self.assertEqual(len(calls), 1)
        command, options = calls[0]
        self.assertEqual(command, ['/usr/bin/pkexec', '--disable-internal-agent',
                                  '/usr/bin/python3', '-I', '-S', '-u', '-c', elevation.ROOT_READER])
        self.assertEqual(options['env'], {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
        self.assertTrue(options['close_fds'])
        self.assertNotIn('shell', options)
        for stream in ('stdin', 'stdout', 'stderr'):
            self.assertEqual(options[stream], subprocess.PIPE)
        self.assertEqual(result['listeners'][0]['port'], 3000)

    def test_disable_closes_reader_and_reauthentication_is_explicit(self):
        def action(session):
            session.authenticate()
            process = session._process
            with patch.object(process, 'terminate', side_effect=PermissionError):
                session.disable()
            self.assertFalse(session.enabled)
            self.assertEqual(process.wait(timeout=1), 0)
            with patch.object(session.normal, 'collect', return_value={'available': True}) as collect:
                session.collect()
                collect.assert_called_once()
            self.assertTrue(session.authenticate()['available'])
            session.cancel()
            self.assertFalse(session.authenticate()['available'])
            return session.collect()
        result, calls = self.inspect(action=action)
        self.assertFalse(result['available'])
        self.assertEqual(len(calls), 2)

    def test_reader_expiry_falls_back_without_reauthentication(self):
        body = FRAME_READER.replace('while True:', 'for _ in range(1):')
        def action(session):
            self.assertTrue(session.authenticate()['elevated'])
            time.sleep(.05)
            with patch.object(session.normal, 'collect', return_value={'available': True, 'listeners': []}):
                result = session.collect()
                self.assertFalse(result['elevated'])
                self.assertFalse(session.enabled)
                self.assertIn('Admin live ended', str(result['notices']))
                session.collect()
            return result
        _, calls = self.inspect(body, action=action)
        self.assertEqual(len(calls), 1)

    def test_authentication_exit_codes(self):
        for code, text in ((126, 'cancelled'), (127, 'unavailable')):
            result, _ = self.inspect(f'import sys\nsys.exit({code})\n')
            self.assertIn(text, result['errors'][0])
            self.assertFalse(result['elevated'])

    def test_invalid_partial_failure_and_oversized_frames(self):
        for payload, message in ((b'\x02\x00\x00\x00\x00', 'Invalid'),
                                 (b'\x00\x00\x00\x00\x04ab', 'incomplete'),
                                 (b'\x01\x00\x00\x00\x00', 'failed'),
                                 (b'\x00\x7f\xff\xff\xff', 'size limit')):
            body = f'import os\nos.read(0, 1)\nos.write(1, {payload!r})\n'
            result, _ = self.inspect(body)
            self.assertFalse(result['available'])
            self.assertIn(message, result['errors'][0])

    def test_auth_timeout_and_stderr_flood_are_bounded(self):
        start = time.monotonic()
        result, _ = self.inspect('import time\ntime.sleep(1)\n', AUTH_TIMEOUT=.05)
        self.assertIn('timed out', result['errors'][0])
        self.assertLess(time.monotonic() - start, .8)
        result, _ = self.inspect('import os\nos.write(2, b"x" * 20000)\n')
        self.assertIn('size limit', result['errors'][0])

    def test_cancel_inflight_drops_data_and_never_kills_process_group(self):
        ready = self.root / 'ready'
        body = f'import os,time\nos.read(0,1)\nopen({str(ready)!r},"w").close()\ntime.sleep(.4)\n'
        def action(session):
            results = []
            thread = threading.Thread(target=lambda: results.append(session.authenticate()))
            thread.start()
            deadline = time.monotonic() + 2
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(ready.exists())
            with patch.object(subprocess.Popen, 'kill') as kill:
                session.cancel()
                thread.join(1)
                kill.assert_not_called()
            self.assertFalse(thread.is_alive())
            self.assertFalse(results[0]['available'])
            return results[0]
        self.inspect(body, action=action)

    def test_trust_checks_and_cancellation_before_spawn(self):
        script = self.root / 'unsafe'
        script.write_text('x')
        script.chmod(0o700)
        with self.assertRaises(ValueError):
            elevation._trusted_executable(script)
        with self.assertRaises(OSError):
            elevation._trusted_executable(self.root / 'missing')
        session = elevation.SessionCollector()
        with patch.object(elevation, '_trusted_executable', side_effect=lambda path: session.disable()), \
             patch.object(elevation.subprocess, 'Popen') as spawn:
            self.assertFalse(session.authenticate()['available'])
            spawn.assert_not_called()
        with patch.object(elevation, '_trusted_executable', side_effect=ValueError), \
             patch.object(elevation.subprocess, 'Popen') as spawn:
            self.assertFalse(session.authenticate()['available'])
            spawn.assert_not_called()

    def test_stop_uses_eof_even_when_root_cannot_be_signaled(self):
        process = Mock()
        process.poll.return_value = None
        process.terminate.side_effect = PermissionError
        elevation._stop(process)
        process.terminate.assert_called_once()
        process.kill.assert_not_called()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close.assert_called_once()
        process.wait.assert_called_once_with(timeout=.2)

    def test_stop_terminates_pending_authentication_prompt(self):
        process = subprocess.Popen(['/usr/bin/python3', '-I', '-S', '-c',
                                    'import time; time.sleep(30)'],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        elevation._stop(process)
        self.assertIsNotNone(process.poll())

    def helper(self, *, replacement=None):
        literal = elevation.ROOT_READER
        if replacement:
            for before, after in replacement.items():
                literal = literal.replace(before, after)
        process = subprocess.Popen(['/usr/bin/python3', '-I', '-S', '-u', '-c', literal],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: elevation._stop(process))
        return process

    def test_literal_reader_exits_on_eof_quit_invalid_token_idle_and_lifetime(self):
        for token in (b'', b'Q', b'X'):
            process = self.helper()
            out, err = process.communicate(token, timeout=1)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(out, b'')
            self.assertEqual(err, b'')
        for replacements in ({'IDLE_TIMEOUT = 10': 'IDLE_TIMEOUT = .05'},
                             {'LIFETIME = 300': 'LIFETIME = 1'}):
            process = self.helper(replacement=replacements)
            self.assertEqual(process.wait(timeout=2), 0)

    def test_literal_reader_uses_fixed_ss_and_framing_under_fake_pkexec(self):
        # Runs the exact literal under our own uid, never actual pkexec/root.
        result, calls = self.inspect('import os,sys\nos.execv(sys.argv[2], sys.argv[2:])\n')
        self.assertEqual(len(calls), 1)
        # Sandbox netlink restrictions may cause a correctly framed failure.
        self.assertTrue(result.get('elevated') or 'inspection failed' in result['errors'][0])
        self.assertIn("['/usr/bin/ss', '-H', '-l', '-n', '-t', '-u', '-p', '-e']", elevation.ROOT_READER)

    def test_literal_query_limits_discard_partial_output(self):
        for code in ('import time;time.sleep(1)', 'import os;os.write(1,b"x"*2048)',
                     'import os;os.write(1,b"partial");os.write(2,b"error")'):
            command = repr(['/usr/bin/python3', '-I', '-S', '-c', code])
            process = self.helper(replacement={
                "['/usr/bin/ss', '-H', '-l', '-n', '-t', '-u', '-p', '-e']": command,
                'LIMIT = 1048576': 'LIMIT = 1024', 'QUERY_TIMEOUT = 3': 'QUERY_TIMEOUT = .05'})
            out, _ = process.communicate(b'S', timeout=2)
            self.assertEqual(out[0], 1)
            self.assertEqual(int.from_bytes(out[1:5], 'big'), len(out) - 5)
            self.assertNotIn(b'partial', out[5:])


if __name__ == '__main__':
    unittest.main()
