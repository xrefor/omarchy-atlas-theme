"""Frontier panel tmux ownership and safe argv construction."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_frontier.tmux_panel import Panel


class FakePanel(Panel):
    def __init__(self, width=160):
        self.calls = []
        self.width = width
        self.panes = []
        self._directory = tempfile.mkdtemp(prefix='atlas-frontier-tmux-')
        super().__init__('%7', ['/path with spaces/atlas-frontier', 'show'],
                         runtime_dir=self._directory)

    def cleanup(self):
        shutil.rmtree(self._directory, ignore_errors=True)

    def _tmux(self, *args):
        self.calls.append(args)
        if args[:2] == ('list-panes', '-a'):
            return '\n'.join(f'{pane}\t%7' for pane in self.panes)
        if args[:3] == ('display-message', '-p', '-t'):
            return f'%7\t$1\t{self.width}'
        if args[0] in ('split-window', 'new-window'):
            self.panes = ['%9']
            return '%9'
        if args[0] == 'kill-pane':
            self.panes.remove(args[-1])
        return ''


class FrontierTmuxTests(unittest.TestCase):
    def panel(self, width=160):
        panel = FakePanel(width)
        self.addCleanup(panel.cleanup)
        return panel

    def test_origin_and_command_are_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                Panel('not-a-pane', ['viewer'], runtime_dir=directory)
            with self.assertRaises(ValueError):
                Panel('%1', ['bad\0argument'], runtime_dir=directory)

    def test_wide_origin_opens_detached_literal_sidebar(self):
        panel = self.panel(160)
        self.assertEqual(panel.open(), '%9')
        split = next(call for call in panel.calls if call[0] == 'split-window')
        self.assertIn('-d', split)
        self.assertEqual(split[split.index('-l') + 1], '60')
        self.assertEqual(split[-3:], ('--', '/path with spaces/atlas-frontier', 'show'))

    def test_medium_origin_uses_48_columns(self):
        panel = self.panel(135)
        panel.open()
        split = next(call for call in panel.calls if call[0] == 'split-window')
        self.assertEqual(split[split.index('-l') + 1], '48')

    def test_narrow_origin_opens_detached_window(self):
        panel = self.panel(129)
        panel.open()
        command = next(call for call in panel.calls if call[0] == 'new-window')
        self.assertIn('-d', command)
        self.assertIn('frontier', command)

    def test_close_only_kills_exact_owned_panel(self):
        panel = self.panel()
        panel.panes = ['%9']
        self.assertTrue(panel.close())
        self.assertEqual(panel.panes, [])
        self.assertFalse(panel.close())


if __name__ == '__main__':
    unittest.main()
