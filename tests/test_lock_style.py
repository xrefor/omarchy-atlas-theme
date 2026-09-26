"""Lock appearance preferences survive upgrades and restore their original value."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from atlas import lock_style, palette, settings, state, user


class LockStyleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='atlas lock style ')
        self.home = Path(self.temp.name)
        self.path = self.home / lock_style.PREFERENCE

    def tearDown(self): self.temp.cleanup()

    def change(self, value):
        with contextlib.redirect_stdout(io.StringIO()):
            return lock_style.select(self.home, value)

    def test_default_toggle_and_restore_missing_preference(self):
        self.assertEqual(lock_style.current(self.home), 'terminal')
        desired = user.plan(ROOT, self.home, {'shell'}, palette.resolve(ROOT / 'colors.toml'))
        self.assertEqual(state.text_value(desired[lock_style.PREFERENCE]), 'terminal\n')
        self.assertEqual(self.change('toggle'), 'classic')
        self.assertEqual(self.change('toggle'), 'terminal')
        records = state.load(self.home)['files']
        with state.lock(self.home), contextlib.redirect_stdout(io.StringIO()):
            state.transact(self.home, {key: item['before'] for key, item in records.items()}, restoring=True)
        self.assertFalse(self.path.exists())

    def test_existing_terminal_preference_survives_install_and_restores(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('terminal\n')
        desired = user.plan(ROOT, self.home, {'shell'}, palette.resolve(ROOT / 'colors.toml'))
        self.assertEqual(state.text_value(desired[lock_style.PREFERENCE]), 'terminal\n')
        self.assertIn('.local/bin/atlas-lock-style', desired)
        self.assertIn('.config/omarchy/plugins/atlas.lock/atlas.svg', desired)
        user.validate(desired)
        self.change('classic')
        updated = user.plan(ROOT, self.home, {'shell'}, palette.resolve(ROOT / 'colors.toml'))
        self.assertEqual(state.text_value(updated[lock_style.PREFERENCE]), 'classic\n')
        records = state.load(self.home)['files']
        with state.lock(self.home), contextlib.redirect_stdout(io.StringIO()):
            state.transact(self.home, {key: item['before'] for key, item in records.items()}, restoring=True)
        self.assertEqual(self.path.read_text(), 'terminal\n')

    def test_manual_edits_and_invalid_preferences_are_preserved(self):
        self.change('terminal')
        self.path.write_text('classic\n')
        with self.assertRaisesRegex(ValueError, 'later edit'): self.change('terminal')
        self.path.write_text('other\n')
        with self.assertRaises(ValueError): lock_style.current(self.home)
        self.assertEqual(self.path.read_text(), 'other\n')

    def test_symlink_preference_is_not_followed(self):
        self.path.parent.mkdir(parents=True)
        other = self.home / 'other'
        other.write_text('terminal\n')
        self.path.symlink_to(other)
        with self.assertRaises(ValueError): self.change('classic')
        self.assertEqual(other.read_text(), 'terminal\n')

    def test_settings_show_switch_only_when_command_installed(self):
        menu = settings.menu_entries()
        self.assertIn('command -v atlas-lock-style', menu['atlas.lock']['when'])
        self.assertEqual(menu['atlas.lock.terminal']['action'], 'atlas-lock-style terminal')

    def test_release_keeps_session_lock_guard_and_latches_style(self):
        service = (ROOT/'components/desktop/plugins/atlas.lock/Service.qml').read_text()
        self.assertIn('sessionLock.locked || sessionLock.secure', service)
        self.assertIn('locked ? activeTerminalStyle : preferredTerminalStyle', service)
        self.assertIn('activeTerminalStyle = preferredTerminalStyle', service)


if __name__ == '__main__': unittest.main()
