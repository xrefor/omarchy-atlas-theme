"""Shared panel rendering stays bounded and retains terminal palette ownership."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
import atlas_panel as panel


class PanelStyleTests(unittest.TestCase):
    def test_layout_preference_falls_back_without_changing_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'layout.json'
            self.assertEqual(panel.read_layout_style(path), 'classic')
            for content, expected in [('{}', 'classic'), ('[]', 'classic'), ('{', 'classic'),
                                      ('{"style":"framed"}', 'framed'),
                                      ('{"style":"classic"}', 'classic')]:
                path.write_text(content)
                self.assertEqual(panel.read_layout_style(path), expected)

    def test_framed_scroll_pins_rails_and_neutral_card_edges(self):
        screen = Mock()
        screen.getmaxyx.return_value = (18, 60)
        styles = {role: index for index, role in enumerate(panel.DEFAULT_PALETTE)}
        styles.update(header=30, header_prefix=31, footer=32)
        rows = [(panel.title('agents', 55), 'accent'), ('1 running', 'secondary'),
                ('', 'muted'), ('', 'foreground')]
        rows += panel.card_rows([(f'content {i}', 'accent') for i in range(30)], 55)
        frames = []
        for offset in (0, 8):
            screen.addstr.reset_mock()
            result = panel.draw_panel_frame(screen, rows, styles, offset,
                                             'h history · q close', style='framed')
            frames.append([call.args for call in screen.addstr.call_args_list])
            self.assertEqual(result[:3], (offset, 10, 32))
        pinned = lambda calls: [call for call in calls if call[0] < 4 or call[0] >= 14]
        self.assertEqual(pinned(frames[0]), pinned(frames[1]))
        self.assertIn((17, 0, '└' + '─' * 57 + '┘', styles['dark_foreground']), frames[0])
        self.assertIn((5, 2, '│', styles['dark_foreground']), frames[0])
        self.assertIn((5, 56, '│', styles['dark_foreground']), frames[0])

    def test_card_outline_uses_continuous_panel_surface(self):
        screen = Mock()
        colors = {role: index for index, role in enumerate(panel.DEFAULT_PALETTE)}
        colors.update({'card_' + role: 100 + index
                       for index, role in enumerate(panel.DEFAULT_PALETTE)})
        rows = panel.card_rows([('Review', 'accent'), ('Elapsed    1m 25s', 'secondary')], 43)
        for y, (text, role) in enumerate(rows):
            panel.draw_row(screen, y, text, role, colors, 48, 2, 43)
        grid = {}
        for call in screen.addstr.call_args_list:
            y, x, text, attribute = call.args
            for index, char in enumerate(text):
                grid[y, x + index] = (char, attribute)
        for y in range(len(rows)):
            for x in range(2, 45):
                self.assertLess(grid[y, x][1], 100)
        self.assertEqual(grid[0, 2][0], '┌')
        self.assertEqual(grid[len(rows) - 1, 44][0], '┘')
        self.assertEqual(''.join(grid[1, x][0] for x in range(3, 44)), ' Review' + ' ' * 34)

    def test_framed_header_alignment_perimeter_and_neutral_footer(self):
        colors = {role: index for index, role in enumerate(panel.DEFAULT_PALETTE)}
        colors.update(header=100, header_prefix=101, footer=102)
        colors.update({'card_' + role: 200 + index
                       for index, role in enumerate(panel.DEFAULT_PALETTE)})
        footer = ['↑↓ scroll · h history', 'r refresh · q close']
        for columns, subtitle, combined in ((60, '2 RUNNING / 1 DONE', True),
                                             (24, '2 RUNNING / 1 DONE', False),
                                             (60, '界面 2 RUNNING', True)):
            screen = Mock()
            rows = [(panel.title('agents', columns - 5), 'accent'),
                    (subtitle, 'secondary'), ('', 'muted'), ('', 'foreground')]
            result = panel.draw_framed_panel(screen, rows, colors, 99, footer,
                                             dimensions=(20, columns))
            self.assertEqual(result[:3], (0, 11, 0))
            calls = [call.args for call in screen.addstr.call_args_list]
            self.assertTrue(all(attribute < 100 for _, _, _, attribute in calls))
            left, width = panel.layout(columns)
            if combined:
                self.assertIn((1, left + width - panel.cell_width(subtitle), subtitle,
                               colors['secondary']), calls)
            else:
                self.assertIn((2, left, subtitle, colors['secondary']), calls)
            for row in range(1, 19):
                self.assertTrue(any(y == row and x == 0 and text[0] in '│├'
                                    for y, x, text, _ in calls))
                self.assertTrue(any(y == row and x + panel.cell_width(text) == columns - 1
                                    and text[-1] in '│┤' for y, x, text, _ in calls))
            self.assertIn((18, left, '└' + '─' * (width - 2) + '┘',
                           colors['dark_foreground']), calls)

    def test_pending_plan_cells_render_as_solid_neutral_blocks(self):
        screen = Mock()
        colors = {role: index for index, role in enumerate(panel.DEFAULT_PALETTE)}
        rows = panel.card_rows([('█ □ □', 'accent')], 23)
        for row, (text, role) in enumerate(rows):
            panel.draw_row(screen, row, text, role, colors, 28, 2, 23)
        calls = [call.args for call in screen.addstr.call_args_list]
        self.assertIn((1, 6, '█', colors['secondary']), calls)
        self.assertIn((1, 8, '█', colors['secondary']), calls)
        screen.addstr.reset_mock()
        for row, (text, role) in enumerate(panel.card_rows([('Task □ literal', 'foreground')], 23)):
            panel.draw_row(screen, row, text, role, colors, 28, 2, 23)
        self.assertFalse(any(call.args[2] == '█' for call in screen.addstr.call_args_list))

    def test_paired_card_spans_preserve_colors_and_unicode_positions(self):
        colors = {role: index for index, role in enumerate(panel.DEFAULT_PALETTE)}
        colors.update({'card_' + role: 100 + index
                       for index, role in enumerate(panel.DEFAULT_PALETTE)})
        for left_text, suffix in (('Review', 'WORKER'), ('界 e\u0301', '役割 e\u0301')):
            screen = Mock()
            inner = 23
            content = left_text + ' ' * (inner - panel.cell_width(left_text + suffix)) + suffix
            role = f'split:bright_foreground:secondary:{panel.cell_width(suffix)}'
            text, card_role = panel.card_rows([(content, role)], inner + 4)[1]
            panel.draw_row(screen, 3, text, card_role, colors, 32, 2, inner + 4)
            calls = [call.args for call in screen.addstr.call_args_list]
            self.assertEqual(calls[0], (3, 2, text, colors['bright_foreground']))
            self.assertIn((3, 4 + inner - panel.cell_width(suffix), suffix, colors['secondary']), calls)
            self.assertIn((3, 28, '│', colors['dark_foreground']), calls)
            self.assertTrue(all(attribute < 100 for _, _, _, attribute in calls))

    def test_paired_plan_colors_only_its_right_span(self):
        colors = {role: index for index, role in enumerate(panel.DEFAULT_PALETTE)}
        for plan_role in ('accent', 'green'):
            screen = Mock()
            prefix, suffix, inner = 'Plan □ 1/3', '█ □ □', 23
            content = prefix + ' ' * (inner - len(prefix + suffix)) + suffix
            role = f'split:secondary:plan_{plan_role}:5'
            text, card_role = panel.card_rows([(content, role)], inner + 4)[1]
            panel.draw_row(screen, 0, text, card_role, colors, 32, 2, inner + 4)
            calls = [call.args for call in screen.addstr.call_args_list]
            self.assertEqual(calls[0][3], colors['secondary'])
            self.assertIn((0, 22, suffix, colors[plan_role]), calls)
            self.assertIn((0, 24, '█', colors['secondary']), calls)
            self.assertIn((0, 26, '█', colors['secondary']), calls)
            self.assertEqual(sum(text == '█' for _, _, text, _ in calls), 2)

    def test_malformed_paired_spans_fail_without_repainting_or_raising(self):
        colors = {role: index for index, role in enumerate(panel.DEFAULT_PALETTE)}
        content = 'label' + ' ' * 16 + '界'
        for role in ('split:accent:secondary:0', 'split:accent:secondary:99',
                     'split:accent:secondary:1',  # Would split the final wide glyph.
                     'split:accent:secondary:-1', 'split:accent:secondary:x',
                     'split:accent:secondary:999999999999999999999999999',
                     'split:header:secondary:2', 'split:accent:card_accent:2',
                     'split:accent:plan_red:2', 'split:accent:secondary:2:extra'):
            screen = Mock()
            text, card_role = panel.card_rows([(content, role)], 27)[1]
            panel.draw_row(screen, 0, text, card_role, colors, 32, 2, 27)
            calls = [call.args for call in screen.addstr.call_args_list]
            self.assertEqual(len(calls), 3, role)
            self.assertEqual(calls[0][3], colors['foreground'], role)

    def test_tiny_list_footer_prioritizes_exit_without_changing_string_footer(self):
        colors = dict.fromkeys([*panel.DEFAULT_PALETTE, 'header', 'footer', 'header_prefix'], 0)
        rows = [('AGENTS', 'accent'), ('', 'secondary'), ('', 'muted'), ('', 'foreground')]
        footer = ['↑↓ scroll · h history', 'r refresh · q close']
        for columns, expected in ((48, footer[1]), (16, 'q close')):
            screen = Mock()
            panel.draw_framed_panel(screen, rows, colors, 0, footer,
                                    dimensions=(8, columns))
            self.assertTrue(any(call.args[0] == 7 and call.args[2] == expected
                                for call in screen.addstr.call_args_list))
        screen = Mock()
        panel.draw_framed_panel(screen, rows, colors, 0, 'existing string', dimensions=(8, 48))
        self.assertTrue(any(call.args[2] == 'existing string' for call in screen.addstr.call_args_list))

    def test_framed_resize_keeps_controls_and_draws_within_terminal(self):
        styles = dict.fromkeys([*panel.DEFAULT_PALETTE, 'header', 'footer', 'header_prefix'], 0)
        for height in (1, 3, 8, 10, 24):
            for columns in (1, 4, 12, 24, 48, 60):
                screen = Mock()
                screen.getmaxyx.return_value = (height, columns)
                _, width = panel.layout(columns)
                rows = [(panel.title('agents', width), 'accent'), ('1 running', 'secondary'),
                        ('', 'muted'), ('', 'foreground')]
                rows += panel.card_rows([('界面 e\u0301 ' * 20, 'accent')] * 30, width)
                panel.draw_panel_frame(screen, rows, styles, 999, 'q close', style='framed')
                calls = [call.args for call in screen.addstr.call_args_list]
                for row, left, text, _ in calls:
                    self.assertTrue(0 <= row < height)
                    self.assertLessEqual(left + panel.cell_width(text), columns - 1)
                if columns >= 24:
                    self.assertTrue(any('q close' in call[2] for call in calls))

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
