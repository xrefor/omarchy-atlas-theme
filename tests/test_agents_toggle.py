"""Manual agent toggles handle an empty or still-starting local conversation."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'components/apps'))
from atlas_agents import __main__ as cli


class AgentsToggleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='atlas-agents-toggle-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'snapshot.json'
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)

        def mocked(name, **kwargs):
            return self.stack.enter_context(patch.object(cli, name, **kwargs))

        mocked('runtime_directory', return_value=self.directory)
        mocked('cache_path', return_value=self.path)
        mocked('origin_pane', return_value='%0')
        self.panels = mocked('Panels').return_value
        self.panels.existing.return_value = []
        self.process = mocked('codex_process', side_effect=cli.NoCodexProcess('Open Codex'))
        mocked('process_start', return_value='456')
        self.root = mocked('process_root', return_value=None)
        self.watcher = mocked('spawn_watcher')
        self.tmux = mocked('tmux')
        self.observer = mocked('Observer')
        self.observer.return_value.poll.return_value = {'root_id': 'ready-thread', 'agents': []}

    def active(self):
        self.process.side_effect = None
        self.process.return_value = 123

    def snapshot(self, root='', key='123:456'):
        cli.write_cache(self.path, {'root_id': root, 'session_key': key, 'agents': []})

    def invoke(self, action='toggle'):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            result = cli.main([action, '--pane', '%0'])
        return result, errors.getvalue()

    def assert_notice(self, text):
        self.assertEqual(self.invoke(), (0, ''))
        self.tmux.assert_called_once()
        args = self.tmux.call_args.args
        self.assertEqual(args[:3], ('display-message', '-t', '%0'))
        self.assertIn(text, args[3])
        self.panels.open.assert_not_called()

    def test_fresh_shell_without_snapshot_explains_how_to_start(self):
        self.assert_notice('Open Codex in this pane')
        self.watcher.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_finished_startup_without_thread_explains_how_to_start(self):
        self.snapshot()
        self.assert_notice('Open Codex in this pane')
        self.watcher.assert_not_called()

    def test_active_startup_snapshot_waits_and_keeps_observation_running(self):
        self.active()
        self.snapshot()
        self.assert_notice('Waiting for Codex to open its conversation')
        self.watcher.assert_called_once_with(123, '%0', None)

    def test_active_process_without_snapshot_waits_and_starts_observation(self):
        self.active()
        self.assert_notice('Waiting for Codex to open its conversation')
        self.watcher.assert_called_once_with(123, '%0', None)
        self.assertFalse(self.path.exists(), 'Waiting must not fabricate a conversation')

    def test_new_process_does_not_open_previous_conversation_while_starting(self):
        self.active()
        self.snapshot('old-thread', key='122:455')
        self.assert_notice('Waiting for Codex to open its conversation')
        self.watcher.assert_called_once_with(123, '%0', None)

    def test_active_ready_snapshot_opens_and_clears_dismissal(self):
        self.active()
        self.snapshot('ready-thread')
        cli.dismiss(self.path, cli.read_cache(self.path))
        self.assertEqual(self.invoke(), (0, ''))
        self.panels.open.assert_called_once_with('ready-thread', str(self.path))
        self.watcher.assert_called_once_with(123, '%0', None)
        self.assertFalse(self.path.with_suffix('.dismissed').exists())
        self.tmux.assert_not_called()

    def test_active_ready_conversation_attaches_without_existing_snapshot(self):
        self.active()
        self.root.return_value = 'ready-thread'
        self.assertEqual(self.invoke(), (0, ''))
        self.panels.open.assert_called_once_with('ready-thread', str(self.path))
        self.watcher.assert_called_once_with(123, '%0', None)
        self.assertEqual(cli.read_cache(self.path)['session_key'], '123:456')

    def test_completed_summary_reopens_without_codex(self):
        self.snapshot('completed-thread')
        self.assertEqual(self.invoke(), (0, ''))
        self.panels.open.assert_called_once_with('completed-thread', str(self.path))
        self.watcher.assert_not_called()
        self.tmux.assert_not_called()

    def test_open_panel_closes_and_records_dismissal(self):
        self.snapshot('ready-thread')
        self.panels.existing.return_value = ['%1']
        self.assertEqual(self.invoke(), (0, ''))
        self.panels.close.assert_called_once_with()
        self.assertTrue(cli.is_dismissed(self.path, '123:456'))
        self.process.assert_not_called()
        self.panels.open.assert_not_called()

    def test_ambiguous_process_is_not_treated_as_empty(self):
        self.snapshot('old-thread')
        self.process.side_effect = ValueError('Multiple Codex processes')
        result, errors = self.invoke()
        self.assertEqual(result, 1)
        self.assertIn('Multiple Codex processes', errors)
        self.panels.open.assert_not_called()
        self.tmux.assert_not_called()

    def test_ambiguous_conversation_is_not_treated_as_startup(self):
        self.active()
        self.root.side_effect = ValueError('Multiple open Codex conversations')
        result, errors = self.invoke()
        self.assertEqual(result, 1)
        self.assertIn('Multiple open Codex conversations', errors)
        self.watcher.assert_not_called()
        self.panels.open.assert_not_called()
        self.tmux.assert_not_called()

    def test_unsafe_cache_is_not_treated_as_empty(self):
        self.snapshot()
        self.path.chmod(0o644)
        result, errors = self.invoke()
        self.assertEqual(result, 1)
        self.assertIn('not a private regular file', errors)
        self.panels.open.assert_not_called()
        self.tmux.assert_not_called()

    def test_explicit_attach_during_startup_starts_observation(self):
        self.active()
        self.assertEqual(self.invoke('attach'), (0, ''))
        self.watcher.assert_called_once_with(123, '%0', None)
        self.assertIn('Waiting for Codex', self.tmux.call_args.args[-1])
        self.panels.open.assert_not_called()


if __name__ == '__main__':
    unittest.main()
