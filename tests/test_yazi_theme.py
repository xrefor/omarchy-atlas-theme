"""Validate the rendered preview palette and readable file-manager state colors."""
from pathlib import Path
import plistlib
import sys
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from atlas import palette


def contrast(first, second):
    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                  for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class YaziThemeTests(unittest.TestCase):
    def setUp(self):
        self.colors = tomllib.loads((ROOT / 'colors.toml').read_text())

    def syntax(self, colors):
        rendered = palette.render(ROOT / 'components/apps/templates/yazi.tmTheme', colors)
        self.assertNotIn('{{', rendered)
        theme = plistlib.loads(rendered.encode())
        scopes = {scope.strip(): rule['settings']
                  for rule in theme['settings'] if 'scope' in rule
                  for scope in rule['scope'].split(',')}
        return theme['settings'][0]['settings'], scopes

    def test_preview_roles_are_distinct_and_readable(self):
        base, scopes = self.syntax(self.colors)
        self.assertEqual(base['background'], self.colors['background'])
        self.assertEqual(base['foreground'], self.colors['foreground'])
        expected_roles = {
            'string': 'green', 'entity.name.function': 'blue',
            'support.function': 'blue', 'entity.name.class': 'yellow',
            'support.type': 'yellow', 'constant': 'bright_yellow',
            'variable.other.constant': 'bright_yellow',
            'variable.parameter': 'cyan', 'variable.other.member': 'cyan',
            'variable.other.property': 'bright_cyan',
            'variable': 'foreground', 'keyword.operator': 'foreground',
        }
        for scope, color in expected_roles.items():
            with self.subTest(scope=scope):
                self.assertEqual(scopes[scope]['foreground'], self.colors[color])
        comment = scopes['comment']['foreground']
        self.assertNotEqual(comment, scopes['string']['foreground'])
        for scope in ('string.quoted.docstring', 'string.quoted.single.block.python',
                      'string.quoted.double.block.python'):
            self.assertEqual(scopes[scope]['foreground'], comment)
        self.assertEqual(scopes['constant.character.escape'], scopes['keyword'])
        self.assertEqual(scopes['constant.language'], scopes['constant.numeric'])
        for scope in ('comment', 'punctuation', 'keyword', 'constant.numeric'):
            for background in ('background', 'lighter_background', 'selection'):
                with self.subTest(scope=scope, background=background):
                    self.assertGreaterEqual(contrast(scopes[scope]['foreground'],
                                                     self.colors[background]), 4.5)

    def test_preview_recolors_with_the_active_palette(self):
        _, original = self.syntax(self.colors)
        changed = {key: '#eef2f6' if key == 'background' else '#25384b'
                   for key, value in self.colors.items()
                   if isinstance(value, str) and value.startswith('#')}
        base, scopes = self.syntax(changed)
        self.assertEqual(base['background'], '#eef2f6')
        for scope in original:
            if 'foreground' in original[scope]:
                with self.subTest(scope=scope):
                    self.assertNotEqual(scopes[scope]['foreground'], original[scope]['foreground'])

    def test_directory_focus_and_danger_text_are_readable(self):
        theme = tomllib.loads(palette.render(ROOT / 'components/apps/templates/yazi.toml',
                                            self.colors))
        directory = next(rule for rule in theme['filetype']['rules'] if rule['url'] == '*/')
        icon = next(rule for rule in theme['icon']['globs'] if rule['url'] == '*/')
        self.assertEqual(directory['fg'], self.colors['foreground'])
        self.assertEqual(icon['fg'], self.colors['accent'])
        self.assertEqual(theme['indicator']['current']['fg'], self.colors['accent'])
        for style in (theme['mgr']['count_cut'], theme['mode']['unset_main'],
                      theme['mode']['unset_alt']):
            self.assertGreaterEqual(contrast(style['fg'], style['bg']), 4.5)


if __name__ == '__main__':
    unittest.main()
