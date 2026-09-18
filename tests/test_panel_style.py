"""Shared panel rendering stays bounded and retains terminal palette ownership."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
import atlas_panel as panel


class PanelStyleTests(unittest.TestCase):
    def test_strips_and_content_share_inset_at_sidebar_and_window_widths(self):
        for columns in (1, 2, 4, 8, 12, 24, 48, 60, 120):
            with self.subTest(columns=columns):
                screen = Mock()
                left, width = panel.layout(columns)
                panel.draw_bar(screen, 0, panel.title('agents', width), 10, columns, 11)
                panel.put(screen, 4, panel.clip('界 e\u0301 activity ' * 20, width), 12, columns, left)
                panel.draw_bar(screen, 9, 'q close', 13, columns)
                for call in screen.addstr.call_args_list:
                    _, x, text, _ = call.args
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x + panel.cell_width(text), columns - 1)
                if columns >= 24:
                    writes = [call.args for call in screen.addstr.call_args_list]
                    self.assertIn((9, left, 'q close', 13), writes)
                    self.assertTrue(any(y == 4 and x == left for y, x, _, _ in writes))
                    self.assertIn((0, 0, ' ' * (columns - 1), 10), writes)

    def test_resize_and_missing_glyph_draw_failures_are_tolerated(self):
        for error in (panel.curses.error(), UnicodeEncodeError('ascii', '界', 0, 1, 'unsupported')):
            screen = Mock()
            screen.addstr.side_effect = error
            panel.draw_bar(screen, 0, '// N Y M', 0, 48)

    def test_sidebar_preserves_main_pane_space_and_limits_growth(self):
        for columns in (0, 80, 129):
            self.assertIsNone(panel.sidebar_width(columns))
        self.assertEqual(panel.sidebar_width(130), 48)
        self.assertEqual(panel.sidebar_width(140), 48)
        self.assertEqual(panel.sidebar_width(141), 60)
        self.assertEqual(panel.sidebar_width(150), 60)
        for columns in (130, 140, 141, 144, 150, 180, 240, 400):
            width = panel.sidebar_width(columns)
            self.assertGreaterEqual(width, 48)
            self.assertLessEqual(width, 60)
            self.assertGreaterEqual(columns - width - 1, 80)

    def test_field_groups_move_intact_and_long_values_remain_available(self):
        fields = [('SERVICE', 'active / running'), ('STARTUP', 'enabled')]
        self.assertEqual(panel.field_rows(fields, 55),
                         ['SERVICE  active / running   STARTUP  enabled'])
        self.assertEqual(panel.field_rows(fields, 43),
                         ['SERVICE  active / running', 'STARTUP  enabled'])
        value = 'Auto / excludes your country and entry country'
        rows = panel.field_rows([('ENTRY', value)], 43, label_width=18)
        self.assertTrue(all(row.startswith(' ' * 18) for row in rows[1:]))
        self.assertEqual(' '.join(' '.join(rows).split()), 'ENTRY ' + value)

    def test_field_reflow_handles_unicode_and_narrow_panes(self):
        for width in (0, 1, 2, 5, 12, 24, 43, 55):
            with self.subTest(width=width):
                rows = panel.field_rows([('地域', '東京 e\u0301 ' * 8), ('EXIT', 'a' * 70)], width)
                self.assertTrue(all(panel.cell_width(row) <= width for row in rows))
                if width >= 2:
                    self.assertEqual(''.join(''.join(rows).split()), '地域' + '東京e\u0301' * 8 + 'EXIT' + 'a' * 70)

    def test_palette_exhaustion_keeps_all_semantic_roles_available(self):
        with patch.object(panel.curses, 'has_colors', return_value=True), \
             patch.object(panel.curses, 'start_color'), \
             patch.object(panel.curses, 'use_default_colors'), \
             patch.object(panel.curses, 'COLORS', 256, create=True), \
             patch.object(panel.curses, 'COLOR_PAIRS', 4, create=True), \
             patch.object(panel.curses, 'init_pair') as init_pair, \
             patch.object(panel.curses, 'init_color') as init_color, \
             patch.object(panel.curses, 'color_pair', side_effect=lambda i: i << 8):
            styles = panel.styles(panel.DEFAULT_PALETTE)
        self.assertTrue(set(panel.DEFAULT_PALETTE) <= styles.keys())
        self.assertTrue({'header', 'header_prefix', 'footer'} <= styles.keys())
        self.assertEqual(init_pair.call_count, 3)
        init_color.assert_not_called()


if __name__ == '__main__':
    unittest.main()
