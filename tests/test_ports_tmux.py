"""Ports panel ownership, literal argv, and native tmux rendering/controls."""
from concurrent.futures import ThreadPoolExecutor
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
from atlas_ports.tmux_panel import Panel


class FakePanel(Panel):
    def __init__(self, directory, width=160):
        self.calls, self.panes, self.width = [], [], width
        super().__init__('%7', ['/path with spaces/atlas-ports', 'show'], runtime_dir=directory)

    def _tmux(self, *args):
        self.calls.append(args)
        if args[0] == 'list-panes':
            return '\n'.join(f'{pane}\t%7' for pane in self.panes)
        if args[0] == 'display-message':
            return f'%7\t$1\t{self.width}'
        if args[0] in ('split-window', 'new-window'):
            self.panes.append('%9')
            return '%9'
        if args[0] == 'kill-pane':
            self.panes.remove(args[-1])
        return ''


class PortsTmuxTests(unittest.TestCase):
    def test_shared_sizing_and_no_directory_argument(self):
        for width, expected in ((160, '60'), (135, '48'), (120, None)):
            with self.subTest(width=width), tempfile.TemporaryDirectory() as directory:
                panel = FakePanel(directory, width)
                self.assertEqual(panel.open(), '%9')
                call = next(call for call in panel.calls if call[0] in ('split-window', 'new-window'))
                self.assertEqual(call[-3:], ('--', '/path with spaces/atlas-ports', 'show'))
                self.assertIn('-d', call)
                if expected:
                    self.assertEqual(call[call.index('-l') + 1], expected)
                else:
                    self.assertIn('ports-services', call)
                self.assertIn(('set-option', '-p', '-t', '%9', '@atlas_ports_origin', '%7'), panel.calls)
                self.assertEqual(panel.open(), '%9')
                self.assertEqual(panel.toggle(), 'closed')

    def test_cli_authenticates_by_default_and_user_flag_skips(self):
        from atlas_ports import __main__ as cli
        with patch.object(cli, 'SessionCollector') as collector, patch.object(cli.ui, 'run') as run:
            self.assertEqual(cli.main(['show']), 0)
            self.assertTrue(run.call_args.kwargs['authenticate_on_open'])
            self.assertEqual(run.call_args.kwargs['inspect_details'], collector.return_value.authenticate)
            self.assertEqual(cli.main(['show', '--user']), 0)
            self.assertFalse(run.call_args.kwargs['authenticate_on_open'])

    def test_origin_resolution_and_missing_tmux(self):
        from atlas_ports import __main__ as cli
        with patch.dict(os.environ, {'TMUX': '/tmp/socket,1,0', 'TMUX_PANE': '%9'}), \
                patch.object(cli, 'tmux', return_value='%9\t%7'):
            self.assertEqual(cli.origin_pane(), '%7')
        with patch.dict(os.environ, {'TMUX': ''}):
            with self.assertRaisesRegex(ValueError, 'atlas-ports show'):
                cli.origin_pane()


@unittest.skipUnless(shutil.which('tmux'), 'tmux is not installed')
class PortsNativeTmuxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='atlas-ports-tmux-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.socket = self.root / 'tmux.sock'
        self.addCleanup(lambda: subprocess.run(['tmux', '-S', str(self.socket), 'kill-server'],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        stub = self.root / 'ss'
        stub.write_text('#!/usr/bin/env python3\n' +
                        "print('tcp LISTEN 0 128 127.0.0.1:3000 0.0.0.0:* users:((\"web-demo\",pid=987654,fd=3))')\n" +
                        "print('udp UNCONN 0 0 0.0.0.0:5353 0.0.0.0:*')\n" +
                        "for port in range(8000, 8040): print(f'tcp LISTEN 0 128 [::1]:{port} [::]:*')\n")
        stub.chmod(0o755)
        self.environment = patch.dict(os.environ, {'PATH': str(self.root) + os.pathsep + os.environ['PATH']})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        try:
            self.tm('-f', '/dev/null', 'new-session', '-d', '-s', 'test', '-x', '180', '-y', '32', 'sleep', '180')
        except subprocess.CalledProcessError as error:
            if 'Operation not permitted' in error.output or 'Permission denied' in error.output:
                self.skipTest('sandbox does not allow a temporary tmux socket')
            raise
        self.origin = self.tm('display-message', '-p', '-t', 'test:0', '#{pane_id}')
        env = patch.dict(os.environ, {'TMUX': f'{self.socket},1,0'})
        env.start()
        self.addCleanup(env.stop)
        self.panel = Panel(self.origin, [sys.executable, str(ROOT / 'components/apps/bin/atlas-ports'), 'show', '--user'],
                           runtime_dir=self.root)

    def tm(self, *args):
        return subprocess.check_output(['tmux', '-S', str(self.socket), *args], text=True,
                                       stderr=subprocess.STDOUT, timeout=5).rstrip('\n')

    def wait_for(self, pane, text):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            value = self.tm('capture-pane', '-p', '-t', pane)
            if text in value:
                return value
            time.sleep(0.05)
        self.fail(f'Panel never displayed {text!r}:\n{value}')

    def test_sidebar_pages_filter_scroll_resize_and_owned_close(self):
        pane = self.panel.open()
        self.wait_for(pane, '3000')
        self.assertEqual(self.tm('display-message', '-p', '-t', pane, '#{pane_width}'), '60')
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)
        self.tm('send-keys', '-t', pane, '2')
        udp = self.wait_for(pane, '5353')
        self.assertNotIn('3000', udp)
        self.tm('send-keys', '-t', pane, '1', 'End')
        bottom = self.wait_for(pane, '8039')
        self.assertIn('P O R T S', bottom.splitlines()[0])
        self.assertIn('/ filter', bottom.splitlines()[-1])
        self.tm('send-keys', '-t', pane, 'Home')
        self.wait_for(pane, '3000')
        self.tm('send-keys', '-t', pane, '1', '/')
        self.tm('send-keys', '-t', pane, '-l', '3000')
        self.tm('send-keys', '-t', pane, 'Enter')
        self.wait_for(pane, 'Filter: 3000')
        frame = self.wait_for(pane, '/ filter')
        self.assertIn('web-demo', frame)
        self.assertNotIn('8000', frame)
        self.tm('resize-pane', '-t', pane, '-x', '48')
        self.wait_for(pane, '3000')
        # Owned close must preserve another utility pane.
        other = self.tm('split-window', '-d', '-t', self.origin, '-P', '-F', '#{pane_id}', 'sleep', '180')
        self.assertTrue(self.panel.close())
        panes = self.tm('list-panes', '-a', '-F', '#{pane_id}').splitlines()
        self.assertIn(self.origin, panes)
        self.assertIn(other, panes)
        self.assertNotIn(pane, panes)

    def test_graphical_auth_on_open_live_updates_cancel_and_owned_close(self):
        # Exercise real curses/tmux with a session fixture. No real authentication
        # subprocess, desktop dialog, credential cache, or password is involved.
        counter = self.root / 'admin-count'
        auth_count = self.root / 'auth-count'
        expired = self.root / 'expired'
        cancelled = self.root / 'cancel-auth'
        closed = self.root / 'closed'
        driver = self.root / 'auth-driver.py'
        driver.write_text(f'''import sys, time
from pathlib import Path
sys.path.insert(0, {str(ROOT / "components/apps")!r})
from atlas_ports import ui
from atlas_ports.backend import Collector
counter = Path({str(counter)!r})
auth_count = Path({str(auth_count)!r})
expired = Path({str(expired)!r})
cancelled = Path({str(cancelled)!r})
closed = Path({str(closed)!r})
class Session:
    enabled = False
    def __init__(self):
        self.normal = Collector()
    def details(self, count):
        value = self.normal.parse_output(
            f'tcp LISTEN 0 128 127.0.0.1:{{4444 + count}} *:* users:(("admin-demo",pid=987655,fd=3)) ino:42')
        return dict(value, elevated=True, captured_at=time.time())
    def authenticate(self):
        count = int(auth_count.read_text()) + 1 if auth_count.exists() else 1
        auth_count.write_text(str(count))
        if cancelled.exists():
            self.disable()
            return dict(available=False, errors=['Administrator details cancelled.'])
        self.enabled = True
        return self.details(0)
    def collect(self):
        if self.enabled and expired.exists():
            self.disable()
            return dict(self.normal.collect(), elevated=False,
                        notices=['Admin live ended. Press a to authenticate again.'])
        if self.enabled:
            count = int(counter.read_text()) + 1 if counter.exists() else 1
            counter.write_text(str(count))
            return self.details(count)
        return self.normal.collect()
    def disable(self):
        self.enabled = False
    def cancel(self):
        self.disable()
        self.normal.cancel()
        closed.touch()
session = Session()
ui.run(session, inspect_details=session.authenticate, stop_admin=session.disable,
       authenticate_on_open=True)
''')
        self.panel.command = [sys.executable, str(driver)]
        pane = self.panel.open()
        frame = self.wait_for(pane, 'ADMIN LIVE')
        self.assertIn('admin-demo', frame)
        self.assertEqual(auth_count.read_text(), '1')
        self.assertNotIn('Authenticate for', frame)
        self.wait_for(pane, '4445')
        self.wait_for(pane, '4446')
        self.assertEqual(auth_count.read_text(), '1')
        expired.touch()
        frame = self.wait_for(pane, 'Admin live ended')
        self.assertNotIn('ADMIN LIVE', frame)
        self.assertIn('3000', frame)
        self.assertEqual(auth_count.read_text(), '1')
        expired.unlink()
        self.tm('send-keys', '-t', pane, 'a')
        self.wait_for(pane, 'ADMIN LIVE')
        self.assertEqual(auth_count.read_text(), '2')
        self.tm('send-keys', '-t', pane, 'r')
        frame = self.wait_for(pane, '3000')
        self.assertNotIn('ADMIN LIVE', frame)
        calls = counter.read_text()
        time.sleep(2.2)
        self.assertEqual(counter.read_text(), calls)
        cancelled.touch()
        self.tm('send-keys', '-t', pane, 'a')
        frame = self.wait_for(pane, 'cancelled')
        self.assertNotIn('ADMIN LIVE', frame)
        self.assertIn('3000', frame)
        self.assertEqual(auth_count.read_text(), '3')
        self.tm('send-keys', '-t', pane, 'q')
        deadline = time.monotonic() + 3
        while self.panel.existing() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertEqual(self.panel.existing(), [])
        self.assertTrue(closed.exists())
        self.assertIn(self.origin, self.tm('list-panes', '-a', '-F', '#{pane_id}').splitlines())

    def test_narrow_window_and_parallel_open_do_not_duplicate(self):
        self.tm('resize-window', '-t', self.origin, '-x', '100', '-y', '32')
        with ThreadPoolExecutor(max_workers=3) as pool:
            panes = list(pool.map(lambda _: self.panel.open(), range(3)))
        self.assertEqual(len(set(panes)), 1)
        pane = panes[0]
        self.wait_for(pane, '3000')
        self.assertEqual(self.tm('display-message', '-p', '-t', pane, '#{window_name}'), 'ports-services')
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)
        self.tm('send-keys', '-t', pane, 'q')
        deadline = time.monotonic() + 3
        while self.panel.existing() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.panel.existing(), [])
        self.assertIn(self.origin, self.tm('list-panes', '-a', '-F', '#{pane_id}').splitlines())


if __name__ == '__main__':
    unittest.main()
