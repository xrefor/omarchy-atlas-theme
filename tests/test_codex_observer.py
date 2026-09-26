"""The Codex color PTY observes the real child and cleans up its agent panel."""
import json
from pathlib import Path
import shlex
import shutil
import sys
import unittest

import test_agents_lifecycle as lifecycle


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'components/apps/bin/atlas-codex'


@unittest.skipUnless(shutil.which('tmux'), 'tmux is not installed')
class CodexObserverTests(unittest.TestCase):
    def setUp(self):
        # Reuse the isolated server and fake session database without inheriting
        # and rerunning the original lifecycle test cases.
        self.fixture = lifecycle.LifecycleTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        fixture = self.fixture
        palette = fixture.root / '.local/state/omarchy/current/theme/colors.toml'
        palette.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / 'colors.toml', palette)
        fixture.fake.write_text(fixture.fake.read_text().replace(
            "'pid': os.getpid(), 'args': sys.argv[1:]",
            "'pid': os.getpid(), 'args': sys.argv[1:], 'tty': os.ttyname(0), "
            "'parent': os.getppid(), 'terminal': os.isatty(0) and os.isatty(1)"))
        # Host preferences must not bypass the PTY in this fixture.
        fixture.tm('set-environment', '-gu', 'NO_COLOR')

    def launch(self, args):
        fixture = self.fixture
        invocation = [sys.executable, str(LAUNCHER), '--observe', '--', str(fixture.fake), *args]
        script = (shlex.join(invocation) + '; status=$?; printf "%s" "$status" > '
                  + shlex.quote(str(fixture.exit_status)) + '; exec sleep 90')
        fixture.tm('respawn-pane', '-k', '-t', fixture.origin, 'bash', '-c', script)
        fixture.wait(fixture.ready.exists)
        return json.loads(fixture.ready.read_text())

    def test_inner_pty_uses_cli_identity_and_closes_panel_on_exit(self):
        fixture = self.fixture
        args = ['--model', 'fixture-model', 'literal spaces #{} $(not a command)']
        ready = self.launch(args)
        self.assertEqual(ready['args'][:len(args)], args)
        self.assertEqual(ready['args'][len(args):], [
            '-c', 'tui.terminal_title=' + json.dumps([
                'thread-id', 'app-name', 'activity', 'thread-name', 'project-name'])])
        self.assertTrue(ready['terminal'])
        self.assertNotEqual(ready['tty'], fixture.tm(
            'display-message', '-p', '-t', fixture.origin, '#{pane_tty}'))
        pid = ready['pid']
        started = lifecycle.backend.process_start(pid)
        self.assertEqual(lifecycle.backend.process_root(pid, fixture.home), 'root')
        observed = fixture.wait(lambda: fixture.snapshot().get('connected') and fixture.snapshot())
        self.assertEqual(observed['session_key'], f'{pid}:{started}')
        self.assertEqual(observed['root_id'], 'root')
        self.assertNotEqual(observed['cli_pid'], ready['parent'])
        watchers = fixture.wait(lambda: fixture.record_watchers(pid))
        self.assertEqual(len(watchers), 1)
        watcher_pid, argv = watchers[0]
        self.assertEqual(argv[argv.index('--pid') + 1], str(pid))

        fixture.child('color-wrapper-child')
        fixture.wait(fixture.owned_panels)
        self.assertEqual(fixture.tm('display-message', '-p', '#{pane_id}'), fixture.origin)
        fixture.wait(lambda: fixture.snapshot().get('agents'))
        self.assertEqual(fixture.snapshot()['agents'][0]['id'], 'color-wrapper-child')
        fixture.exit_request.write_text('17')
        fixture.wait(fixture.exit_status.exists)
        self.assertEqual(fixture.exit_status.read_text(), '17')
        fixture.wait(lambda: lifecycle.backend.process_start(watcher_pid) is None)
        fixture.wait(lambda: not fixture.owned_panels())
        self.assertFalse(fixture.snapshot()['connected'])
        self.assertEqual(fixture.tm('list-panes', '-a', '-F', '#{pane_id}'), fixture.origin)

    def test_origin_removal_stops_inner_cli_observer_and_panel(self):
        fixture = self.fixture
        ready = self.launch(['fixture origin removal'])
        pid = ready['pid']
        started = lifecycle.backend.process_start(pid)
        watcher_pid, _ = fixture.wait(lambda: fixture.record_watchers(pid))[0]
        fixture.child('active-on-close')
        fixture.wait(fixture.owned_panels)
        unrelated = fixture.tm('new-window', '-d', '-n', 'unrelated', '-P', '-F', '#{pane_id}',
                               'sleep', '120')
        fixture.tm('kill-pane', '-t', fixture.origin)
        fixture.wait(lambda: lifecycle.backend.process_start(pid) != started)
        fixture.wait(lambda: lifecycle.backend.process_start(watcher_pid) is None)
        fixture.wait(lambda: not fixture.owned_panels())
        self.assertEqual(fixture.tm('list-panes', '-a', '-F', '#{pane_id}'), unrelated)


if __name__ == '__main__':
    unittest.main()
