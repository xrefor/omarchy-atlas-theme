"""Render the actual curses dashboard in a disposable tmux terminal."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('tmux'), 'tmux is not installed')
class FramedTerminalTests(unittest.TestCase):
    def test_real_cards_resize_history_and_close(self):
        with tempfile.TemporaryDirectory(prefix='atlas-framed-ui-') as directory:
            base = Path(directory)
            socket = base / 'tmux.sock'
            demo = base / 'demo.py'
            demo.write_text(
                'import sys,time\n'
                f'sys.path.insert(0, {str(ROOT / "components/apps")!r})\n'
                'from atlas_agents import ui\n'
                'ui.read_layout_style=lambda: "framed"\n'
                'snapshot={"connected":True,"agents":['
                '{"name":"Palette review","status":"running","started_at":time.time()-103,'
                '"task":"Review shared syntax colors in Neovim and Yazi.",'
                '"plan":[{"step":"Inspect sources","status":"completed"},{"step":"Check contrast","status":"inProgress"},{"step":"Run UI checks","status":"pending"}]},'
                '{"name":"Finished review","status":"completed","started_at":time.time()-100,'
                '"finished_at":time.time()-40,"task":"Completed task"}]}\n'
                'ui.run(lambda:snapshot)\n')

            def tm(*args):
                return subprocess.check_output(['tmux', '-S', str(socket), *args],
                                               text=True, stderr=subprocess.STDOUT)

            def capture_when(predicate):
                deadline = time.monotonic() + 4
                capture = ''
                while time.monotonic() < deadline:
                    capture = tm('capture-pane', '-p')
                    if predicate(capture):
                        return capture
                    time.sleep(.05)
                self.fail('Terminal did not render expected content:\n' + capture)

            try:
                try:
                    tm('-f', '/dev/null', 'new-session', '-d', '-x', '60', '-y', '35',
                       'python3', str(demo))
                except subprocess.CalledProcessError as error:
                    if 'Operation not permitted' in error.output or 'Permission denied' in error.output:
                        self.skipTest('sandbox does not allow a temporary tmux socket')
                    raise
                capture = capture_when(lambda text: 'Palette review' in text)
                self.assertIn('█ █ █', capture)
                self.assertIn('1 of 3 steps complete', capture)
                self.assertIn('┌', capture)
                self.assertIn('h history', capture)
                self.assertNotIn('Finished review', capture)
                self.assertNotIn('Inspect sources', capture)
                tm('send-keys', 'p')
                detailed = capture_when(lambda text: '✓ Inspect sources' in text)
                self.assertIn('● Check contrast', detailed)
                self.assertIn('○ Run UI checks', detailed)
                tm('send-keys', 'p')
                capture_when(lambda text: 'Inspect sources' not in text)
                tm('send-keys', 'h')
                capture_when(lambda text: 'Finished review' in text)
                tm('resize-window', '-x', '24', '-y', '10')
                capture_when(lambda text: 'q close' in text and
                             max(map(len, text.splitlines()), default=0) <= 24)
                tm('send-keys', 'End')
                last = capture_when(lambda text: '└' + '─' * 17 + '┘' in text)
                self.assertIn('└' + '─' * 17 + '┘', last)
                tm('send-keys', 'q')
            finally:
                subprocess.run(['tmux', '-S', str(socket), 'kill-server'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    unittest.main()
