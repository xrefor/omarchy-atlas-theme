"""Exercise launch and observation with fake Codex state in disposable tmux."""
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'components/apps'))
from atlas_agents import __main__ as cli
from atlas_agents import backend

LAUNCHER = ROOT / 'components/apps/bin/atlas-agents'


def encoded(value):
    return json.dumps(value) + '\n'


class SnapshotTests(unittest.TestCase):
    def test_explicit_thread_watcher_remains_pinned(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = SimpleNamespace(pane='%1', pid=123, start='456', thread='selected')
            with (patch.object(cli, 'origin_pane', return_value='%1'),
                  patch.object(cli, 'cache_path', return_value=Path(temporary) / 'snapshot.json'),
                  patch.object(cli, 'process_start', side_effect=['456', '456', None]),
                  patch.object(cli, 'process_root') as discover,
                  patch.object(cli, 'Observer') as observer,
                  patch.object(cli, 'tmux', return_value='%1'),
                  patch.object(cli, 'write_cache'), patch.object(cli.time, 'sleep'),
                  patch.object(cli.signal, 'signal'), patch.object(cli, 'Panels') as panels):
                observer.return_value.root_id = 'selected'
                observer.return_value.poll.return_value = {
                    'root_id': 'selected', 'connected': True, 'agents': [], 'updated_at': 1}
                panels.return_value.existing.return_value = []
                cli.watch(args)
                discover.assert_not_called()
                observer.assert_called_once_with('selected')

    def test_watcher_closes_panel_even_when_final_snapshot_write_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'snapshot.json'
            args = SimpleNamespace(pane='%1', pid=123, start='456', thread=None)
            with (patch.object(cli, 'origin_pane', return_value='%1'),
                  patch.object(cli, 'cache_path', return_value=path),
                  patch.object(cli, 'process_start', return_value=None),
                  patch.object(cli.signal, 'signal'),
                  patch.object(cli, 'Panels') as panels,
                  patch.object(cli, 'write_cache', side_effect=OSError('disk full'))):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    cli.watch(args)
                panels.return_value.close.assert_called_once_with()

    def test_corrupt_or_unreadable_dismissal_marker_does_not_hide_new_activity(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {'XDG_RUNTIME_DIR': temporary}):
                path = cli.runtime_directory() / 'snapshot.json'
                marker = path.with_suffix('.dismissed')
                cli.dismiss(path, {'session_key': '123:456'})
                self.assertTrue(cli.is_dismissed(path, '123:456'))
                self.assertFalse(cli.is_dismissed(path, '123:789'))
                marker.write_text('{invalid json')
                self.assertFalse(cli.is_dismissed(path, '123:456'))
                cli.dismiss(path, {'session_key': '123:456'})
                marker.chmod(0o644)
                self.assertFalse(cli.is_dismissed(path, '123:456'))
                marker.unlink()
                marker.symlink_to(path)
                self.assertFalse(cli.is_dismissed(path, '123:456'))

    def test_snapshot_is_private_and_symlink_cannot_redirect_reads_or_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {'XDG_RUNTIME_DIR': temporary}):
                path = cli.runtime_directory() / 'snapshot.json'
                cli.write_cache(path, {'agents': []})
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(cli.read_cache(path), {'agents': []})
                target = Path(temporary) / 'keep.json'
                target.write_text('untouched')
                path.unlink()
                path.symlink_to(target)
                with self.assertRaises(OSError):
                    cli.read_cache(path)
                cli.write_cache(path, {'agents': ['replacement']})
                self.assertFalse(path.is_symlink())
                self.assertEqual(target.read_text(), 'untouched')
                self.assertEqual(cli.read_cache(path), {'agents': ['replacement']})


@unittest.skipUnless(shutil.which('tmux'), 'tmux is not installed')
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas-agents-lifecycle-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / 'codex home #1?'
        (self.home / 'sessions').mkdir(parents=True)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.socket = self.root / 'tmux.sock'
        self.addCleanup(lambda: subprocess.run(
            ['tmux', '-S', str(self.socket), 'kill-server'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        try:
            self.tm('-f', '/dev/null', 'new-session', '-d', '-s', 'test',
                    '-x', '180', '-y', '35', 'sleep', '120')
        except subprocess.CalledProcessError as error:
            if any(text in (error.output or '') for text in ('Operation not permitted', 'Permission denied')):
                self.skipTest('sandbox does not allow a temporary tmux socket')
            raise
        self.origin = self.tm('display-message', '-p', '#{pane_id}')
        self.environment = dict(os.environ, HOME=str(self.root), CODEX_HOME=str(self.home),
                                XDG_RUNTIME_DIR=str(self.runtime), ATLAS_AGENTS_AUTO='1',
                                PYTHONDONTWRITEBYTECODE='1',
                                TMUX=f'{self.socket},{self.tm("display-message", "-p", "#{pid}")},0',
                                TMUX_PANE=self.origin)
        for name in ('HOME', 'CODEX_HOME', 'XDG_RUNTIME_DIR', 'ATLAS_AGENTS_AUTO', 'PYTHONDONTWRITEBYTECODE'):
            self.tm('set-environment', '-g', name, self.environment[name])
        self.database = self.home / 'state_5.sqlite'
        self.rollout = self.home / 'sessions/root.jsonl'
        self.rollout.write_text(encoded({'type': 'session_meta', 'payload': {'id': 'root', 'source': 'cli'}}))
        with sqlite3.connect(self.database) as database:
            database.executescript('''
                CREATE TABLE threads (id TEXT PRIMARY KEY, rollout_path TEXT, agent_path TEXT,
                    agent_nickname TEXT, agent_role TEXT, created_at INTEGER, history_mode TEXT);
                CREATE TABLE thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT, status TEXT);
            ''')
            database.execute('INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?)',
                             ('root', str(self.rollout), '/root', '', '', int(time.time()), 'paginated'))
        self.fake = self.root / 'fake cli #{pane_id}.py'
        self.ready = self.root / 'ready.json'
        self.exit_request = self.root / 'exit-request'
        self.exit_status = self.root / 'exit-status'
        self.fake.write_text('#!' + sys.executable + '\n' + '''import json, os, pathlib, sys, time
root = pathlib.Path(os.environ['HOME'])
rollout = open(pathlib.Path(os.environ['CODEX_HOME']) / 'sessions/root.jsonl')
(root / 'ready.json').write_text(json.dumps({'pid': os.getpid(), 'args': sys.argv[1:]}))
while not (root / 'exit-request').exists():
    time.sleep(.025)
sys.exit(int((root / 'exit-request').read_text()))
''')
        self.fake.chmod(0o700)
        with patch.dict(os.environ, self.environment):
            self.snapshot_path = cli.cache_path(self.origin)
        self.watchers = {}
        self.addCleanup(self.stop_watchers)

    def tm(self, *args):
        return subprocess.check_output(['tmux', '-S', str(self.socket), *args],
                                       text=True, stderr=subprocess.STDOUT).strip()

    def wait(self, condition, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = condition()
            if value:
                return value
            time.sleep(.04)
        self.fail('Timed out waiting for the fake Codex lifecycle')

    def snapshot(self):
        try:
            return json.loads(self.snapshot_path.read_text())
        except (OSError, ValueError):
            return {}

    def owned_panels(self):
        rows = self.tm('list-panes', '-a', '-F', '#{pane_id} #{@atlas_agents_origin}')
        return [row.split()[0] for row in rows.splitlines() if row.endswith(' ' + self.origin)]

    def launch(self, args):
        invocation = [sys.executable, str(LAUNCHER), 'launch', '--', str(self.fake), *args]
        script = (shlex.join(invocation) + '; status=$?; printf "%s" "$status" > '
                  + shlex.quote(str(self.exit_status)) + '; exec sleep 90')
        self.tm('respawn-pane', '-k', '-t', self.origin, 'bash', '-c', script)
        self.wait(self.ready.exists)
        return json.loads(self.ready.read_text())

    def record_watchers(self, pid):
        try:
            children = (Path('/proc') / str(pid) / 'task' / str(pid) / 'children').read_text().split()
        except OSError:
            return []
        result = []
        for child in children:
            try:
                argv = (Path('/proc') / child / 'cmdline').read_bytes().decode().split('\0')
            except OSError:
                continue
            if str(LAUNCHER) in argv and 'watch' in argv:
                identifier = int(child)
                self.watchers[identifier] = backend.process_start(identifier)
                result.append((identifier, argv))
        return result

    def stop_watchers(self):
        for pid, started in self.watchers.items():
            if started is not None and backend.process_start(pid) == started:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        # Watchers are detached; allow their final cache write before fixture cleanup.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if all(backend.process_start(pid) != started for pid, started in self.watchers.items()):
                break
            time.sleep(.025)

    def child(self, identifier, parent='root', *, boundary=True):
        path = self.home / 'sessions' / f'{identifier}.jsonl'
        metadata = {'id': identifier, 'parent_thread_id': parent}
        if boundary:
            metadata['subagent_history_start_ordinal'] = 0
        path.write_text(encoded({'type': 'session_meta', 'payload': metadata}))
        self.append(path, 'task_started', turn_id=identifier, started_at=time.time())
        with sqlite3.connect(self.database) as database:
            database.execute('INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?)',
                             (identifier, str(path), '/root/' + identifier, '', 'worker',
                              int(time.time()), 'paginated'))
            database.execute('INSERT INTO thread_spawn_edges VALUES (?, ?, ?)', (parent, identifier, 'open'))
        return path

    def append(self, path, detail, **fields):
        with path.open('a') as output:
            output.write(encoded({'type': 'event_msg', 'timestamp': time.time(),
                                  'payload': dict(type=detail, **fields)}))

    def test_launch_auto_open_dismissal_and_process_exit(self):
        args = ['--model', 'fake-model', 'prompt with spaces #{} $(literal)']
        ready = self.launch(args)
        pid = ready['pid']
        self.assertEqual(ready['args'], args)
        started = backend.process_start(pid)
        self.assertEqual(backend.process_root(pid, self.home), 'root')
        observed = self.wait(lambda: self.snapshot().get('connected') and self.snapshot())
        self.assertEqual(observed['session_key'], f'{pid}:{started}')
        self.assertEqual(observed['root_id'], 'root')
        self.assertEqual(observed['agents'], [])
        self.assertEqual(self.owned_panels(), [])
        watchers = self.wait(lambda: self.record_watchers(pid))
        self.assertEqual(len(watchers), 1)
        watcher_pid, argv = watchers[0]
        self.assertEqual(argv[argv.index('--pid') + 1], str(pid))
        self.assertEqual(argv[argv.index('--start') + 1], started)

        child = self.child('first-child', boundary=False)
        pane = self.wait(lambda: self.owned_panels())[0]
        self.wait(lambda: len(self.snapshot().get('agents', [])) == 1)
        self.assertEqual(self.snapshot()['agents'][0]['status'], 'running')
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)
        duplicate = subprocess.run(
            [sys.executable, str(LAUNCHER), 'watch', '--pid', str(pid), '--start', started,
             '--pane', self.origin], env=self.environment, capture_output=True, text=True, timeout=4)
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertEqual(self.owned_panels(), [pane])

        self.append(child, 'task_complete', turn_id='first-child', completed_at=time.time())
        self.wait(lambda: self.snapshot().get('agents', [{}])[0].get('status') == 'completed')
        self.tm('kill-pane', '-t', pane)
        dismissed = self.snapshot_path.with_suffix('.dismissed')
        self.wait(dismissed.exists)
        self.assertEqual(json.loads(dismissed.read_text())['session_key'], f'{pid}:{started}')
        self.child('second-child')
        threshold = time.time() + 1
        self.wait(lambda: len(self.snapshot().get('agents', [])) == 2
                  and self.snapshot().get('updated_at', 0) > threshold)
        self.assertEqual(self.owned_panels(), [])
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)

        self.exit_request.write_text('17')
        self.wait(self.exit_status.exists)
        self.assertEqual(self.exit_status.read_text(), '17')
        self.wait(lambda: backend.process_start(watcher_pid) is None)
        final = self.snapshot()
        self.assertFalse(final['connected'])
        self.assertIn('session ended', final['error'])
        self.assertEqual({row['id']: row['status'] for row in final['agents']},
                         {'first-child': 'completed', 'second-child': 'unknown'})
        self.assertEqual(self.snapshot_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.owned_panels(), [])

    def check_exit_closes_open_panel(self, width):
        self.tm('resize-window', '-t', 'test:0', '-x', str(width), '-y', '35')
        ready = self.launch(['exit with an open panel'])
        watcher = self.wait(lambda: self.record_watchers(ready['pid']))[0][0]
        self.child('active-at-exit')
        pane = self.wait(lambda: self.owned_panels())[0]
        origin_window = self.tm('display-message', '-p', '-t', self.origin, '#{window_id}')
        panel_window = self.tm('display-message', '-p', '-t', pane, '#{window_id}')
        self.assertEqual(panel_window == origin_window, width >= 130)

        self.exit_request.write_text('17')
        self.wait(self.exit_status.exists)
        self.wait(lambda: backend.process_start(watcher) is None)
        self.assertEqual(self.exit_status.read_text(), '17')
        self.assertEqual(self.owned_panels(), [])
        self.assertEqual(self.tm('display-message', '-p', '-t', self.origin, '#{pane_id}'), self.origin)
        self.assertEqual(len(self.tm('list-windows').splitlines()), 1)
        self.assertFalse(self.snapshot()['connected'])
        self.assertEqual(self.snapshot()['agents'][0]['status'], 'unknown')

    def test_exit_closes_open_side_panel(self):
        self.check_exit_closes_open_panel(180)

    def test_exit_closes_open_panel_window(self):
        self.check_exit_closes_open_panel(100)

    def test_conversation_switch_updates_lineage_and_marks_missing_root_stale(self):
        # Model /new and /resume by changing the open rollout in the same CLI
        # process, including an interval when no root rollout is open.
        self.fake.write_text(self.fake.read_text().replace(
            '    time.sleep(.025)', '''    selection = root / 'select-root'
    if selection.exists():
        target = selection.read_text()
        selection.unlink()
        if rollout is not None:
            rollout.close()
        rollout = open(target) if target else None
    time.sleep(.025)'''))
        second = self.home / 'sessions/second-root.jsonl'
        second.write_text(encoded({'type': 'session_meta', 'payload': {'id': 'second-root', 'source': 'cli'}}))
        with sqlite3.connect(self.database) as database:
            database.execute('INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?)',
                             ('second-root', str(second), '/root', '', '', int(time.time()), 'paginated'))
        with patch.dict(os.environ, self.environment):
            cli.write_cache(self.snapshot_path.with_suffix('.thread'),
                            {'session_key': 'previous-launch', 'thread': 'second-root'})
        ready = self.launch(['switch conversation'])
        self.wait(lambda: self.record_watchers(ready['pid']))
        self.child('first-only')
        first_panel = self.wait(lambda: self.owned_panels())[0]
        key = self.snapshot()['session_key']

        selection = self.root / 'select-root'
        selection.write_text('')
        self.wait(lambda: not self.snapshot().get('connected')
                  and 'current Codex conversation' in self.snapshot().get('error', ''))
        self.assertEqual(self.snapshot()['root_id'], 'root')
        self.assertEqual(self.owned_panels(), [first_panel])

        self.child('second-only', parent='second-root')
        selection.write_text(str(second))
        self.wait(lambda: self.snapshot().get('root_id') == 'second-root'
                  and self.snapshot().get('connected'))
        self.wait(lambda: self.owned_panels() and first_panel not in self.owned_panels())
        self.assertEqual([row['id'] for row in self.snapshot()['agents']], ['second-only'])
        self.assertEqual(self.snapshot()['session_key'], key)
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)

        selection.write_text(str(self.rollout))
        self.wait(lambda: self.snapshot().get('root_id') == 'root'
                  and self.snapshot().get('connected'))
        self.wait(lambda: f'{self.origin}\troot' in self.tm(
            'list-panes', '-a', '-F', '#{@atlas_agents_origin}\t#{@atlas_agents_thread}').splitlines())
        self.assertEqual([row['id'] for row in self.snapshot()['agents']], ['first-only'])
        self.assertEqual(len(self.owned_panels()), 1)

        # Explicit attach must reach the existing observer despite its same-PID
        # duplicate lock. Only process discovery is mocked: the fixture binary
        # is Python, while discovery deliberately requires the Codex executable.
        with (patch.dict(os.environ, self.environment),
              patch.object(cli, 'codex_process', return_value=ready['pid'])):
            cli.attach(SimpleNamespace(pane=self.origin, thread='second-root'))
        threshold = time.time() + 1
        self.wait(lambda: self.snapshot().get('root_id') == 'second-root'
                  and self.snapshot().get('updated_at', 0) > threshold)
        self.assertEqual(backend.process_root(ready['pid'], self.home), 'root')
        self.assertEqual([row['id'] for row in self.snapshot()['agents']], ['second-only'])
        self.assertEqual(self.snapshot()['session_key'], key)
        self.assertEqual(self.snapshot_path.with_suffix('.thread').stat().st_mode & 0o777, 0o600)

    def test_origin_pane_removal_closes_panel_and_preserves_unrelated_pane(self):
        # A child can outlive the pane's hangup; pane ownership must still end.
        self.fake.write_text(self.fake.read_text().replace(
            'root = pathlib.Path',
            'import signal\nsignal.signal(signal.SIGHUP, signal.SIG_IGN)\nroot = pathlib.Path', 1))
        ready = self.launch(['close the originating terminal pane'])
        started = backend.process_start(ready['pid'])
        def stop_surviving_cli():
            if backend.process_start(ready['pid']) == started:
                try:
                    os.kill(ready['pid'], signal.SIGTERM)
                except ProcessLookupError:
                    pass
        self.addCleanup(stop_surviving_cli)
        watcher = self.wait(lambda: self.record_watchers(ready['pid']))[0][0]
        self.child('active-at-close')
        self.wait(lambda: self.owned_panels())
        unrelated = self.tm('new-window', '-d', '-n', 'unrelated', '-P', '-F', '#{pane_id}',
                            'sleep', '120')
        self.tm('set-option', '-p', '-t', unrelated, '@atlas_agents_origin', '%99999')
        self.tm('kill-pane', '-t', self.origin)

        self.wait(lambda: backend.process_start(watcher) is None)
        self.assertEqual(backend.process_start(ready['pid']), started)
        self.assertEqual(self.owned_panels(), [])
        self.assertEqual(self.tm('list-panes', '-a', '-F', '#{pane_id}'), unrelated)
        self.assertFalse(self.snapshot()['connected'])

    def test_utility_launches_bypass_watcher_and_preserve_exit_status(self):
        self.exit_request.write_text('23')
        for args in (['--help'], ['exec', 'a prompt with spaces']):
            with self.subTest(args=args):
                self.ready.unlink(missing_ok=True)
                self.exit_status.unlink(missing_ok=True)
                ready = self.launch(args)
                self.wait(self.exit_status.exists)
                self.assertEqual(ready['args'], args)
                self.assertEqual(self.exit_status.read_text(), '23')
                self.assertFalse(self.snapshot_path.exists())
                self.assertFalse(self.snapshot_path.with_suffix('.watch.lock').exists())
                self.assertEqual(self.owned_panels(), [])

    def test_quick_relaunch_waits_for_previous_watcher_lock_then_observes_new_process(self):
        first = self.launch(['first launch'])
        self.wait(lambda: self.snapshot().get('connected'))
        old_watcher = self.wait(lambda: self.record_watchers(first['pid']))[0][0]
        old_start = backend.process_start(old_watcher)
        old_key = self.snapshot()['session_key']
        self.child('before-relaunch')
        old_panel = self.wait(lambda: self.owned_panels())[0]
        lock_path = self.snapshot_path.with_suffix('.watch.lock')
        self.assertEqual(lock_path.read_text(), old_key)

        # Pause the previous observer while it owns the lock, making the otherwise
        # timing-sensitive exit/relaunch overlap deterministic and short.
        os.kill(old_watcher, signal.SIGSTOP)
        def resume_old_watcher():
            if backend.process_start(old_watcher) == old_start:
                try:
                    os.kill(old_watcher, signal.SIGCONT)
                except ProcessLookupError:
                    pass
        self.addCleanup(resume_old_watcher)
        self.exit_request.write_text('7')
        self.wait(self.exit_status.exists)
        self.assertEqual(self.exit_status.read_text(), '7')
        for path in (self.ready, self.exit_request, self.exit_status):
            path.unlink()
        second = self.launch(['second launch'])
        new_key = f'{second["pid"]}:{backend.process_start(second["pid"])}'
        self.assertNotEqual(new_key, old_key)
        new_watcher = self.wait(lambda: self.record_watchers(second['pid']))[0][0]
        time.sleep(.2)
        self.assertIsNotNone(backend.process_start(new_watcher), 'Replacement observer exited instead of waiting')
        self.assertEqual(lock_path.read_text(), old_key)
        resume_old_watcher()

        self.wait(lambda: self.snapshot().get('session_key') == new_key
                  and self.snapshot().get('connected'))
        self.wait(lambda: backend.process_start(old_watcher) is None)
        self.assertNotIn(old_panel, self.owned_panels())
        self.assertEqual(lock_path.read_text(), new_key)
        self.assertEqual(self.snapshot()['cli_pid'], second['pid'])
        self.child('after-relaunch')
        self.wait(lambda: self.owned_panels())
        self.assertEqual(len(self.owned_panels()), 1)
        self.assertEqual(self.tm('display-message', '-p', '#{pane_id}'), self.origin)
        self.exit_request.write_text('19')
        self.wait(self.exit_status.exists)
        self.assertEqual(self.exit_status.read_text(), '19')
        self.wait(lambda: backend.process_start(new_watcher) is None)
        self.assertEqual(self.snapshot()['session_key'], new_key)
        self.assertFalse(self.snapshot()['connected'])
        self.assertEqual(self.owned_panels(), [])


if __name__ == '__main__':
    unittest.main()
