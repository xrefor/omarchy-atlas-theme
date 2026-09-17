"""Keep Python-rendered color mixes compatible with Omarchy templates."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from atlas import palette


class MixTests(unittest.TestCase):
    def render(self, text, colors=None):
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / 'test.tpl'
            template.write_text(text)
            return palette.render(template, colors or {'start': '#000000', 'end': '#ffffff'})

    def test_fraction_and_percentage_forms_agree(self):
        for amount in ('0.2', '20', '20%', '20.0%'):
            with self.subTest(amount=amount):
                self.assertEqual(self.render('{{ mix start end ' + amount + ' }}'), '#333333')

    def test_channels_round_half_up(self):
        self.assertEqual(self.render('{{ mix start end 0.5 }}',
                                    {'start': '#000102', 'end': '#010203'}), '#010203')

    def test_endpoints_and_clamping(self):
        for amount, expected in [('0', '#000000'), ('1', '#ffffff'),
                                 ('100%', '#ffffff'), ('200%', '#ffffff'), ('200', '#ffffff')]:
            with self.subTest(amount=amount):
                self.assertEqual(self.render('{{ mix start end ' + amount + ' }}'), expected)

    def test_mix_and_plain_tokens_render_together(self):
        self.assertEqual(self.render('fg={{mix\tstart end 50%}}; bg={{ start }}'),
                         'fg=#808080; bg=#000000')

    def test_unknown_color_is_not_silently_substituted(self):
        with self.assertRaises(KeyError):
            self.render('{{ mix missing end 20% }}')


if __name__ == '__main__':
    unittest.main()
