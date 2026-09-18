"""Layout regressions without a VPN session, service, or terminal."""
import importlib.machinery
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

vpn = importlib.machinery.SourceFileLoader(
    'vpn_ui', str(Path(__file__).resolve().parents[1] / 'components/apps/bin/atlas-vpn')
).load_module()
from atlas_panel import cell_width, layout


class Screen:
    def __init__(self, height=24, columns=48):
        self.height, self.columns = height, columns
        self.calls = []

    def getmaxyx(self):
        return self.height, self.columns

    def erase(self):
        self.calls.clear()

    def addstr(self, row, left, text, style):
        assert 0 <= row < self.height
        assert 0 <= left < self.columns
        assert left + cell_width(text) < self.columns
        self.calls.append((row, left, text, style))


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.data = {'status': 'State: Connected', 'tunnel': 'Two-hop: off',
                     'gateway': '', 'message': ''}
        self.attributes = dict.fromkeys(
            [*vpn.ROW_ROLES.values(), 'header', 'header_prefix', 'footer'], 0)

    def test_dashboard_status_groups_wrap_together_without_inline_shortcuts(self):
        self.data['service'] = {'ActiveState': 'active', 'SubState': 'running',
                                'UnitFileState': 'enabled'}
        self.data['tunnel'] = 'Two-hop: on\nIPv6: on\nCircumvention transports: off'
        for columns in (48, 60):
            _, width = layout(columns)
            rows = [line for line, _ in vpn.dashboard(self.data, width, [])]
            if columns == 60:
                self.assertIn('SERVICE  active / running   STARTUP  enabled', rows)
            else:
                self.assertIn('SERVICE  active / running', rows)
                self.assertIn('STARTUP  enabled', rows)
            self.assertIn('IPv6  on   CIRCUMVENTION  off', rows)
            self.assertIn('SELECTED MODE   dVPN / TWO-HOP WIREGUARD', rows)
            self.assertTrue(all(cell_width(line) <= width for line in rows))
            text = '\n'.join(rows)
            for shortcut in ('[B setup', 'O app]', '[M options]', '/ O app]'):
                self.assertNotIn(shortcut, text)

    def test_gateway_values_wrap_with_hanging_alignment_without_losing_text(self):
        value = 'Gateway in Norway with a very long descriptive country and location name'
        self.data['gateway'] = 'Entry point: ' + value
        for columns in (48, 60):
            _, width = layout(columns)
            rows = [line for line, _ in vpn.dashboard(self.data, width, [])]
            first = next(index for index, line in enumerate(rows) if line.startswith('ENTRY'))
            group = []
            for line in rows[first:]:
                if not line:
                    break
                group.append(line)
            self.assertGreater(len(group), 1)
            self.assertEqual(group[0][:18], 'ENTRY'.ljust(18))
            self.assertTrue(all(line.startswith(' ' * 18) for line in group[1:]))
            self.assertEqual(' '.join(line[18:].strip() for line in group), value)
            self.assertTrue(all(cell_width(line) <= width for line in group))

    def test_long_status_values_remain_available_as_continuations(self):
        value = 'waiting for service readiness during an extended startup operation'
        self.data['service'] = {'ActiveState': value, 'SubState': 'starting',
                                'UnitFileState': 'enabled-runtime'}
        rows = [line for line, _ in vpn.dashboard(self.data, 43, [])]
        first = next(index for index, line in enumerate(rows) if line.startswith('SERVICE'))
        last = next(index for index, line in enumerate(rows) if line.startswith('STARTUP'))
        group = rows[first:last]
        self.assertEqual(' '.join(line[9:].strip() for line in group), value + ' / starting')
        self.assertTrue(all(line.startswith(' ' * 9) for line in group[1:]))
        self.assertIn('STARTUP  enabled-runtime', rows)
        self.assertTrue(all(cell_width(line) <= 43 for line in group))

    def test_live_palette_change_restyles_once_without_touching_backend(self):
        first = {'foreground': '#d6cfc4'}
        changed = {'foreground': '#abcdef'}
        screen = Mock()
        screen.getmaxyx.return_value = (24, 48)
        screen.getch.side_effect = [-1, -1, ord('q'), ord('q')]
        service = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
                   'UnitFileState': 'disabled', 'error': ''}
        with patch.object(vpn, 'read_service', return_value=service), \
                patch.object(vpn, 'read_palette', side_effect=[first, first, changed, changed]), \
                patch.object(vpn, 'styles', side_effect=[dict(self.attributes, foreground=10),
                                                       dict(self.attributes, foreground=20)]) as style, \
                patch.object(vpn.curses, 'curs_set'), \
                patch.object(vpn, 'Backend') as backend:
            vpn.panel(screen, None)
        self.assertEqual([call.args[0] for call in style.call_args_list], [first, changed])
        self.assertEqual([call.args for call in screen.bkgd.call_args_list], [(' ', 10), (' ', 20)])
        backend.assert_not_called()

    def test_sidebar_footer_keeps_all_dashboard_actions_and_tunnel_hint(self):
        _, width = layout(48)
        footer = vpn.footer_rows(width, age='Last reading 2s ago')
        text = '\n'.join(footer)
        for hint in ('c connect', 'd disconnect', 'm mode', 's settings', 'r refresh',
                     'i details', 'b setup', 'o app', '↑↓ scroll', 'q close',
                     'Closing keeps VPN running'):
            self.assertIn(hint, text)
        self.assertTrue(all(cell_width(line) <= width for line in footer))

    def test_editor_confirmation_and_mode_keys_match_the_current_page(self):
        editor = '\n'.join(vpn.footer_rows(43, 'advanced', editor='average-packet-delay'))
        self.assertIn('Enter apply', editor)
        self.assertIn('Esc cancel', editor)
        self.assertNotIn('Digits select', editor)
        self.assertNotIn('scroll', editor)
        confirm = '\n'.join(vpn.footer_rows(43, 'service', confirm='start'))
        self.assertIn('y confirm', confirm)
        self.assertIn('n/Esc cancel', confirm)
        self.assertNotIn('2 enable', confirm)
        mode = '\n'.join(vpn.footer_rows(43, 'mode'))
        self.assertIn('1 dVPN', mode)
        self.assertIn('2 Mixnet', mode)
        self.assertNotIn('a advanced', mode)

    def test_header_and_footer_stay_pinned_while_scrolling(self):
        screen = Screen()
        _, width = layout(screen.columns)
        rows = vpn.header_rows('MIXNET / DVPN CONTROL', width)
        rows += [(f'body {index}', 7) for index in range(60)]
        footer = vpn.footer_rows(width)
        vpn.draw_frame(screen, rows, footer, self.attributes, 0)
        first = list(screen.calls)
        self.assertEqual(vpn.draw_frame(screen, rows, footer, self.attributes, 12), 12)
        pinned = lambda calls: [call for call in calls if call[0] < 4 or call[0] >= screen.height - len(footer)]
        self.assertEqual(pinned(first), pinned(screen.calls))
        self.assertIn((4, 2, 'body 12', 0), screen.calls)
        self.assertIn((23, 2, 'Closing keeps VPN running', 0), screen.calls)

    def test_short_sidebar_keeps_exit_and_confirmation_keys_visible(self):
        for height in (5, 10):
            for options, keys in (({}, ('q close',)),
                                  ({'page': 'settings'}, ('Esc back',)),
                                  ({'page': 'service', 'confirm': 'enable'}, ('n/Esc cancel', 'y confirm')),
                                  ({'page': 'advanced', 'editor': 'average-packet-delay'}, ('Esc cancel', 'Enter apply'))):
                screen = Screen(height, 48)
                _, width = layout(screen.columns)
                rows = vpn.dashboard(self.data, width, [])
                vpn.draw_frame(screen, rows, vpn.footer_rows(width, **options), self.attributes, 0)
                text = '\n'.join(call[2] for call in screen.calls)
                for key in keys:
                    self.assertIn(key, text)

    def test_body_and_subtitle_preserve_right_inset_with_wide_text(self):
        screen = Screen()
        rows = vpn.header_rows('界' * 50, 43) + [('界' * 50, 7)]
        vpn.draw_frame(screen, rows, vpn.footer_rows(43), self.attributes, 0)
        for row, left, text, _ in screen.calls:
            if row in (1, 4):
                self.assertLessEqual(cell_width(text), 43)
                self.assertEqual(left, 2)

    def test_all_pages_share_fixed_header_and_survive_small_windows(self):
        service = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
                   'UnitFileState': 'disabled', 'error': ''}
        for columns in (1, 4, 12, 28, 48, 80):
            _, width = layout(columns)
            width = max(1, width)
            pages = [vpn.dashboard(self.data, width, []),
                     vpn.settings_rows(self.data, width, 'settings'),
                     vpn.service_rows(service, width, None)]
            for rows in pages:
                self.assertEqual(rows[0][0], vpn.title('NYM', width))
                self.assertEqual(rows[2][0], '─' * width)
                self.assertEqual(rows[3][0], '')
                for height in (1, 3, 8, 24):
                    with self.subTest(columns=columns, height=height):
                        screen = Screen(height, columns)
                        vpn.draw_frame(screen, rows, vpn.footer_rows(width), self.attributes, 999)


if __name__ == '__main__':
    unittest.main()
