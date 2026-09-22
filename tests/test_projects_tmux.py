"""Projects panel tmux ownership and literal project-path execution."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_projects import __main__ as command
from atlas_projects.tmux_panel import Panel


class FakePanel(Panel):
    def __init__(self, width='160', current_path='/tmp/project $(touch nope) #{pane_id}'):
        self.calls = []
        self.width = width
        self.current_path = current_path
        self.panes = []
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas-projects-tmux-')
        super().__init__('%7', ['/path with spaces/atlas-projects', 'show'],
                         runtime_dir=self.temporary.name)

    def _tmux(self, *arguments):
        self.calls.append(arguments)
        if arguments[0] == 'list-panes':
            return '\n'.join(f'{pane}\t%7' for pane in self.panes)
        if arguments[0] == 'display-message':
            return (self.current_path if arguments[-1] == '#{pane_current_path}'
                    else f'%7\t$1\t{self.width}')
        if arguments[0] in ('split-window', 'new-window'):
            self.panes.append('%9')
            return '%9'
        if arguments[0] == 'kill-pane':
            self.panes.remove(arguments[-1])
        return ''

    def cleanup(self):
        self.temporary.cleanup()


class ProjectsTmuxTests(unittest.TestCase):
    def panel(self, *arguments, **keywords):
        panel = FakePanel(*arguments, **keywords)
        self.addCleanup(panel.cleanup)
        return panel

    def test_wide_origin_opens_detached_literal_sidebar(self):
        literal = '/tmp/project $(touch nope) #{pane_id} with spaces'
        panel = self.panel(current_path=literal)
        self.assertEqual(panel.open(), '%9')
        split = next(call for call in panel.calls if call[0] == 'split-window')
        self.assertIn('-d', split)
        self.assertEqual(split[split.index('-l') + 1], '60')
        self.assertEqual(split[-5:], ('--', '/path with spaces/atlas-projects',
                                     'show', '--path', literal))
        self.assertIn(('set-option', '-p', '-t', '%9',
                       '@atlas_projects_origin', '%7'), panel.calls)

    def test_medium_and_narrow_origins_use_shared_width_policy(self):
        medium = self.panel('135')
        medium.open()
        split = next(call for call in medium.calls if call[0] == 'split-window')
        self.assertEqual(split[split.index('-l') + 1], '48')
        narrow = self.panel('129')
        narrow.open()
        window = next(call for call in narrow.calls if call[0] == 'new-window')
        self.assertIn('projects', window)

    def test_toggle_closes_only_exact_owned_panel(self):
        panel = self.panel()
        self.assertEqual(panel.toggle(), 'opened')
        self.assertEqual(panel.toggle(), 'closed')
        self.assertEqual(panel.panes, [])

    def test_origin_pane_maps_a_panel_back_to_its_exact_owner(self):
        with patch.dict(os.environ, {'TMUX': '/tmp/tmux,1,2', 'TMUX_PANE': '%9'}), \
             patch.object(command, 'tmux', return_value='%9\t%7') as tmux:
            self.assertEqual(command.origin_pane(), '%7')
            tmux.assert_called_once_with('display-message', '-p', '-t', '%9',
                                         '#{pane_id}\t#{@atlas_projects_origin}')

    def test_rejects_invalid_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                Panel('session:1', ['atlas-projects'], runtime_dir=directory)


if __name__ == '__main__':
    unittest.main()
