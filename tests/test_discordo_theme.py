"""Discordo receives only a palette-derived visual overlay."""
from pathlib import Path
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

    def test_template_contains_only_visual_theme_keys(self):
        rendered = tomllib.loads(palette.render(self.template, self.colors))
        self.assertEqual(set(rendered), {'theme'})
        self.assertEqual(rendered['theme']['messages_list']['mention_style']['foreground'],
                         self.colors['accent'])
        self.assertEqual(rendered['theme']['messages_list']['message_style']['background'],
                         self.colors['background'])

    def test_install_merges_theme_without_changing_preferences(self):
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
            self.assertEqual(config['sidebar']['width_percent'], 37)
            self.assertEqual(config['keybinds']['quit'], 'q')
            self.assertEqual(config['theme']['title']['alignment'], 'left')
            self.assertEqual(config['theme']['title']['normal_style']['foreground'],
                             self.colors['secondary'])

    def test_palette_sync_regenerates_only_the_theme(self):
        with tempfile.TemporaryDirectory(prefix='atlas-discordo-sync-') as directory:
            home = Path(directory)
            path = home / '.config/discordo/config.toml'
            path.parent.mkdir(parents=True)
            path.write_text('editor = "helix"\n[theme.title]\nnormal_style = {}\n')
            changed = dict(self.colors, accent='#123456')
            desired = user.plan(ROOT, home, {'apps'}, changed, syncing=True)
            config = tomllib.loads(state.text_value(desired['.config/discordo/config.toml']))
            self.assertEqual(config['editor'], 'helix')
            self.assertEqual(config['theme']['title']['active_style']['foreground'], '#123456')


if __name__ == '__main__':
    unittest.main()
