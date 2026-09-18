"""Ownership, focus and literal argv checks using disposable tmux servers."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'components/apps'))
SPEC = importlib.util.spec_from_file_location(
    'atlas_agents_tmux_test', ROOT / 'components/apps/atlas_agents/tmux_panel.py')
panels = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panels)


class RuntimeTests(unittest.TestCase):
    def test_runtime_directory_is_private_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.dict(os.environ, {'XDG_RUNTIME_DIR': directory}):
                runtime = panels.runtime_directory()
                self.assertEqual(runtime, base / 'atlas-agents')
                self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)
                runtime.rmdir()
                runtime.symlink_to(base, target_is_directory=True)
                with self.assertRaises(OSError):
                    panels.runtime_directory()

    def test_lock_rejects_symlink_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = panels.Panels('%1', ['viewer'], runtime_dir=directory)
            target = Path(directory) / 'keep'
            target.write_text('unchanged')
            (Path(directory) / manager.lock_name).symlink_to(target)
            with self.assertRaises(OSError):
                manager.close()
            self.assertEqual(target.read_text(), 'unchanged')


@unittest.skipUnless(shutil.which('tmux'), 'tmux is not installed')
class PanelsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas-agents-tmux-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.socket = self.root / 'tmux.sock'
        self.addCleanup(lambda: subprocess.run(
            ['tmux', '-S', str(self.socket), 'kill-server'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        try:
            self.tm('-f', '/dev/null', 'new-session', '-d', '-s', 'test',
                    '-x', '180', '-y', '35', 'sleep', '120')
        except subprocess.CalledProcessError as error:
            message = error.output or ''
            if 'Operation not permitted' in message or 'Permission denied' in message:
                self.skipTest('sandbox does not allow a temporary tmux socket')
            raise
        self.origin = self.tm('display-message', '-p', '-t', 'test:0', '#{pane_id}')
        tmux_environment = f'{self.socket},{self.tm("display-message", "-p", "#{pid}")},0'
        self.environment = patch.dict(os.environ, {'TMUX': tmux_environment})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.viewer = self.root / 'viewer #{pane_id} $(no-command).py'
        self.viewer.write_text('''import json, pathlib, sys, time
snapshot = pathlib.Path(sys.argv[sys.argv.index('--snapshot') + 1])
snapshot.with_suffix('.seen').write_text(json.dumps(sys.argv))
time.sleep(90)
''')
        self.snapshot = self.root / 'snapshot #{pane_id} $(no-command).json'
        self.snapshot.write_text('{}')
        self.manager = panels.Panels(self.origin, [sys.executable, str(self.viewer)],
                                     runtime_dir=self.root)

    def tm(self, *args):
        return subprocess.check_output(['tmux', '-S', str(self.socket), *args],
                                       text=True, stderr=subprocess.STDOUT).strip()

    def wait(self, condition):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.025)
        self.fail('Temporary tmux viewer did not become ready')

    def test_wide_open_preserves_focus_reuses_panel_and_passes_literal_paths(self):
        pane = self.manager.open('thread-one', str(self.snapshot))
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)
        self.assertEqual(self.tm('display-message', '-p', '-t', pane, '#{pane_width}'), '60')
        self.assertEqual(self.manager.open('thread-one', str(self.snapshot)), pane)
        self.assertEqual(self.manager.existing(), [pane])
        self.wait(lambda: self.snapshot.with_suffix('.seen').exists())
        argv = json.loads(self.snapshot.with_suffix('.seen').read_text())
        self.assertEqual(argv, [str(self.viewer), '--snapshot', str(self.snapshot)])
        replacement = self.manager.open('thread-two', str(self.snapshot))
        self.assertNotEqual(pane, replacement)
        self.assertEqual(self.tm('display-message', '-p', '-t', replacement, '#{pane_width}'), '60')
        self.assertEqual(self.tm('display-message', '-p', '-t', replacement, '#{window_id}'),
                         self.tm('display-message', '-p', '-t', self.origin, '#{window_id}'))
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)
        self.assertTrue(self.manager.dismiss())
        self.assertFalse(self.manager.close())
        self.assertTrue(self.snapshot.exists())

    def test_sidebar_size_tracks_available_columns_with_readable_limits(self):
        for columns, expected in ((130, 48), (140, 48), (141, 60), (150, 60), (240, 60)):
            with self.subTest(columns=columns):
                self.tm('resize-window', '-t', 'test:0', '-x', str(columns), '-y', '35')
                pane = self.manager.open('thread-one', str(self.snapshot))
                self.assertEqual(int(self.tm('display-message', '-p', '-t', pane,
                                              '#{pane_width}')), expected)
                self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)
                self.manager.close()

    def test_narrow_window_opens_detached_and_cleanup_keeps_other_panes(self):
        self.tm('resize-window', '-t', 'test:0', '-x', '100', '-y', '35')
        other = self.tm('new-window', '-d', '-n', 'unrelated', '-P', '-F', '#{pane_id}',
                        'sleep', '120')
        self.tm('set-option', '-p', '-t', other, '@atlas_agents_origin', '%99999')
        self.tm('set-option', '-p', '-t', other, '@atlas_agents_thread', 'thread-one')
        pane = self.manager.open('thread-one', str(self.snapshot))
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)
        self.assertNotEqual(self.tm('display-message', '-p', '-t', pane, '#{window_id}'),
                            self.tm('display-message', '-p', '-t', self.origin, '#{window_id}'))
        replacement = self.manager.open('thread-two', str(self.snapshot))
        self.assertNotEqual(pane, replacement)
        self.assertEqual(self.manager.existing(), [replacement])
        self.assertTrue(self.manager.close())
        self.assertEqual(self.tm('display-message', '-p', '-t', other, '#{pane_id}'), other)
        self.assertEqual(len(self.tm('list-windows').splitlines()), 2)

    def test_parallel_open_creates_one_panel_and_detects_manual_close(self):
        def open_panel(_):
            manager = panels.Panels(self.origin, [sys.executable, str(self.viewer)],
                                    runtime_dir=self.root)
            return manager.open('thread-one', str(self.snapshot))
        with ThreadPoolExecutor(max_workers=4) as executor:
            created = list(executor.map(open_panel, range(4)))
        self.assertEqual(len(set(created)), 1)
        self.assertEqual(self.manager.existing(), [created[0]])
        self.tm('kill-pane', '-t', created[0])
        self.assertEqual(self.manager.existing(), [])
        self.assertFalse(self.manager.close())


if __name__ == '__main__':
    unittest.main()
