import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_maintain.tmux_panel import Panel
from atlas_maintain import __main__ as maintain_main


class FakePanel(Panel):
    def __init__(self, width='160'):
        self.calls = []
        self.width = width
        self.panes = []
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas-maintain-tmux-')
        super().__init__('%7', ['/path with spaces/atlas-maintain', 'show'],
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


class MaintainTmuxTests(unittest.TestCase):
    def test_toggle_from_focused_panel_normalizes_to_its_origin(self):
        with patch.dict(os.environ, {'TMUX': '/tmp/tmux,1,0', 'TMUX_PANE': '%9'}), \
                patch.object(maintain_main, '_tmux', return_value='%9\t%7'):
            self.assertEqual(maintain_main.origin_pane(None), '%7')

    def test_wide_origin_opens_detached_literal_sidebar(self):
        panel = FakePanel()
        try:
            self.assertEqual(panel.open(), '%9')
            split = next(call for call in panel.calls if call[0] == 'split-window')
            self.assertIn('-d', split)
            self.assertEqual(split[-3:], ('--', '/path with spaces/atlas-maintain', 'show'))
            self.assertIn(('set-option', '-p', '-t', '%9', '@atlas_maintain_origin', '%7'),
                          panel.calls)
        finally:
            panel.cleanup()

    def test_48_column_sidebar_and_narrow_window(self):
        sidebar = FakePanel('130')
        narrow = FakePanel('100')
        try:
            sidebar.open()
            split = next(call for call in sidebar.calls if call[0] == 'split-window')
            self.assertEqual(split[split.index('-l') + 1], '48')
            narrow.open()
            self.assertTrue(any(call[0] == 'new-window' for call in narrow.calls))
        finally:
            sidebar.cleanup()
            narrow.cleanup()

    def test_toggle_closes_owned_pane_and_rejects_invalid_origin(self):
        panel = FakePanel()
        try:
            self.assertEqual(panel.toggle(), 'opened')
            self.assertEqual(panel.toggle(), 'closed')
            self.assertEqual(panel.panes, [])
        finally:
            panel.cleanup()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                Panel('session:1', ['atlas-maintain'], runtime_dir=directory)


if __name__ == '__main__':
    unittest.main()
