"""Layout switching preserves the classic preset and restoration records."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from atlas import layout, palette, settings, state, user


class LayoutSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='atlas-layout-test-')
        self.home = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_switch_back_and_restore_original_absence(self):
        self.assertEqual(layout.current(self.home), 'classic')
        layout.select(self.home, 'framed', live=False)
        self.assertEqual(layout.current(self.home), 'framed')
        self.assertEqual((self.home / layout.TMUX_PREFERENCE).read_text(),
                         'set -g @atlas-layout framed\n')
        layout.select(self.home, 'classic', live=False)
        self.assertEqual(layout.current(self.home), 'classic')
        records = state.load(self.home)['files']
        self.assertTrue(all(item['before']['kind'] == 'absent' for item in records.values()))
        with state.lock(self.home):
            state.transact(self.home, {rel: item['before'] for rel, item in records.items()},
                           restoring=True)
        self.assertFalse((self.home / layout.PREFERENCE).exists())
        self.assertFalse((self.home / layout.TMUX_PREFERENCE).exists())

    def test_failed_live_reload_rolls_back_preferences_and_option(self):
        layout.select(self.home, 'classic', live=False)
        before = {rel: state.snapshot(self.home / rel) for rel in layout.values('classic')}
        with patch.object(layout, 'server_available', return_value=True), \
             patch.object(layout, 'refresh', side_effect=[subprocess.CalledProcessError(1, 'tmux'), None]) as refresh:
            with self.assertRaises(subprocess.CalledProcessError):
                layout.select(self.home, 'framed')
        self.assertEqual([call.args[1] for call in refresh.call_args_list], ['framed', 'classic'])
        self.assertEqual({rel: state.snapshot(self.home / rel) for rel in before}, before)
        for rel in before:
            self.assertEqual(state.load(self.home)['files'][rel]['installed'], before[rel])

    def test_update_and_sync_preserve_selected_style(self):
        layout.select(self.home, 'framed', live=False)
        colors = palette.resolve(ROOT / 'colors.toml')
        for syncing in (False, True):
            desired = user.plan(ROOT, self.home, {'apps'}, colors, syncing=syncing)
            for rel in layout.values('framed'):
                if rel in desired:
                    self.assertEqual(desired[rel], state.snapshot(self.home / rel))
        self.assertEqual(layout.current(self.home), 'framed')

    def test_manual_edit_and_symlink_are_preserved(self):
        layout.select(self.home, 'framed', live=False)
        path = self.home / layout.TMUX_PREFERENCE
        path.write_text('# custom\n')
        with self.assertRaisesRegex(ValueError, 'later edit'):
            layout.select(self.home, 'classic', live=False)
        self.assertEqual(layout.current(self.home), 'framed')
        path.unlink()
        path.symlink_to('layout.json')
        with self.assertRaisesRegex(ValueError, 'regular files'):
            layout.select(self.home, 'classic', live=False)

    def test_no_tmux_server_saves_for_next_terminal(self):
        with patch.object(layout, 'server_available', return_value=False), \
             patch.object(layout, 'refresh') as refresh:
            layout.select(self.home, 'framed')
        refresh.assert_not_called()
        self.assertEqual(layout.current(self.home), 'framed')
        self.assertEqual(settings.menu_entries()['atlas.layout.classic']['action'],
                         'atlas-settings layout classic')


if __name__ == '__main__':
    unittest.main()
