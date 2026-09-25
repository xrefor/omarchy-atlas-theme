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
        preference = patch.object(vpn, "read_layout_style", return_value="classic")
        preference.start()
        self.addCleanup(preference.stop)
        self.data = {'status': 'State: Connected', 'tunnel': 'Two-hop: off',
                     'gateway': '', 'message': ''}
        self.attributes = dict.fromkeys(
            [*vpn.ROW_ROLES.values(), 'header', 'header_prefix', 'footer'], 0)

    def test_framed_active_mode_comes_from_status_not_selected_settings(self):
        for status, selected, active, configured in (
                ('State: Connected wg to 192.0.2.1 [Entry] → 198.51.100.1 [Exit]',
                 'off', 'dVPN / WireGuard', 'MIXNET'),
                ('State: Connected mix to 192.0.2.1',
                 'on', 'MIXNET', 'dVPN / TWO-HOP WIREGUARD')):
            self.data.update(status=status, tunnel='Two-hop: ' + selected)
            for columns in (48, 60):
                _, width = layout(columns)
                rows = vpn.dashboard(self.data, width, [], style='framed')
                text = '\n'.join(line for line, _ in rows)
                self.assertEqual(rows[1][0], 'CONNECTED · ' + ('dVPN' if active.startswith('dVPN') else 'MIXNET'))
                self.assertNotIn('MIXNET' if active.startswith('dVPN') else 'dVPN', rows[1][0])
                self.assertIn('ACTIVE TUNNEL MODE  ' + active, text)
                content = ' '.join(line[2:-2].strip() for line, role in rows
                                   if isinstance(role, str) and role.startswith('card:')
                                   and line.startswith('│'))
                self.assertIn('SELECTED MODE ' + configured, ' '.join(content.split()))
                self.assertLess(text.index('ACTIVE TUNNEL MODE'), text.index('LIVE ROUTE'))
                self.assertLess(text.index('LIVE ROUTE'), text.index('NEXT CONNECTION'))
                self.assertLess(text.index('NEXT CONNECTION'), text.index('SELECTED MODE'))
                self.assertTrue(all(cell_width(line) <= width for line, _ in rows))

    def test_framed_disconnected_transitions_and_unknown_never_claim_selected_mode_active(self):
        for status, state, active in (
                ('State: Disconnected', 'DISCONNECTED', 'NONE (disconnected)'),
                ('State: Connecting mix, selecting gateways', 'CONNECTING', 'NOT CONFIRMED'),
                ('State: Reconnecting wg', 'RECONNECTING', 'NOT CONFIRMED'),
                ('State: Disconnecting', 'DISCONNECTING', 'NOT CONFIRMED'),
                ('State: Error: tunnel failed', 'ERROR', 'UNKNOWN'),
                ('State: Offline', 'OFFLINE', 'NONE (offline)'),
                ('State: Connected', 'CONNECTED', 'UNKNOWN'),
                ('State: Connected futuristic to 192.0.2.1', 'CONNECTED', 'UNKNOWN'),
                ('Unavailable — last readings may be stale\nState: Connected wg', 'UNAVAILABLE', 'UNKNOWN'),
                ('State: Connectedness unknown', 'UNAVAILABLE', 'UNKNOWN'),
                ('', 'UNAVAILABLE', 'UNKNOWN')):
            with self.subTest(status=status):
                self.data.update(status=status, tunnel='Two-hop: off')
                rows = vpn.dashboard(self.data, 43, [], style='framed')
                self.assertTrue(rows[1][0].startswith(state + ' · '))
                self.assertNotIn('MIXNET', rows[1][0])
                text = '\n'.join(line for line, _ in rows)
                self.assertIn('ACTIVE TUNNEL MODE  ' + active, text)
                self.assertIn('SELECTED MODE   MIXNET', text)

    def test_framed_live_route_and_gateway_configuration_are_distinct(self):
        self.data.update(status='State: Connected wg to 192.0.2.1 [Norway] → 198.51.100.1 [Sweden]',
                         gateway='Entry point: Auto\nExit point: Switzerland',
                         tunnel='Two-hop: off\nIPv6: on')
        for columns in (48, 60):
            screen = Screen(36, columns)
            _, width = layout(columns)
            rows = vpn.dashboard(self.data, width, [('12:00', 'Connected')], style='framed')
            text = '\n'.join(line for line, _ in rows)
            route, configuration = text.split('NEXT CONNECTION / CONFIGURATION')
            self.assertIn('192.0.2.1', route)
            self.assertIn('Norway', route)
            self.assertIn('198.51.100.1', route)
            self.assertNotIn('Switzerland', route)
            self.assertIn('GATEWAY CONFIGURATION', configuration)
            self.assertIn('Switzerland', configuration)
            with patch.object(vpn, 'read_layout_style', return_value='framed'):
                vpn.draw_frame(screen, rows, vpn.footer_rows(width, style='framed'), self.attributes, 999)
            visible = '\n'.join(call[2] for call in screen.calls)
            self.assertIn('CONNECTED', visible)
            self.assertIn('q close', visible)
            self.assertIn('Closing keeps VPN running', visible)

    def test_framed_cards_preserve_wrapped_fields_and_rectangular_edges(self):
        value = 'Gateway in Norway with a very long descriptive country and location name'
        self.data.update(gateway='Entry point: ' + value,
                         message='Settings updated',
                         service={'ActiveState': 'active', 'SubState': 'running',
                                  'UnitFileState': 'enabled'})
        for width in (23, 43, 55):
            rows = vpn.dashboard(self.data, width, [('12:00', 'Connected')],
                                 detailed=True, style='framed')
            cards, current = [], None
            for line, role in rows[4:]:
                if line.startswith('┌'):
                    current = []
                elif line.startswith('└'):
                    cards.append(current)
                    current = None
                elif current is not None:
                    self.assertTrue(line.startswith('│ ') and line.endswith(' │'))
                    self.assertTrue(role.startswith('card:'))
                    current.append(line[2:-2].rstrip())
                if line:
                    self.assertEqual(cell_width(line), width)
            self.assertEqual(len(cards), 6)
            configuration = ' '.join(' '.join(cards[1]).split())
            self.assertIn(value, configuration)
            self.assertIn('SELECTED MODE MIXNET', configuration)
            for columns in (12, 48):
                screen = Screen(8, columns)
                with patch.object(vpn, 'read_layout_style', return_value='framed'):
                    vpn.draw_frame(screen, rows, vpn.footer_rows(max(1, columns - 5)),
                                   self.attributes, 999)

    def test_framed_dashboard_retains_all_action_hints_and_pinned_footer(self):
        screen = Screen(30, 60)
        _, width = layout(screen.columns)
        rows = vpn.dashboard(self.data, width, []) + [(f'body {i}', 7) for i in range(40)]
        footer = vpn.footer_rows(width, style='framed')
        frames = []
        with patch.object(vpn, 'read_layout_style', return_value='framed'):
            for offset in (0, 8):
                vpn.draw_frame(screen, rows, footer, self.attributes, offset)
                frames.append(list(screen.calls))
        text = '\n'.join(call[2] for call in frames[0])
        for hint in ('c connect', 'd disconnect', 'm mode', 's settings', 'r refresh',
                     'i details', 'b setup', 'o app', 'q close', 'Closing keeps VPN running'):
            self.assertIn(hint, text)
        pinned = lambda calls: [call for call in calls if call[0] < 4 or call[0] >= 30 - len(footer) - 3]
        self.assertEqual(pinned(frames[0]), pinned(frames[1]))

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

    def test_framed_footer_hints_fit_inside_the_inset_outline(self):
        for columns in (48, 60):
            _, width = layout(columns)
            footer = vpn.footer_rows(width, style='framed')
            self.assertTrue(all(cell_width(line) <= width - 4 for line in footer))
            screen = Screen(36, columns)
            rows = vpn.dashboard(self.data, width, [], style='framed')
            with patch.object(vpn, 'read_layout_style', return_value='framed'):
                vpn.draw_frame(screen, rows, footer, self.attributes, 999)
            visible = '\n'.join(call[2] for call in screen.calls)
            for hint in ('c connect', 'd disconnect', 'm mode', 's settings',
                         'r refresh', 'i details', 'b setup', 'o app', 'q close'):
                self.assertIn(hint, visible)

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
