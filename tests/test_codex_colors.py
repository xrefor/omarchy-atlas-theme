"""Terminal sequences may be split anywhere, including opaque control payloads."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_codex.colors import Colors

PALETTE = {key: '#112233' for key in (*Colors.names, 'lighter_background')}
PALETTE.update(accent='#ff5a12', bright_yellow='#ffbb55', lighter_background='#25201e')


class CodexColorsTests(unittest.TestCase):
    def transformed(self, source, expected):
        for split in range(len(source) + 1):
            colors = Colors(PALETTE)
            self.assertEqual(colors.feed(source[:split]) + colors.feed(source[split:]) + colors.finish(), expected)
        colors = Colors(PALETTE)
        self.assertEqual(b''.join(colors.feed(bytes([b])) for b in source) + colors.finish(), expected)

    def test_named_and_indexed_interface_colors(self):
        self.transformed(b'\x1b[1;36mhello\x1b[0m', b'\x1b[1;38;2;255;90;18mhello\x1b[0m')
        self.transformed(b'\x1b[94m\x1b[38;5;6m', b'\x1b[38;2;255;187;85m\x1b[38;2;255;90;18m')
        self.transformed(b'\x1b[48;5;4m', b'\x1b[48;2;255;90;18m')

    def test_only_dark_neutral_truecolor_backgrounds_change(self):
        self.transformed(b'\x1b[48;2;40;42;44m', b'\x1b[48;2;37;32;30m')
        for seq in (b'\x1b[38;2;40;42;44m', b'\x1b[58;2;40;42;44m',
                    b'\x1b[48;2;255;42;44m', b'\x1b[48;2;40;60;44m', b'\x1b[38;5;200m'):
            self.transformed(seq, seq)

    def test_colon_malformed_and_non_sgr_are_unchanged(self):
        for seq in (b'\x1b[38:2::1:2:3m', b'\x1b[38;2;1;m', b'\x1b[38;5;999m',
                    b'\x1b[?25h', b'\x1b[2J', b'\x1b[48;2;;2;3m', b'\x1b[38m',
                    b'\x1b[38;3;4m', b'\x1b[999999999999999999999m'):
            self.transformed(seq, seq)

    def test_control_strings_are_opaque_and_bel_only_terminates_osc(self):
        for start in (b'\x1bP', b'\x1b_', b'\x1b^', b'\x1bX'):
            seq = start + b'data\x07\x1b[36mopaque\x1b\\'
            self.transformed(seq, seq)
        self.transformed(b'\x1b]title\x1b[36m\x07\x1b[36m', b'\x1b]title\x1b[36m\x07\x1b[38;2;255;90;18m')
        self.transformed(b'\x1b]52;c;opaque\x1b[36m\x1b\\', b'\x1b]52;c;opaque\x1b[36m\x1b\\')

    def test_buffers_bounded_and_incomplete_sequences_flushed(self):
        for prefix in (b'\x1b[', b'\x1b]', b'\x1bP'):
            colors = Colors(PALETTE)
            data = prefix + b'1' * 100000
            output = colors.feed(data)
            self.assertLessEqual(len(colors.pending), colors.max_sequence)
            self.assertEqual(output + colors.finish(), data)
        self.transformed(b'end\x1b[38;2;', b'end\x1b[38;2;')
        self.transformed('æøå 🦀'.encode() + b'\x1b', 'æøå 🦀'.encode() + b'\x1b')

    def test_invalid_palette_rejected_before_output(self):
        for changed in ({'accent': 'orange'}, {'red': 123}):
            with self.assertRaises(ValueError):
                Colors(PALETTE | changed)
        with self.assertRaises(KeyError):
            Colors({})

    def test_c1_control_strings_stay_opaque_without_mistaking_utf8(self):
        for start in (b'\x90', b'\x98', b'\x9d', b'\x9e', b'\x9f'):
            seq = start + b'data\x1b[36m' + 'ě🦀'.encode() + b'\x9c'
            self.transformed(seq, seq)
        seq = 'ě🦀'.encode() + b'\x1b[36m'
        self.transformed(seq, 'ě🦀'.encode() + b'\x1b[38;2;255;90;18m')
        self.transformed(b'\x9b36m', b'\x9b36m')
