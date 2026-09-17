"""Agent dashboard content, terminal safety and active palette behavior."""
import importlib.util
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agents_ui', ROOT / 'components/apps/atlas_agents/ui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class AgentsUiTests(unittest.TestCase):
    def snapshot(self, **agent):
        return {'connected': True, 'agents': [dict(
            id='agent-id', name='palette-review', status='running', started_at=100,
            updated_at=180, activity='Checking the active theme palette', **agent)]}

    def test_reported_status_progress_and_duration(self):
        snapshot = self.snapshot(plan=[{'step': 'Read theme', 'status': 'completed'},
                                       {'step': 'Check panel', 'status': 'in_progress'}])
        rows = ui.dashboard(snapshot, 48, now=185)
        text = '\n'.join(line for line, _ in rows)
        self.assertIn('1 running', text)
        self.assertIn('RUNNING · 1m 25s', text)
        self.assertIn('Plan: 1 / 2 complete', text)
        self.assertNotIn('%', text)
        self.assertIn(('  RUNNING · 1m 25s', 'accent'), rows)

    def test_completed_elapsed_freezes_and_retains_result(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(status='completed', finished_at=185,
                                     activity='Palette and readability checks passed')
        before = ui.dashboard(snapshot, 48, now=200)
        after = ui.dashboard(snapshot, 48, now=10000, show_completed=True)
        self.assertIn(('  COMPLETED · 1m 25s', 'green'), before)
        self.assertIn(('  COMPLETED · 1m 25s', 'green'), after)
        self.assertIn('checks passed', '\n'.join(line for line, _ in after))

    def test_successful_completion_moves_to_history_after_thirty_seconds(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(status='completed', finished_at=185)
        before = ui.dashboard(snapshot, 60, now=214.999)
        after = ui.dashboard(snapshot, 60, now=215)
        self.assertIn(('✓ palette-review', 'bright_foreground'), before)
        self.assertIn(('1 completed', 'secondary'), before)
        self.assertNotIn(('✓ palette-review', 'bright_foreground'), after)
        self.assertIn(('No active agents', 'secondary'), after)
        self.assertIn(('▸ Recently completed (1) · h show', 'secondary'), after)
        self.assertNotIn('Spawned agents will appear here.', '\n'.join(line for line, _ in after))

    def test_only_successful_completed_agents_move_to_history(self):
        snapshot = {'connected': True, 'agents': [
            {'name': status, 'status': status, 'started_at': 100, 'finished_at': 185}
            for status in ui.STATUS
        ]}
        rows = ui.dashboard(snapshot, 60, now=10000)
        names = [line for line, role in rows if role == 'bright_foreground']
        self.assertEqual(len(names), len(ui.STATUS) - 1)
        for status, (symbol, _, _) in ui.STATUS.items():
            if status != 'completed':
                self.assertIn(f'{symbol} {status}', names)

    def test_missing_invalid_or_future_completion_time_keeps_agent_visible(self):
        for finished in (None, '', 'invalid', float('nan'), float('inf'),
                         float('-inf'), {}, [], True, False, -1, 10001):
            with self.subTest(finished=finished):
                snapshot = self.snapshot()
                snapshot['agents'][0].update(status='completed', finished_at=finished)
                rows = ui.dashboard(snapshot, 60, now=10000)
                self.assertIn(('✓ palette-review', 'bright_foreground'), rows)
                self.assertFalse(any('Recently completed' in line for line, _ in rows))

    def test_history_is_latest_first_and_resumed_agent_returns_to_main_list(self):
        snapshot = {'connected': True, 'agents': [
            {'name': 'older-result', 'status': 'completed', 'finished_at': 150},
            {'name': 'newer-result', 'status': 'completed', 'finished_at': 160},
            {'name': 'active', 'status': 'running'},
        ]}
        rows = ui.dashboard(snapshot, 60, now=200, show_completed=True)
        names = [line for line, role in rows if role == 'bright_foreground']
        self.assertEqual(names, ['● active', '✓ newer-result', '✓ older-result'])
        snapshot['agents'][0]['status'] = 'running'
        rows = ui.dashboard(snapshot, 60, now=200)
        self.assertIn(('● older-result', 'bright_foreground'), rows)
        self.assertIn(('2 running', 'secondary'), rows)
        self.assertIn(('▸ Recently completed (1) · h show', 'secondary'), rows)

    def test_missing_completion_time_uses_last_update(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(status='interrupted')
        self.assertIn(('  INTERRUPTED · 1m 20s', 'yellow'),
                      ui.dashboard(snapshot, 48, now=300))

    def test_active_agents_appear_before_completed_results(self):
        snapshot = {'connected': True, 'agents': [
            {'name': 'finished', 'status': 'completed', 'started_at': 190},
            {'name': 'older-active', 'status': 'running', 'started_at': 100},
            {'name': 'newer-active', 'status': 'running', 'started_at': 150},
            {'name': 'awaiting-input', 'status': 'waiting', 'started_at': 175},
        ]}
        rows = ui.dashboard(snapshot, 48, now=200)
        names = [line for line, role in rows if role == 'bright_foreground']
        self.assertEqual(names, ['● newer-active', '● older-active',
                                 '◌ awaiting-input', '✓ finished'])

    def test_no_progress_is_invented_for_empty_or_missing_plan(self):
        for plan in (None, [], [None]):
            rows = ui.dashboard(self.snapshot(plan=plan), 48, now=200)
            self.assertNotIn('Plan:', '\n'.join(line for line, _ in rows))

    def test_tiny_and_wide_character_layout_remains_in_bounds(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(name='界面 e\u0301 ' * 20,
                                     activity='🔍 分析 ' * 100)
        for width in (0, 1, 2, 3, 8, 24, 48, 120):
            with self.subTest(width=width):
                rows = ui.dashboard(snapshot, width, now=200)
                self.assertTrue(all(ui.cell_width(line) <= width for line, _ in rows))
                self.assertLess(len(rows), 15)

    def test_terminal_escapes_bidi_and_controls_never_reach_output(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(
            name='\x1b]2;hostile title\x07review\x1b[31m\x1b[0m',
            activity='OK\x00\x1b]52;c;hidden\x1b\\\u202e\u2066\n\tchecking')
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 60, now=200))
        self.assertIn('review', text)
        self.assertIn('OK checking', text)
        for forbidden in ('\x1b', '\x00', '\x07', '\u202e', '\u2066', 'hostile title', 'hidden'):
            self.assertNotIn(forbidden, text)

    def test_huge_agent_list_and_activity_are_bounded(self):
        snapshot = self.snapshot()
        snapshot['agents'][0]['activity'] = 'very long update ' * 20000
        snapshot['agents'] *= 500
        rows = ui.dashboard(snapshot, 48, now=200)
        self.assertLess(len(rows), 1500)
        self.assertTrue(all(ui.cell_width(line) <= 48 for line, _ in rows))
        self.assertIn(('300 more agents omitted', 'secondary'), rows)

    def test_disconnected_and_empty_observer_explains_wait(self):
        rows = ui.dashboard({'connected': False, 'agents': []}, 48, now=200)
        text = '\n'.join(line for line, _ in rows)
        self.assertIn('Waiting for this Codex conversation', text)
        self.assertIn('Spawned agents will appear here.', text)
        self.assertNotIn('%', text)

    def test_default_palette_matches_theme_source(self):
        source = tomllib.loads((ROOT / 'colors.toml').read_text())
        for role, color in ui.DEFAULT_PALETTE.items():
            self.assertEqual(color, source[role], role)

    def test_active_palette_updates_with_invalid_roles_falling_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'palette.json'
            self.assertEqual(ui.read_palette(path), ui.DEFAULT_PALETTE)
            path.write_text(json.dumps({'accent': '#123ABC', 'red': 'bad', 'unknown': '#ffffff'}))
            palette = ui.read_palette(path)
            self.assertEqual(palette['accent'], '#123abc')
            self.assertEqual(palette['red'], ui.DEFAULT_PALETTE['red'])
            self.assertNotIn('unknown', palette)
            path.write_text('{')
            self.assertEqual(ui.read_palette(path), ui.DEFAULT_PALETTE)
            path.write_text(json.dumps({'accent': '#abcdef'}))
            self.assertEqual(ui.read_palette(path)['accent'], '#abcdef')

    def test_indexed_color_preserves_global_terminal_palette(self):
        with patch.object(ui.curses, 'has_colors', return_value=True), \
             patch.object(ui.curses, 'start_color'), \
             patch.object(ui.curses, 'use_default_colors'), \
             patch.object(ui.curses, 'COLORS', 256, create=True), \
             patch.object(ui.curses, 'COLOR_PAIRS', 256, create=True), \
             patch.object(ui.curses, 'init_pair') as init_pair, \
             patch.object(ui.curses, 'init_color') as init_color, \
             patch.object(ui.curses, 'color_pair', side_effect=lambda index: index << 8):
            styles = ui._styles(ui.DEFAULT_PALETTE)
            self.assertNotEqual(styles['accent'], styles['foreground'])
            self.assertEqual(ui._color_index('#ff0000'), 196)
            self.assertEqual(ui._color_index('#080808'), 232)
            self.assertTrue(all(16 <= call.args[1] <= 255 and 16 <= call.args[2] <= 255
                                for call in init_pair.call_args_list))
            init_color.assert_not_called()

    def test_monochrome_terminal_can_still_render(self):
        with patch.object(ui.curses, 'has_colors', return_value=False):
            styles = ui._styles(ui.DEFAULT_PALETTE)
            self.assertIn('header', styles)
            self.assertIn('foreground', styles)

    def test_refresh_scroll_and_exit_remain_read_only(self):
        screen = Mock()
        screen.getmaxyx.return_value = (8, 40)
        screen.getch.side_effect = [ord('j'), ord('r'), ord('q')]
        get_snapshot = Mock(return_value=self.snapshot())
        on_refresh = Mock()
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'read_palette', return_value=ui.DEFAULT_PALETTE), \
             patch.object(ui, '_styles', return_value=dict.fromkeys(
                 [*ui.DEFAULT_PALETTE, 'header', 'header_prefix', 'footer'], 0)):
            ui._screen(screen, get_snapshot, None, on_refresh)
        on_refresh.assert_called_once_with()
        self.assertEqual(get_snapshot.call_count, 2)
        self.assertEqual(screen.refresh.call_count, 3)

    def test_history_keyboard_toggle_recovers_results(self):
        screen = Mock()
        screen.getmaxyx.return_value = (12, 60)
        screen.getch.side_effect = [ui.curses.KEY_END, ord('h'), ord('H'), ord('q')]
        snapshot = self.snapshot()
        snapshot['agents'][0].update(status='completed', finished_at=185,
                                     activity='Recovered result')
        on_refresh = Mock()
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui.time, 'time', return_value=300), \
             patch.object(ui, 'read_palette', return_value=ui.DEFAULT_PALETTE), \
             patch.object(ui, '_styles', return_value=dict.fromkeys(
                 [*ui.DEFAULT_PALETTE, 'header', 'header_prefix', 'footer'], 0)), \
             patch.object(ui, 'dashboard', wraps=ui.dashboard) as dashboard:
            ui._screen(screen, Mock(return_value=snapshot), None, on_refresh)
        self.assertEqual([call.kwargs['show_completed'] for call in dashboard.call_args_list],
                         [False, False, True, False])
        rendered = [call.args[2] for call in screen.addstr.call_args_list]
        self.assertIn('  Recovered result', rendered)
        self.assertIn('▾ Recently completed (1) · h hide', rendered)
        on_refresh.assert_not_called()


if __name__ == '__main__':
    unittest.main()
