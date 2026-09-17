"""Neovim comment preferences survive upgrades and preserve user edits/originals."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from atlas import palette, readability, state, user


class ReadabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='atlas readability ')
        self.home = Path(self.temp.name)
        self.path = self.home / readability.PREFERENCE

    def tearDown(self): self.temp.cleanup()

    def select(self, value):
        with contextlib.redirect_stdout(io.StringIO()):
            return readability.select(self.home, value)

    def restore(self):
        records = state.load(self.home)['files']
        with state.lock(self.home), contextlib.redirect_stdout(io.StringIO()):
            state.transact(self.home, {key: item['before'] for key, item in records.items()}, restoring=True)

    def test_optional_default_repeat_selection_and_restore(self):
        self.assertEqual(readability.current(self.home), 'standard')
        self.assertFalse(self.path.exists())
        self.select('readable')
        stamp = state.metadata(self.home, 'manifest.json').stat().st_mtime_ns
        self.select('readable')
        self.assertEqual(state.metadata(self.home, 'manifest.json').stat().st_mtime_ns, stamp)
        self.select('standard')
        self.restore()
        self.assertFalse(self.path.exists())

    def test_preexisting_choice_survives_upgrade_palette_sync_and_restores(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('standard\n')
        self.select('readable')
        colors = palette.resolve(ROOT / 'colors.toml')
        for components in ({'theme'}, {'desktop'}):
            desired = user.plan(ROOT, self.home, components, colors)
            self.assertEqual(state.text_value(desired[readability.PREFERENCE]), 'readable\n')
        colors['foreground'] = '#ffffff'
        synced = user.plan(ROOT, self.home, {'theme', 'desktop', 'apps'}, colors, syncing=True)
        self.assertNotIn(readability.PREFERENCE, synced)
        self.restore()
        self.assertEqual(self.path.read_text(), 'standard\n')

    def test_manual_and_malformed_edits_block_changes(self):
        self.select('readable')
        self.path.write_text('standard\n')
        with self.assertRaisesRegex(ValueError, 'later edit'): self.select('readable')
        self.path.write_text('unknown\n')
        with self.assertRaises(ValueError): self.select('standard')
        self.assertEqual(self.path.read_text(), 'unknown\n')
        with self.assertRaises(ValueError): self.select('unknown')

    def test_symlink_preference_is_not_followed(self):
        self.path.parent.mkdir(parents=True)
        original = self.home / 'original'
        original.write_text('standard\n')
        self.path.symlink_to(original)
        with self.assertRaises(ValueError): self.select('readable')
        self.assertEqual(original.read_text(), 'standard\n')

    def test_menu_commands_and_validation(self):
        def run(*args):
            return subprocess.run([sys.executable, str(ROOT / 'settings.py'), *args,
                                   '--home', str(self.home)], capture_output=True, text=True)
        self.assertEqual(run('readability-is', 'standard').returncode, 0)
        self.assertEqual(run('readability', 'readable').returncode, 0)
        self.assertEqual(run('readability-is', 'readable').returncode, 0)
        self.assertEqual(run('readability-is', 'standard').returncode, 1)
        for args in [('readability',), ('readability', 'unknown'), ('opacity',),
                     ('opacity', 'readable'), ('opacity-is', '90'), ('status', 'readable')]:
            self.assertEqual(run(*args).returncode, 2, args)
        self.assertEqual(readability.current(self.home), 'readable')


if __name__ == '__main__': unittest.main()
