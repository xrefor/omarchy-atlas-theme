"""Pane-local discovery with daemon-based Codex, without reading UI transcripts."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'components/apps'))
from atlas_agents import backend
from atlas_agents import __main__ as cli

THREAD = '01a0dddf-47d7-79b2-bd0c-e334596a6645'
OTHER = '01a0dddf-481b-7673-908d-196ceda6e897'


class TitleDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        with closing(sqlite3.connect(self.home / 'state_5.sqlite')) as database, database:
            database.executescript('CREATE TABLE threads (id TEXT); CREATE TABLE thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT);')
            database.executemany('INSERT INTO threads VALUES (?)', [(THREAD,), (OTHER,)])
            database.execute('INSERT INTO thread_spawn_edges VALUES (?, ?)', (THREAD, OTHER))

    def test_exact_signal_accepts_root_and_rejects_children_and_arbitrary_uuids(self):
        self.assertEqual(backend.title_root(f'{THREAD} | Codex | Working | project', self.home), THREAD)
        for prefix in ('', '● ', '[ ! ] Action Required | ', '● [ . ] Action Required | '):
            self.assertEqual(backend.title_root(f'{prefix}{THREAD} | Codex ⠋ project', self.home), THREAD)
        for title in (f'project {THREAD}', f'Codex | {THREAD}', f'{OTHER} | Codex',
                      f'{THREAD} | unrelated app', 'Working | Codex | project',
                      '00000000-0000-0000-0000-000000000000 | Codex'):
            with self.subTest(title=title):
                self.assertIsNone(backend.title_root(title, self.home))

    def test_default_title_keeps_original_items_after_routing_prefix(self):
        args, enabled = backend.title_launch_args(['resume', THREAD], self.home)
        self.assertTrue(enabled)
        self.assertEqual(args[:2], ['resume', THREAD])
        self.assertEqual(json.loads(args[-1].split('=', 1)[1]),
                         ['thread-id', 'app-name', 'activity', 'thread-name', 'project-name'])

    def test_actual_abbreviated_title_requires_unique_long_root_prefix(self):
        title = '01a0dddf-47d7-79b2-bd0c-e3345... | codex | Replace repo wallpapers | Work'
        # This is the native TUI's observed 29-character UUID prefix.
        self.assertEqual(backend.title_root(title, self.home), THREAD)
        with closing(sqlite3.connect(self.home / 'state_5.sqlite')) as database, database:
            collision = '01a0dddf-47d7-79b2-bd0c-e3345fffffff'
            database.execute('INSERT INTO threads VALUES (?)', (collision,))
            database.execute('INSERT INTO thread_spawn_edges VALUES (?, ?)', (THREAD, collision))
        self.assertIsNone(backend.title_root(title, self.home))
        self.assertIsNone(backend.title_root('01a0dddf-... | codex', self.home))
        self.assertIsNone(backend.title_root(OTHER[:-6] + '... | codex', self.home))

    def test_profiles_overrides_and_prompt_separator_preserve_user_arguments(self):
        (self.home / 'config.toml').write_text('[tui]\nterminal_title=["model"]\n[profiles.work.tui]\nterminal_title=["project-name"]\n')
        original = ['-p', 'work', '-c', 'model=gpt-6-astra', '--config=tui.terminal_title=["thread-name","session-id"]', '--', 'a prompt']
        args, enabled = backend.title_launch_args(original, self.home)
        self.assertTrue(enabled)
        self.assertEqual(args[-2:], ['--', 'a prompt'])
        self.assertEqual(args[:5], original[:5])
        self.assertEqual(json.loads(args[-3].split('=', 1)[1]), ['thread-id', 'app-name', 'thread-name'])
        profile_args, _ = backend.title_launch_args(['--profile=work'], self.home)
        self.assertEqual(json.loads(profile_args[-1].split('=', 1)[1]), ['thread-id', 'app-name', 'project-name'])

    def test_explicit_disabled_title_and_unreadable_config_are_not_overridden(self):
        for text, arguments in (('[tui]\nterminal_title=[]\n', []),
                                ('', ['-c', 'tui.terminal_title=[]']),
                                ('invalid toml', []), ('tui=3', []), ('profiles=3', []),
                                ('profile=3', []), ('[profiles]\nwork=3', ['-p', 'work'])):
            (self.home / 'config.toml').write_text(text)
            self.assertEqual(backend.title_launch_args(arguments, self.home), (arguments, False))

    def test_project_disabled_title_respects_cd_argument(self):
        project = self.home / 'project'
        (project / '.codex').mkdir(parents=True)
        (project / '.codex/config.toml').write_text('[tui]\nterminal_title=[]\n')
        args = ['--cd', str(project)]
        self.assertEqual(backend.title_launch_args(args, self.home), (args, False))

    def test_launch_clears_stale_title_and_binds_watcher_before_exec(self):
        order = []
        with (patch.object(cli.os, 'isatty', return_value=True),
              patch.dict(os.environ, {'TMUX': 'test,1,0', 'ATLAS_AGENTS_AUTO': '1'}),
              patch.object(cli, 'origin_pane', return_value='%0'),
              patch.object(cli, 'codex_home', return_value=self.home),
              patch.object(cli, 'tmux', side_effect=lambda *a: order.append(('tmux', a))),
              patch.object(cli, 'spawn_watcher', side_effect=lambda *a, **kw: order.append(('watch', a, kw))),
              patch.object(cli.os, 'execv', side_effect=lambda *a: order.append(('exec', a)))):
            cli.launch(['/usr/bin/codex', 'resume', THREAD])
        self.assertEqual(order[0], ('tmux', ('select-pane', '-t', '%0', '-T', '')))
        self.assertEqual(order[1][1], (os.getpid(), '%0'))
        self.assertEqual(order[1][2], {'title_signal': True})
        self.assertIn('tui.terminal_title=', order[2][1][1][-1])

    def test_watcher_tracks_title_changes_and_does_not_use_daemon_files(self):
        args = SimpleNamespace(pane='%0', pid=123, start='456', thread=None, title_signal=True)
        titles = iter((f'{THREAD} | Codex', 'Codex', f'{OTHER} | Codex'))
        snapshots = []
        with closing(sqlite3.connect(self.home / 'state_5.sqlite')) as database, database:
            database.execute('DELETE FROM thread_spawn_edges')
        with (patch.object(cli, 'origin_pane', return_value='%0'),
              patch.object(cli, 'cache_path', return_value=self.home / 'snapshot.json'),
              patch.object(cli, 'codex_home', return_value=self.home),
              patch.object(cli, 'process_start', side_effect=['456', '456', '456', None]),
              patch.object(cli, 'process_root', return_value=None) as legacy,
              patch.object(cli, 'tmux', side_effect=lambda *a: next(titles) if a[-1] == '#{pane_title}' else '%0'),
              patch.object(cli, 'write_cache', side_effect=lambda p, s: snapshots.append(dict(s))),
              patch.object(cli.time, 'sleep'), patch.object(cli.signal, 'signal'),
              patch.object(cli, 'Observer') as observer, patch.object(cli, 'Panels') as panels):
            panels.return_value.existing.return_value = []
            observer.return_value.poll.return_value = {'root_id': THREAD, 'connected': True, 'agents': [], 'updated_at': 1}
            cli.watch(args)
            self.assertEqual([c.args[0] for c in observer.call_args_list], [THREAD, OTHER])
            legacy.assert_called_once_with(123, self.home)
        self.assertTrue(snapshots[0]['connected'])
        self.assertFalse(snapshots[1]['connected'])
        self.assertTrue(all(snapshot['title_signal'] for snapshot in snapshots))

    def test_restart_recovers_title_signal_only_for_matching_process_identity(self):
        for key, enabled in (('123:456', True), ('123:455', False), ('122:456', False)):
            with (self.subTest(key=key),
                    patch.object(cli, 'process_start', return_value='456'),
                    patch.object(cli, 'cache_path', return_value=self.home / 'snapshot.json'),
                    patch.object(cli, 'read_cache', return_value={'session_key': key, 'title_signal': True}),
                    patch.object(cli, 'write_cache') as write,
                    patch.object(cli.subprocess, 'Popen') as spawn):
                cli.spawn_watcher(123, '%0', THREAD)
                arguments = spawn.call_args.args[0]
                self.assertEqual('--title-signal' in arguments, enabled)
                self.assertEqual(arguments[arguments.index('--thread') + 1], THREAD)
                self.assertEqual(write.call_args.args[1]['session_key'], '123:456')

    def test_title_database_failure_marks_watcher_unavailable_instead_of_exiting(self):
        args = SimpleNamespace(pane='%0', pid=123, start='456', thread=None, title_signal=True)
        snapshots = []
        with (patch.object(cli, 'origin_pane', return_value='%0'),
              patch.object(cli, 'cache_path', return_value=self.home / 'snapshot.json'),
              patch.object(cli, 'process_start', side_effect=['456', None]),
              patch.object(cli, 'title_root', side_effect=sqlite3.OperationalError('database is locked')),
              patch.object(cli, 'tmux', return_value='%0'),
              patch.object(cli, 'write_cache', side_effect=lambda p, s: snapshots.append(dict(s))),
              patch.object(cli.time, 'sleep'), patch.object(cli.signal, 'signal'),
              patch.object(cli, 'Panels')):
            self.assertEqual(cli.watch(args), 0)
        self.assertFalse(snapshots[0]['connected'])
        self.assertEqual(snapshots[0]['error'], 'database is locked')

    def test_manual_process_selection_excludes_shared_daemons(self):
        # Real /proc reads are replaced with a process tree: two daemon children
        # under our client and a second client rooted in another pane.
        entries = {10: (1, 'bash', b'bash\0'), 20: (10, 'codex', b'codex\0'),
                   21: (20, 'codex', b'codex\0app-server\0daemon\0'),
                   22: (20, 'codex', b'codex\0app-server\0daemon\0update-loop\0'),
                   30: (1, 'codex', b'codex\0')}
        real_read_text = Path.read_text
        real_read_bytes = Path.read_bytes
        real_iterdir = Path.iterdir
        def read_text(path, *a, **kw):
            if str(path).startswith('/proc/') and path.name == 'stat':
                pid = int(path.parent.name)
                return f'{pid} ({entries[pid][1]}) S {entries[pid][0]} 0 0'
            return real_read_text(path, *a, **kw)
        def read_bytes(path):
            if str(path).startswith('/proc/') and path.name == 'cmdline':
                return entries[int(path.parent.name)][2]
            return real_read_bytes(path)
        def iterdir(path):
            if str(path) == '/proc': return iter(Path('/proc') / str(pid) for pid in entries)
            return real_iterdir(path)
        with (patch.object(cli, 'tmux', return_value='10'), patch.object(Path, 'read_text', read_text),
              patch.object(Path, 'read_bytes', read_bytes), patch.object(Path, 'iterdir', iterdir),
              patch.object(os, 'readlink', side_effect=lambda p: '/usr/bin/' + entries[int(p.parent.name)][1])):
            self.assertEqual(cli.codex_process('%0'), 20)
            entries[25] = (10, 'codex', b'codex\0')
            with self.assertRaisesRegex(ValueError, 'Multiple Codex processes'):
                cli.codex_process('%0')


if __name__ == '__main__':
    unittest.main()
