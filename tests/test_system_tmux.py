import tempfile
import unittest
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_system.tmux_panel import Panel
from atlas_system.__main__ import origin_pane


class FakePanel(Panel):
    def __init__(self, width='160'):
        self.calls = []
        self.width = width
        self.panes = []
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas-system-tmux-')
        super().__init__('%7', ['/path with spaces/atlas-system', 'show'],
                         runtime_dir=self.temporary.name)

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
        return ''

    def cleanup(self):
        self.temporary.cleanup()


class SystemTmuxTests(unittest.TestCase):
    def test_wide_origin_opens_detached_literal_sidebar(self):
        panel = FakePanel()
        try:
            self.assertEqual(panel.open(), '%9')
            split = next(call for call in panel.calls if call[0] == 'split-window')
            self.assertIn('-d', split)
            self.assertEqual(split[-3:], ('--', '/path with spaces/atlas-system', 'show'))
            self.assertIn(('set-option', '-p', '-t', '%9', '@atlas_system_origin', '%7'), panel.calls)
        finally:
            panel.cleanup()

    def test_narrow_origin_uses_separate_window_and_toggle_closes(self):
        panel = FakePanel('100')
        try:
            self.assertEqual(panel.toggle(), 'opened')
            self.assertTrue(any(call[0] == 'new-window' for call in panel.calls))
            self.assertEqual(panel.toggle(), 'closed')
            self.assertEqual(panel.panes, [])
        finally:
            panel.cleanup()

    def test_rejects_invalid_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                Panel('session:1', ['atlas-system'], runtime_dir=directory)

    @mock.patch.dict('os.environ', {'TMUX': '/tmp/tmux,1,0', 'TMUX_PANE': '%9'}, clear=False)
    @mock.patch('atlas_system.__main__.subprocess.check_output', return_value='%9\t%7\n')
    def test_focused_panel_resolves_original_pane(self, check_output):
        self.assertEqual(origin_pane(None), '%7')
        self.assertEqual(check_output.call_args.args[0][-1],
                         '#{pane_id}\t#{@atlas_system_origin}')


if __name__ == '__main__':
    unittest.main()
