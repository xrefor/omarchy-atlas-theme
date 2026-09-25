"""Exercise appearance switching without touching the user's tmux server."""
from pathlib import Path
import fcntl
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from atlas import palette


@unittest.skipUnless(shutil.which('tmux'), 'tmux is not installed')
class AppearanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='atlas-appearance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.socket = self.root / 'tmux.sock'
        self.addCleanup(lambda: subprocess.run(
            ['tmux', '-S', str(self.socket), 'kill-server'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        try:
            self.tm('-f', '/dev/null', 'new-session', '-d', '-s', 'appearance',
                    '-x', '180', '-y', '35', 'sleep', '120')
        except subprocess.CalledProcessError as error:
            if 'Operation not permitted' in error.output or 'Permission denied' in error.output:
                self.skipTest('sandbox does not allow a temporary tmux socket')
            raise
        master, slave = os.openpty()
        self.addCleanup(os.close, master)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 36, 180, 0, 0))
        environment = dict(os.environ, TERM='xterm-256color')
        environment.pop('TMUX', None)
        self.client = subprocess.Popen(
            ['tmux', '-S', str(self.socket), 'attach-session', '-t', 'appearance'],
            stdin=slave, stdout=slave, stderr=slave, env=environment)
        os.close(slave)
        self.addCleanup(self.client.wait)
        self.addCleanup(self.client.terminate)
        self.rendered = bytearray()
        def drain():
            try:
                while chunk := os.read(master, 65536):
                    self.rendered.extend(chunk)
            except OSError:
                pass
        threading.Thread(target=drain, daemon=True).start()
        for _ in range(100):
            if self.tm('display-message', '-p', '-t', 'appearance', '#{session_attached}') == '1':
                break
            time.sleep(.01)
        else:
            self.fail('disposable tmux client did not attach')
        template = ROOT / 'components/apps/templates/tmux.conf'
        tokens = set(re.findall(r'\{\{ (\w+) \}\}', template.read_text()))
        colors = {token: '#777777' for token in tokens}
        colors.update(accent='#ff6600', foreground='#eeeeee', muted='#444444')
        self.config = self.root / 'appearance.conf'
        self.layout = self.root / 'layout.conf'
        self.config.write_text(palette.render(template, colors).replace(
            '~/.config/atlas/layout.conf', str(self.layout)))

    def tm(self, *args):
        return subprocess.check_output(['tmux', '-S', str(self.socket), *args],
                                       text=True, stderr=subprocess.STDOUT).strip()

    def load(self):
        self.tm('source-file', str(self.config))

    def option(self, name):
        return self.tm('show-options', '-gv', name)

    def test_switch_and_restore_preserves_panes(self):
        self.load()
        names = ('status-left', 'status-left-length', 'status-right',
                 'window-status-format', 'window-status-current-format',
                 'window-status-separator', 'pane-border-style', 'pane-active-border-style',
                 'status', 'status-format[1]', 'pane-border-indicators')
        classic = {name: self.option(name) for name in names}
        self.tm('split-window', '-h', '-t', 'appearance', 'sleep', '120')
        before = self.tm('list-panes', '-t', 'appearance', '-F', '#{pane_id}:#{pane_width}:#{pane_height}')
        self.layout.write_text('set -g @atlas-layout framed\n')
        self.load()
        self.assertEqual(self.option('pane-active-border-style'), 'fg=#777777')
        self.assertIn('fg=#eeeeee', self.option('window-status-current-format'))
        self.assertIn('▎', self.option('window-status-current-format'))
        framed = self.tm('list-panes', '-t', 'appearance', '-F', '#{pane_id}:#{pane_width}:#{pane_height}')
        for old, new in zip(before.splitlines(), framed.splitlines()):
            old_id, old_width, old_height = old.split(':')
            new_id, new_width, new_height = new.split(':')
            self.assertEqual((old_id, old_width), (new_id, new_width))
            self.assertEqual(int(old_height) - 1, int(new_height))
        self.assertEqual(self.option('pane-border-indicators'), 'arrows')
        # Inspect the attached client's actual terminal stream as well as the
        # format expansion: the native status renderer must draw the hairline.
        for _ in range(100):
            if ('─' * 20).encode() in self.rendered:
                break
            time.sleep(.01)
        else:
            self.fail('native status renderer did not emit the horizontal rail')
        self.load()
        self.assertEqual(framed, self.tm('list-panes', '-t', 'appearance', '-F', '#{pane_id}:#{pane_width}:#{pane_height}'))
        self.layout.write_text('set -g @atlas-layout classic\n')
        self.load()
        self.assertEqual(classic, {name: self.option(name) for name in names})
        self.assertEqual(before, self.tm('list-panes', '-t', 'appearance', '-F', '#{pane_id}:#{pane_width}:#{pane_height}'))
        self.tm('kill-pane', '-t', 'appearance')
        self.assertEqual(self.tm('display-message', '-p', '-t', 'appearance', '#{window_panes}'), '1')
        self.assertEqual(self.tm('display-message', '-p', '-t', 'appearance', '#{pane_width}'), '180')

    def test_framed_rail_collapses_at_narrow_width(self):
        self.tm('set-option', '-g', '@atlas-layout', 'framed')
        self.load()
        for width, workspace, shortcuts in ((180, True, True), (120, True, True), (80, False, False)):
            left = self.tm('display-message', '-p', self.option('status-left').replace('#{client_width}', str(width)))
            right = self.tm('display-message', '-p', self.option('status-right').replace('#{client_width}', str(width)))
            self.assertEqual('WORKSPACE' in left, workspace)
            self.assertEqual('C-Space' in right, shortcuts)
            rail = self.tm('display-message', '-p', self.option('status-format[1]').replace('#{client_width}', str(width)))
            self.assertEqual(re.sub(r'#\[[^]]*\]', '', rail), '─' * width)

    def test_custom_status_options_and_absent_second_format_restore(self):
        for second in ('#[fg=red]custom #{window_name}', '', None):
            with self.subTest(second=second):
                self.tm('set-option', '-g', 'status', '3')
                self.tm('set-option', '-g', 'pane-border-indicators', 'both')
                if second is None:
                    self.tm('set-option', '-gu', 'status-format[1]')
                else:
                    self.tm('set-option', '-g', 'status-format[1]', second)
                previous = self.option('status-format')
                self.tm('set-option', '-g', '@atlas-layout', 'framed')
                self.load()
                self.tm('set-option', '-g', '@atlas-layout', 'classic')
                self.load()
                self.assertEqual(self.option('status'), '3')
                self.assertEqual(self.option('status-format'), previous)
                self.assertEqual(self.option('pane-border-indicators'), 'both')


if __name__ == '__main__':
    unittest.main()
