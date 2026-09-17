"""Run only isolated Python terminal fixtures; never start the real Codex client."""
import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

from test_codex_colors import PALETTE

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'components/apps/bin/atlas-codex'


class CodexPtyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        palette = self.home / '.local/state/omarchy/current/theme/colors.toml'
        palette.parent.mkdir(parents=True)
        palette.write_text('\n'.join(f'{key} = "{value}"' for key, value in PALETTE.items()))
        self.palette = palette
        self.env = dict(os.environ, HOME=str(self.home), ATLAS_AGENTS_AUTO='0')
        self.env.pop('NO_COLOR', None)
        self.env.pop('ATLAS_CODEX_COLORS', None)
        self.script = self.home / 'child with spaces.py'

    def start(self, script, args=(), env=None):
        self.script.write_text(script)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        original = termios.tcgetattr(slave)
        process = subprocess.Popen([sys.executable, str(ADAPTER), '--', sys.executable,
                                    str(self.script), *args], stdin=slave, stdout=slave,
                                   stderr=slave, env=self.env | (env or {}))
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        self.addCleanup(cleanup)
        return process, master, slave, original

    def read_until(self, process, master, marker=b'', timeout=5):
        result = bytearray()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if select.select([master], [], [], 0.05)[0]:
                try:
                    part = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO: break
                    raise
                result.extend(part)
                if marker and marker in result: return bytes(result)
            elif process.poll() is not None:
                return bytes(result)
        if process.poll() is None:
            process.kill()
        self.fail(f'terminal fixture timed out: {bytes(result)!r}')

    def finish(self, started):
        process, master, slave, original = started
        try:
            output = self.read_until(process, master)
            code = process.wait(timeout=5)
            self.assertEqual(termios.tcgetattr(slave), original)
            return output, code
        finally:
            os.close(master)
            os.close(slave)

    def test_real_pty_literal_arguments_output_and_exit(self):
        args = ['two words', '', 'line\nbreak', '$(touch unwanted)', '*?[]']
        started = self.start('''import json, os, sys
assert os.isatty(0) and os.isatty(1)
assert os.open('/dev/tty', os.O_RDWR) >= 0
print(json.dumps(sys.argv[1:]))
os.write(1, b'\\x1b[36mCOLOR\\x1b[0mTAIL\\x1b[')
raise SystemExit(37)
''', args)
        output, code = self.finish(started)
        self.assertEqual(code, 37)
        self.assertIn(json.dumps(args).encode(), output)
        self.assertIn(b'\x1b[38;2;255;90;18mCOLOR', output)
        self.assertTrue(output.endswith(b'TAIL\x1b['), output)
        self.assertFalse((self.home / 'unwanted').exists())

    def test_non_tty_and_explicit_opt_out_keep_bytes(self):
        script = "import os; os.write(1, b'\\x1b[36mRAW'); raise SystemExit(23)"
        for env in ({'NO_COLOR': ''}, {'ATLAS_CODEX_COLORS': '0'}):
            output, code = self.finish(self.start(script, env=env))
            self.assertEqual((output, code), (b'\x1b[36mRAW', 23))
        self.script.write_text(script)
        result = subprocess.run([sys.executable, str(ADAPTER), '--', sys.executable, str(self.script)],
                                capture_output=True, env=self.env, timeout=5)
        self.assertEqual((result.stdout, result.returncode), (b'\x1b[36mRAW', 23))

    def test_missing_invalid_and_other_palettes_bypass(self):
        script = "import os; os.write(1, b'\\x1b[36mRAW')"
        for value in ('not toml {', 'accent = "#abcdef"', 'accent = "#ff5a12"'):
            self.palette.write_text(value)
            self.assertEqual(self.finish(self.start(script)), (b'\x1b[36mRAW', 0))
        self.palette.unlink()
        self.assertEqual(self.finish(self.start(script)), (b'\x1b[36mRAW', 0))

    def test_input_resize_and_ctrl_c(self):
        started = self.start('''import fcntl, os, signal, struct, termios, tty
assert os.tcgetpgrp(0) == os.getpgrp()
signal.signal(signal.SIGWINCH, lambda *_: os.write(1, b'SIZE=' + str(struct.unpack('HHHH', fcntl.ioctl(0, termios.TIOCGWINSZ, b'\\0'*8))[:2]).encode()))
signal.signal(signal.SIGINT, lambda *_: exit(42))
print('READY', flush=True)
line = input()
print('INPUT=' + line, flush=True)
while True: signal.pause()
''')
        process, master, slave, _ = started
        self.read_until(process, master, b'READY')
        os.write(master, 'æ ø å\n'.encode())
        self.assertIn('INPUT=æ ø å'.encode(), self.read_until(process, master, b'INPUT='))
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 38, 120, 0, 0))
        process.send_signal(signal.SIGWINCH)
        self.assertIn(b'SIZE=(38, 120)', self.read_until(process, master, b'SIZE='))
        os.write(master, b'\x03')
        _, code = self.finish(started)
        self.assertEqual(code, 42)

    def test_termination_forwards_and_reaps_child(self):
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            with self.subTest(sig=sig):
                pidfile = self.home / 'child.pid'
                started = self.start(f'''import os, pathlib, signal
pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid()))
print('READY', flush=True)
while True: signal.pause()
''')
                process, master, _, _ = started
                self.read_until(process, master, b'READY')
                pid = int(pidfile.read_text())
                process.send_signal(sig)
                _, code = self.finish(started)
                self.assertEqual(code, 128 + sig)
                with self.assertRaises(ProcessLookupError): os.kill(pid, 0)

    def test_ignored_term_is_bounded(self):
        started = self.start('''import signal
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print('READY', flush=True)
while True: signal.pause()
''')
        process, master, _, _ = started
        self.read_until(process, master, b'READY')
        process.terminate()
        _, code = self.finish(started)
        self.assertEqual(code, 128 + signal.SIGKILL)

    def test_large_output_drains_and_descendant_cannot_hold_terminal(self):
        started = self.start('''import os, signal, time
signal.signal(signal.SIGHUP, signal.SIG_IGN)
os.write(1, b'X' * 200000)
if os.fork() == 0:
    time.sleep(2)
    os._exit(0)
os._exit(11)
''')
        output, code = self.finish(started)
        self.assertEqual(code, 11)
        self.assertEqual(output, b'X' * 200000)

    def test_closed_child_terminal_cannot_leave_wrapper_hanging(self):
        started = self.start("""import os, signal, time
signal.signal(signal.SIGHUP, signal.SIG_IGN)
for fd in (0, 1, 2): os.close(fd)
time.sleep(30)
""")
        _, code = self.finish(started)
        self.assertEqual(code, 128 + signal.SIGKILL)

    def test_help_and_version_arguments_bypass_coloring(self):
        for argument in ('--help', '--version', '--remote=test'):
            output, code = self.finish(self.start("import os; os.write(1, b'\\x1b[36mRAW')", [argument]))
            self.assertEqual((output, code), (b'\x1b[36mRAW', 0))
        result = subprocess.run([sys.executable, str(ADAPTER), '--help'], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'usage:', result.stdout)

    def test_external_stop_and_child_stop_restore_then_resume_terminal(self):
        for child_stop in (False, True):
            with self.subTest(child_stop=child_stop):
                started = self.start("""import os, signal
print('READY', flush=True)
input()
""" + ("os.kill(os.getpid(), signal.SIGSTOP)\n" if child_stop else '') + "print('RESUMED', flush=True)\n")
                process, master, slave, original = started
                self.read_until(process, master, b'READY')
                if child_stop:
                    os.write(master, b'\n')
                else:
                    process.send_signal(signal.SIGTSTP)
                end = time.monotonic() + 3
                while time.monotonic() < end:
                    waited, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
                    if waited and os.WIFSTOPPED(status):
                        break
                    time.sleep(0.01)
                else:
                    process.kill()
                    self.fail('adapter did not stop')
                self.assertEqual(termios.tcgetattr(slave), original)
                process.send_signal(signal.SIGCONT)
                if not child_stop:
                    os.write(master, b'\n')
                output, code = self.finish(started)
                self.assertEqual(code, 0)
                self.assertIn(b'RESUMED', output)

    def test_redirected_stderr_remains_separate_and_bypasses_colors(self):
        self.script.write_text("import os; os.write(1, b'\\x1b[36mOUT'); os.write(2, b'ERR')")
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen([sys.executable, str(ADAPTER), '--', sys.executable, str(self.script)],
                                       stdin=slave, stdout=slave, stderr=subprocess.PIPE, env=self.env)
            _, errors = process.communicate(timeout=5)
            output = self.read_until(process, master)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(output, b'\x1b[36mOUT')
            self.assertEqual(errors, b'ERR')
        finally:
            os.close(master)
            os.close(slave)

    def test_continuous_descendant_output_cannot_keep_adapter_alive(self):
        started = self.start("""import os, signal, time
signal.signal(signal.SIGHUP, signal.SIG_IGN)
if os.fork() == 0:
    while True: os.write(1, b'X' * 1024)
time.sleep(0.05)
os._exit(11)
""")
        output, code = self.finish(started)
        self.assertEqual(code, 11)
        self.assertTrue(output)
        self.assertEqual(set(output), {ord('X')})
