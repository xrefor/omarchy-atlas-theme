"""Discordo receives a palette overlay and an auditable source customization."""
from pathlib import Path
import re
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from atlas import palette, state, user


class DiscordoThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.colors = palette.resolve(ROOT / 'colors.toml')
        cls.template = ROOT / 'components/apps/templates/discordo.toml'
        cls.customization = ROOT / 'components/apps/discordo'

    def test_template_contains_the_atlas_presentation(self):
        rendered = tomllib.loads(palette.render(self.template, self.colors))
        self.assertEqual(set(rendered), {
            'date_separator', 'icons', 'show_attachment_links', 'sidebar',
            'theme', 'timestamps',
        })
        self.assertFalse(rendered['show_attachment_links'])
        self.assertEqual(rendered['sidebar']['width_percent'], 28)
        self.assertEqual(rendered['sidebar']['markers'], {
            'expanded': '- ', 'collapsed': '+ ', 'leaf': '  ',
        })
        self.assertTrue(all(value == '' for value in rendered['icons'].values()))
        self.assertEqual(rendered['timestamps']['format'], '15:04')
        self.assertEqual(rendered['date_separator']['format'], '02 January 2006')
        self.assertEqual(rendered['theme']['messages_list']['author_style']['foreground'],
                         self.colors['bright_foreground'])
        self.assertEqual(rendered['theme']['messages_list']['mention_style']['foreground'],
                         self.colors['accent'])
        self.assertEqual(rendered['theme']['messages_list']['message_style']['background'],
                         self.colors['background'])

    def test_install_merges_presentation_without_changing_unowned_preferences(self):
        with tempfile.TemporaryDirectory(prefix='atlas-discordo-') as directory:
            home = Path(directory)
            path = home / '.config/discordo/config.toml'
            path.parent.mkdir(parents=True)
            path.write_text('''editor = "nvim"
[sidebar]
width_percent = 37
[keybinds]
quit = "q"
[theme.title]
alignment = "right"
normal_style = { foreground = "#000000" }
''')
            desired = user.plan(ROOT, home, {'apps'}, self.colors)
            config = tomllib.loads(state.text_value(desired['.config/discordo/config.toml']))
            self.assertEqual(config['editor'], 'nvim')
            self.assertEqual(config['sidebar']['width_percent'], 28)
            self.assertEqual(config['keybinds']['quit'], 'q')
            self.assertEqual(config['theme']['title']['alignment'], 'left')
            self.assertEqual(config['theme']['title']['normal_style']['foreground'],
                             self.colors['secondary'])

    def test_install_preserves_existing_config_mode_and_protects_new_config(self):
        for existing, expected in ((0o640, 0o640), (None, 0o600)):
            with self.subTest(existing=existing), \
                 tempfile.TemporaryDirectory(prefix='atlas-discordo-mode-') as directory:
                home = Path(directory)
                path = home / '.config/discordo/config.toml'
                if existing is not None:
                    path.parent.mkdir(parents=True)
                    path.write_text('editor = "nvim"\n')
                    path.chmod(existing)
                desired = user.plan(ROOT, home, {'apps'}, self.colors)
                self.assertEqual(desired['.config/discordo/config.toml']['mode'], expected)

    def test_palette_sync_regenerates_presentation_without_unowned_changes(self):
        with tempfile.TemporaryDirectory(prefix='atlas-discordo-sync-') as directory:
            home = Path(directory)
            path = home / '.config/discordo/config.toml'
            path.parent.mkdir(parents=True)
            path.write_text('editor = "helix"\n[theme.title]\nnormal_style = {}\n')
            changed = dict(self.colors, accent='#123456')
            desired = user.plan(ROOT, home, {'apps'}, changed, syncing=True)
            config = tomllib.loads(state.text_value(desired['.config/discordo/config.toml']))
            self.assertEqual(config['editor'], 'helix')
            self.assertEqual(config['sidebar']['width_percent'], 28)
            self.assertEqual(config['theme']['title']['active_style']['foreground'], '#123456')

    def test_source_customization_is_version_pinned_and_scoped(self):
        commit = (self.customization / 'BASE_COMMIT').read_text().strip()
        self.assertRegex(commit, r'^[0-9a-f]{40}$')
        self.assertEqual(commit, 'e87645a180accc64f6bcc332d19080f90f0ac39f')

        patch = (self.customization / 'atlas.patch').read_text()
        paths = set(re.findall(r'^diff --git a/(\S+) b/\1$', patch, re.MULTILINE))
        self.assertEqual(paths, {
            'cmd/version.go',
            'internal/markdown/link_label.go',
            'internal/markdown/link_label_test.go',
            'internal/markdown/renderer.go',
            'internal/ui/chat/channelspicker/model.go',
            'internal/ui/chat/channelspicker/model_test.go',
            'internal/ui/chat/chat_presentation_test.go',
            'internal/ui/chat/composer.go',
            'internal/ui/chat/guildstree/model.go',
            'internal/ui/chat/guildstree/model_test.go',
            'internal/ui/chat/mentionslist/model.go',
            'internal/ui/chat/messages_list.go',
            'internal/ui/chat/model.go',
            'internal/ui/list_label.go',
            'internal/ui/list_label_test.go',
            'internal/ui/util.go',
        })
        self.assertFalse(any(path.startswith(('internal/gateway/', 'internal/http/',
                                               'internal/keyring/', 'internal/tls/'))
                             for path in paths))
        license_text = (ROOT / 'LICENSES/Discordo-GPL-3.0.txt').read_text()
        self.assertIn('GNU GENERAL PUBLIC LICENSE', license_text)
        self.assertIn('Version 3, 29 June 2007', license_text)

    def test_customization_subtree_has_an_exact_release_inventory(self):
        files = {path.relative_to(self.customization).as_posix()
                 for path in self.customization.rglob('*') if path.is_file()}
        self.assertEqual(files, {'BASE_COMMIT', 'README.md', 'atlas.patch'})

    def test_apps_install_carries_the_source_customization(self):
        with tempfile.TemporaryDirectory(prefix='atlas-discordo-payload-') as directory:
            home = Path(directory)
            desired = user.plan(ROOT, home, {'apps'}, self.colors)
            prefix = '.local/share/atlas/components/apps/discordo/'
            self.assertEqual(state.text_value(desired[prefix + 'BASE_COMMIT']).strip(),
                             'e87645a180accc64f6bcc332d19080f90f0ac39f')
            self.assertEqual(state.text_value(desired[prefix + 'atlas.patch']),
                             (self.customization / 'atlas.patch').read_text())


if __name__ == '__main__':
    unittest.main()
