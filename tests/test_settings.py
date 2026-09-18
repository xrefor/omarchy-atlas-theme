"""Settings exercise preserved edits, rollback, and installer compatibility."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from atlas import config, palette, settings, state, user


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='atlas-settings-test-')
        self.home = Path(self.temp.name)
        self.rel = '.config/hypr/looknfeel.lua'
        self.original = '-- user comment\no.window(".*", { opacity = "0.87 override 0.87 override 1.0 override" })\no.window("^zen$", { opacity = "1.0 override 1.0 override 1.0 override" })\n'
        self.path = self.home / self.rel
        self.path.parent.mkdir(parents=True)
        self.path.write_text(self.original)

    def tearDown(self): self.temp.cleanup()

    def test_menu_preserves_comments_urls_and_other_entries(self):
        original = '{\n// cast } menu\n"cast": {"action":"https://example.org/a//b",},\n}\n// final }\n'
        result = config.menu_extension(original, settings.menu_entries())
        self.assertIn('// cast } menu', result)
        self.assertEqual(config.jsonc(result)['cast']['action'], 'https://example.org/a//b')
        self.assertEqual(config.menu_extension(result, settings.menu_entries()), result)
        entries = settings.menu_entries()
        self.assertEqual(entries['atlas.opacity.p95']['label'], '95% · Default')
        self.assertEqual(entries['atlas.opacity.p87']['label'], '87%')
        with self.assertRaisesRegex(ValueError, 'unmarked'):
            config.menu_extension('{"atlas": {}}', settings.menu_entries())

    def test_opacity_preserves_exceptions_and_original_through_changes(self):
        settings.set_opacity(self.home, 95, live=False)
        settings.set_opacity(self.home, 100, live=False)
        self.assertIn('-- user comment', self.path.read_text())
        self.assertIn('o.window("^zen$",', self.path.read_text())
        self.assertEqual(settings.opacity_info(self.home)[1], 100)
        records = state.load(self.home)['files']
        self.assertEqual(state.text_value(records[self.rel]['before']), self.original)
        with state.lock(self.home):
            state.transact(self.home, {k: v['before'] for k, v in records.items()}, restoring=True)
        self.assertEqual(self.path.read_text(), self.original)

    def test_rejected_hyprland_reload_reverts_file_and_manifest(self):
        with patch.object(settings, 'hyprland_check', side_effect=[None, ValueError('invalid config'), None]):
            with self.assertRaisesRegex(ValueError, 'invalid config'):
                settings.set_opacity(self.home, 95)
        self.assertEqual(self.path.read_text(), self.original)
        self.assertEqual(state.load(self.home)['files'][self.rel]['installed'], state.snapshot(self.path))

    def test_manual_edits_block_settings_mutation(self):
        settings.set_opacity(self.home, 95, live=False)
        self.path.write_text(self.path.read_text() + '-- later edit\n')
        with self.assertRaisesRegex(ValueError, 'later edit'):
            settings.set_opacity(self.home, 80, live=False)
        self.assertEqual(settings.opacity_info(self.home)[1], 95)

    def test_ambiguous_rules_are_not_changed(self):
        other = self.home / '.config/hypr/hyprland.lua'
        other.write_text(self.original)
        with self.assertRaisesRegex(ValueError, 'one ATLAS opacity rule'):
            settings.set_opacity(self.home, 100, live=False)
        self.assertEqual(self.path.read_text(), self.original)

    def test_installer_retains_selected_opacity_and_menu_is_idempotent(self):
        settings.set_opacity(self.home, 95, live=False)
        colors = palette.resolve(ROOT / 'colors.toml')
        desired = user.plan(ROOT, self.home, {'desktop'}, colors)
        self.assertIn('0.95 override 0.95', state.text_value(desired[self.rel]))
        self.assertEqual(len(settings.OPACITY_RULE.findall(state.text_value(desired[self.rel]))), 1)
        user.validate(desired)
        # Only write relevant config: avoid copying the runtime media just to test merge behavior.
        for rel in (self.rel, settings.MENU_PATH): state.write(self.home / rel, desired[rel])
        second = user.plan(ROOT, self.home, {'desktop'}, colors)
        self.assertEqual(second[self.rel], desired[self.rel])
        self.assertEqual(second[settings.MENU_PATH], desired[settings.MENU_PATH])

    def test_creator_rule_in_main_config_is_not_duplicated(self):
        main = self.home / '.config/hypr/hyprland.lua'
        self.path.rename(main)
        self.path.write_text('-- other preferences\n')
        plan = user.plan(ROOT, self.home, {'desktop'}, palette.resolve(ROOT / 'colors.toml'))
        self.assertNotIn('opacity', state.text_value(plan[self.rel]))
        self.assertEqual(main.read_text(), self.original)

    def test_installer_keeps_zen_opaque_after_global_rule_and_preset_changes(self):
        opaque = 'o.window("^zen$", { opacity = "1.0 override 1.0 override 1.0 override" })'
        global_rule = 'o.window(".*", { opacity = "0.87 override 0.87 override 1.0 override" })'
        cases = {
            'fresh': ('', ''),
            'upgrade': (config.block('', 'APPEARANCE', global_rule, '--'), ''),
            'existing_exception': (self.original, ''),
            'main_config': ('-- other preferences\n', 'require("hypr.looknfeel")\n' + global_rule + '\n'),
        }
        colors = palette.resolve(ROOT / 'colors.toml')
        for name, (looknfeel, main) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                (home / '.config/hypr').mkdir(parents=True)
                originals = {self.rel: looknfeel, '.config/hypr/hyprland.lua': main}
                for rel, content in originals.items():
                    (home / rel).write_text(content)
                desired = user.plan(ROOT, home, {'desktop'}, colors)
                user.validate(desired)
                relevant = {rel: value for rel, value in desired.items()
                            if rel in originals or rel == settings.MENU_PATH}
                with state.lock(home):
                    state.transact(home, relevant)
                rel, percent = settings.opacity_info(home)
                self.assertEqual(percent, 95 if name == 'fresh' else 87)
                text = (home / rel).read_text()
                self.assertGreater(text.rfind(opaque), settings.OPACITY_RULE.search(text).start())
                repeated = user.plan(ROOT, home, {'desktop'}, colors)
                for path, value in relevant.items():
                    self.assertEqual(repeated[path], value)
                for preset in settings.PRESETS:
                    settings.set_opacity(home, preset, live=False)
                    text = (home / rel).read_text()
                    self.assertGreater(text.rfind(opaque), settings.OPACITY_RULE.search(text).start())
                records = state.load(home)['files']
                with state.lock(home):
                    state.transact(home, {path: record['before'] for path, record in records.items()}, restoring=True)
                for path, content in originals.items():
                    self.assertEqual((home / path).read_text(), content)

    def test_restore_active_theme_is_read_only(self):
        settings.set_opacity(self.home, 95, live=False)
        active = self.home / '.local/state/omarchy/current/theme.name'
        active.parent.mkdir(parents=True)
        active.write_text('atlas\n')
        with patch.object(settings.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(settings.restore(ROOT, self.home), 1)
        run.assert_not_called()
        self.assertEqual(settings.opacity_info(self.home)[1], 95)

    def test_restore_cancel_only_runs_preview(self):
        settings.set_opacity(self.home, 95, live=False)
        with patch.object(settings.subprocess, 'run') as run, patch.object(settings.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value=''), contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 0
            self.assertEqual(settings.restore(ROOT, self.home), 0)
        self.assertEqual(run.call_count, 1)
        self.assertIn('--dry-run', run.call_args.args[0])
        self.assertEqual(settings.opacity_info(self.home)[1], 95)

    def test_failed_restore_preview_never_requests_confirmation(self):
        settings.set_opacity(self.home, 95, live=False)
        with patch.object(settings.subprocess, 'run') as run, patch('builtins.input') as prompt, contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 1
            self.assertEqual(settings.restore(ROOT, self.home), 1)
        prompt.assert_not_called()
        self.assertEqual(run.call_count, 1)


if __name__ == '__main__': unittest.main()
