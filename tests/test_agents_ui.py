"""Agent dashboard content, terminal safety and active palette behavior."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import tomllib
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'components/apps'))
spec = importlib.util.spec_from_file_location('agents_ui', ROOT / 'components/apps/atlas_agents/ui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class AgentsUiTests(unittest.TestCase):
    def setUp(self):
        preference = patch.object(ui, "read_layout_style", return_value="classic")
        preference.start()
        self.addCleanup(preference.stop)

    def snapshot(self, **agent):
        return {'connected': True, 'agents': [dict(
            id='agent-id', name='palette-review', status='running', started_at=100,
            updated_at=180, task='Review the active theme palette',
            activity='Checking the active theme palette', **agent)]}

    def test_framed_status_symbols_are_distinct_from_plan_cells(self):
        expected = {'starting': '◌', 'running': '●', 'waiting': '▲',
                    'idle': '○', 'completed': '■', 'interrupted': '−',
                    'error': '✖', 'unknown': '?'}
        for status, symbol in expected.items():
            agent = {'name': 'palette_review', 'task': 'Palette review', 'status': status,
                     'plan': [{'status': 'completed'}, {'status': 'pending'}]}
            rows = ui._framed_agent_rows(agent, 55, 185)
            text = '\n'.join(line for line, _ in rows)
            self.assertIn('Agent · Palette review', text)
            self.assertIn(symbol + ' ' + ui.STATUS[status][1], text)
            self.assertIn('█ □', text)
            self.assertEqual(text.count('Palette review'), 1)

    def test_framed_cards_use_only_reported_steps_and_keep_history(self):
        snapshot = self.snapshot(plan=[{'status': 'completed'}, {'status': 'in_progress'}, None])
        rows = ui.dashboard(snapshot, 55, now=185, style='framed')
        text = '\n'.join(line for line, _ in rows)
        self.assertIn('█ □', text)
        self.assertIn('1 of 2 steps complete', text)
        self.assertIn('01:25', text)
        self.assertTrue(any(line.startswith('┌') and role == 'card:dark_foreground' for line, role in rows))
        snapshot['agents'][0].update(status='completed', finished_at=185)
        self.assertNotIn('Palette review', '\n'.join(line for line, _ in
            ui.dashboard(snapshot, 55, now=300, style='framed')))
        restored = ui.dashboard(snapshot, 55, now=300, style='framed', show_completed=True)
        self.assertIn('Palette review', '\n'.join(line for line, _ in restored))
        self.assertTrue(any('COMPLETED' in line and role.startswith('card:split:green:') for line, role in restored))
        self.assertTrue(any('█ □' in line and ':plan_green:' in role for line, role in restored))
        self.assertTrue(any('█ □' in line and ':plan_accent:' in role for line, role in rows))

    def test_framed_card_uses_adjacent_metadata_rows_without_invented_fields(self):
        agent = self.snapshot(role='worker', plan=[{'status': 'completed'}, {'status': 'pending'}])['agents'][0]
        rows = ui._framed_agent_rows(agent, 55, 185)
        content = [' '.join(line[2:-2].split()) for line, _ in rows if line.startswith('│')]
        self.assertEqual(content[:4], ['Agent · Palette review WORKER', '● RUNNING 01:25',
            'Plan 1 of 2 steps complete █ □', 'Review the active theme palette'])
        self.assertNotIn('', content)
        self.assertEqual(rows[-1], ('', 'foreground'))
        minimal = ui._framed_agent_rows({'name': 'review', 'status': 'running'}, 55, 185)
        text = '\n'.join(line for line, _ in minimal)
        self.assertNotIn('Plan', text)
        self.assertNotIn('worker', text)
        self.assertNotIn('Agent task', text)

    def test_framed_summary_counts_only_displayed_history(self):
        snapshot = {'connected': True, 'agents': [
            {'name': 'active', 'status': 'running'},
            {'name': 'recent', 'status': 'completed', 'finished_at': 190},
            {'name': 'archived', 'status': 'completed', 'finished_at': 150}]}
        self.assertEqual(ui.dashboard(snapshot, 55, now=200, style='framed')[1][0],
                         '1 RUNNING / 1 DONE')
        self.assertEqual(ui.dashboard(snapshot, 55, now=200, style='framed', show_completed=True)[1][0],
                         '1 RUNNING / 2 DONE')
        self.assertEqual(ui.dashboard(snapshot, 55, now=200, show_completed=True)[1][0],
                         '1 running · 1 completed')

    def test_framed_footer_uses_two_rows_and_keeps_narrow_exit(self):
        for width in (34, 43, 55):
            footer = ui._footer(width, 'framed')
            self.assertEqual(len(footer), 2)
            self.assertTrue(all(ui.cell_width(line) <= width for line in footer))
            self.assertIn('h history', footer[0])
            self.assertIn('q close', footer[1])
        self.assertEqual(ui._footer(14, 'framed'), 'q close')
        self.assertIsInstance(ui._footer(55, 'classic'), str)

    def test_framed_elapsed_clock_retains_terminal_state_freezing(self):
        agent = {'status': 'running', 'started_at': 100}
        self.assertEqual(ui.elapsed(agent, 105, compact=True), '00:05')
        self.assertEqual(ui.elapsed(agent, 3765, compact=True), '1:01:05')
        self.assertEqual(ui.elapsed(agent, 3765), '1h 01m')
        agent.update(status='completed', finished_at=185)
        self.assertEqual(ui.elapsed(agent, 9000, compact=True), '01:25')

    def test_framed_next_uses_immediate_pending_step_only_for_live_tasks(self):
        agent = self.snapshot(plan=[{'status': 'inProgress', 'step': 'Current work'},
                                    {'status': 'pending', 'step': 'Run checks'},
                                    {'status': 'pending', 'step': 'Publish results'}])['agents'][0]
        def text():
            return '\n'.join(line for line, _ in ui._framed_agent_rows(agent, 55, 185))
        self.assertIn('Next · Run checks', text())
        self.assertNotIn('Publish results', text())
        for status in ('completed', 'interrupted', 'error', 'unknown'):
            agent['status'] = status
            self.assertNotIn('Next ·', text())
        agent['status'] = 'waiting'
        agent['plan'][1]['step'] = ''
        self.assertNotIn('Next ·', text(), 'do not skip an unnamed immediate next step')
        for duplicate in (agent['task'], agent['activity'], 'Palette review.'):
            agent['plan'][1]['step'] = duplicate
            self.assertNotIn('Next ·', text())

    def test_framed_checklist_normalizes_valid_states_and_sanitizes_names(self):
        agent = self.snapshot(plan=[None, {}, {'status': 'invented', 'step': 'No'},
            {'status': [], 'step': 'Bad state'}, {'status': 'completed', 'step': 'Read sources'},
            {'status': 'inProgress', 'step': '\x1b[31mCheck\u202e colors'},
            {'status': 'in_progress', 'step': 'Check colors'}, {'status': 'pending'}])['agents'][0]
        collapsed = '\n'.join(line for line, _ in ui._framed_agent_rows(agent, 55, 185))
        detailed = '\n'.join(line for line, _ in ui._framed_agent_rows(agent, 55, 185, show_plan=True))
        self.assertIn('1 of 4 steps complete', collapsed)
        self.assertNotIn('Read sources', collapsed)
        self.assertIn('✓ Read sources', detailed)
        self.assertEqual(detailed.count('● Check colors'), 2, 'separate reported steps remain separate')
        self.assertIn('○ Unnamed step', detailed)
        self.assertNotIn('\x1b', detailed)
        self.assertNotIn('\u202e', detailed)
        self.assertNotIn('Bad state', detailed)

    def test_framed_split_and_checklist_fit_unicode_and_narrow_widths(self):
        agent = self.snapshot(role='界面 e\u0301 reviewer', plan=[
            {'status': 'pending', 'step': '界面 e\u0301 ' * 50}])['agents'][0]
        for width in (16, 20, 24, 43, 55):
            rows = ui._framed_agent_rows(agent, width, 185, show_plan=True)
            self.assertTrue(all(ui.cell_width(line) <= width for line, _ in rows))
        row, role = ui._split_rows('Task 界', 'REVIEW e\u0301', 30, 'bright_foreground', 'secondary')[0]
        self.assertEqual(ui.cell_width(row), 30)
        self.assertTrue(row.endswith('REVIEW e\u0301'))
        self.assertEqual(role, 'split:bright_foreground:secondary:8')
        rows = ui._split_rows('Long task title', 'WORKER', 12, 'bright_foreground', 'secondary')
        self.assertGreater(len(rows), 1)
        self.assertTrue(all(ui.cell_width(line) <= 12 for line, _ in rows))

    def test_plan_key_toggles_all_framed_cards_without_refreshing_backend(self):
        screen = Mock()
        screen.getmaxyx.return_value = (30, 60)
        screen.getch.side_effect = [ord('p'), ord('P'), ord('q')]
        snapshot = self.snapshot(plan=[{'status': 'pending', 'step': 'Run checks'}])
        on_refresh = Mock()
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'read_layout_style', return_value='framed'), \
             patch.object(ui, 'read_palette', return_value=ui.DEFAULT_PALETTE), \
             patch.object(ui, '_styles', return_value=dict.fromkeys(
                 [*ui.DEFAULT_PALETTE, 'header', 'header_prefix', 'footer'], 0)), \
             patch.object(ui, 'dashboard', wraps=ui.dashboard) as dashboard:
            ui._screen(screen, Mock(return_value=snapshot), None, on_refresh)
        self.assertEqual([call.kwargs['show_plan'] for call in dashboard.call_args_list],
                         [False, True, False])
        on_refresh.assert_not_called()

    def test_framed_cards_have_no_fictional_progress_and_fit_narrow_widths(self):
        for plan in (None, [], [None], [{'status': 'pending'}] * 100):
            snapshot = self.snapshot(plan=plan)
            snapshot['agents'][0]['name'] = '界面 e\u0301 ' * 30
            for width in (0, 1, 8, 16, 24, 43, 55):
                rows = ui.dashboard(snapshot, width, now=200, style='framed')
                self.assertTrue(all(ui.cell_width(line) <= width for line, _ in rows))
                text = '\n'.join(line for line, _ in rows)
                self.assertNotIn('%', text)
                if not plan or plan == [None]:
                    self.assertNotIn('Steps', text)
                    self.assertNotIn('□', text)
                elif width >= 24:
                    self.assertIn('0 of 64', text)
                    self.assertIn('complete', text)
                    self.assertNotIn('□', text)

    def test_framed_hierarchy_displays_only_supplied_public_activity(self):
        snapshot = self.snapshot(role='worker')
        rows = ui.dashboard(snapshot, 55, now=185, style='framed')
        text = '\n'.join(line for line, _ in rows)
        self.assertIn('Palette review', text)
        self.assertIn('Now · Checking the active theme palette', text)
        self.assertIn('WORKER', text)
        self.assertIn('01:25', text)
        self.assertLess(text.index('RUNNING'), text.index('Now ·'))
        self.assertLess(text.index('WORKER'), text.index('01:25'))
        self.assertLess(text.index('01:25'), text.index('Now ·'))
        for activity in ('', None, snapshot['agents'][0]['task']):
            snapshot['agents'][0]['activity'] = activity
            text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 55, now=185, style='framed'))
            self.assertNotIn('Now ·', text)
        snapshot['agents'][0]['activity'] = '\x1b[31mChecking\u202e\x00'
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 55, now=185, style='framed'))
        self.assertIn('Now · Checking', text)
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\u202e', text)

    def test_busy_framed_dashboard_preserves_full_cards_and_completed_metadata(self):
        for columns, width in ((60, 55), (48, 43)):
            snapshot = {'connected': True, 'agents': [
                {'name': f'task_{i}', 'task': f'Review component {i}', 'role': 'worker',
                 'status': 'running' if i < 6 else 'completed', 'started_at': 100 + i,
                 'finished_at': None if i < 6 else 190, 'activity': 'Checking tests',
                 'plan': [{'status': 'completed'}, {'status': 'pending'}]}
                for i in range(10)]}
            rows = ui.dashboard(snapshot, width, now=200, style='framed')
            text = '\n'.join(line for line, _ in rows)
            self.assertEqual(text.count('Now · Checking tests'), 6)
            for i in range(10):
                self.assertIn(f'Task {i}', text)
                self.assertIn(f'Review component {i}', text)
            self.assertLessEqual(len(rows), 200)
            self.assertTrue(all(ui.cell_width(line) <= width for line, _ in rows))
            active = ui._framed_agent_rows(snapshot['agents'][0], width, 200)
            completed = ui._framed_agent_rows(snapshot['agents'][-1], width, 200)
            self.assertLess(len(completed), len(active))
            self.assertTrue(any('WORKER' in line for line, _ in completed))
            self.assertTrue(any('01:21' in line for line, _ in completed))
            self.assertFalse(any('Now ·' in line for line, _ in completed))
            self.assertEqual(sum(line.startswith('┌') for line, _ in rows), 10)

    def test_framed_narrow_fallback_retains_classic_content(self):
        agent = self.snapshot(role='worker', plan=[{'status': 'completed'}])['agents'][0]
        for width in (0, 1, 8, 15):
            self.assertEqual(ui._framed_agent_rows(agent, width, 200), ui._agent_rows(agent, width, 200))

    def test_busy_framed_end_and_down_reach_last_completed_card(self):
        screen = Mock()
        screen.getmaxyx.return_value = (16, 48)
        screen.getch.side_effect = [ui.curses.KEY_END, ord('j'), ord('q')]
        snapshot = {'connected': True, 'agents': [
            {'name': f'task_{i}', 'task': f'Review component {i}', 'status': 'running',
             'started_at': 100 + i, 'activity': 'Checking tests'} for i in range(10)]}
        frames = []
        def frame():
            frames.append([call.args[2] for call in screen.addstr.call_args_list])
            screen.addstr.reset_mock()
        screen.refresh.side_effect = frame
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'read_layout_style', return_value='framed'), \
             patch.object(ui, 'read_palette', return_value=ui.DEFAULT_PALETTE), \
             patch.object(ui, '_styles', return_value=dict.fromkeys(
                 [*ui.DEFAULT_PALETTE, 'header', 'header_prefix', 'footer'], 0)):
            ui._screen(screen, Mock(return_value=snapshot), None, None)
        self.assertNotIn('Review component 0', '\n'.join(frames[0]))
        self.assertIn('Review component 0', '\n'.join(frames[1]))
        self.assertEqual(frames[1], frames[2])
        self.assertIn('└' + '─' * 41 + '┘', frames[1])

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

    def test_completed_elapsed_freezes_and_retains_task(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(status='completed', finished_at=185,
                                     activity='Palette and readability checks passed')
        before = ui.dashboard(snapshot, 48, now=200)
        after = ui.dashboard(snapshot, 48, now=10000, show_completed=True)
        self.assertIn(('  COMPLETED · 1m 25s', 'green'), before)
        self.assertIn(('  COMPLETED · 1m 25s', 'green'), after)
        self.assertIn('Review the active theme palette', '\n'.join(line for line, _ in after))
        self.assertNotIn('checks passed', '\n'.join(line for line, _ in after))

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

    def test_missing_task_uses_readable_name_instead_of_latest_prose(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(task='', name='nym_panel-styling',
                                     activity='Implemented Nym consolidation: - Shared colors')
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 60, now=200))
        self.assertIn('Nym panel styling', text)
        self.assertNotIn('Implemented', text)

    def test_task_wrapping_aligns_continuations_and_preserves_unicode(self):
        snapshot = self.snapshot()
        snapshot['agents'][0]['task'] = 'Review 界面 spacing and cafe\u0301 controls'
        rows = ui.dashboard(snapshot, 24, now=200)
        description = [line for line, role in rows if role == 'foreground' and line.startswith('  ')]
        self.assertEqual(description, ['  Review 界面 spacing', '  and cafe\u0301 controls'])
        self.assertTrue(all(ui.cell_width(line) <= 24 for line in description))

    def test_tiny_and_wide_character_layout_remains_in_bounds(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(name='界面 e\u0301 ' * 20,
                                     task='🔍 分析 ' * 100)
        for width in (0, 1, 2, 3, 8, 24, 48, 120):
            with self.subTest(width=width):
                rows = ui.dashboard(snapshot, width, now=200)
                self.assertTrue(all(ui.cell_width(line) <= width for line, _ in rows))
                self.assertLess(len(rows), 15)

    def test_terminal_escapes_bidi_and_controls_never_reach_output(self):
        snapshot = self.snapshot()
        snapshot['agents'][0].update(
            name='\x1b]2;hostile title\x07review\x1b[31m\x1b[0m',
            task='OK\x00\x1b]52;c;hidden\x1b\\\u202e\u2066\n\tchecking')
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 60, now=200))
        self.assertIn('review', text)
        self.assertIn('OK checking', text)
        for forbidden in ('\x1b', '\x00', '\x07', '\u202e', '\u2066', 'hostile title', 'hidden'):
            self.assertNotIn(forbidden, text)

    def test_huge_agent_list_and_task_are_bounded(self):
        snapshot = self.snapshot()
        snapshot['agents'][0]['task'] = 'very long task ' * 20000
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

    def test_sidebar_padding_and_fixed_bars_survive_scrolling(self):
        screen = Mock()
        screen.getmaxyx.return_value = (8, 48)
        screen.getch.side_effect = [ord('j'), ord('q')]
        frames = []
        def save_frame():
            frames.append([call.args for call in screen.addstr.call_args_list])
            screen.addstr.reset_mock()
        screen.refresh.side_effect = save_frame
        styles = dict.fromkeys(ui.DEFAULT_PALETTE, 0)
        styles.update(header=1, header_prefix=2, footer=3)
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'read_palette', return_value=ui.DEFAULT_PALETTE), \
             patch.object(ui, '_styles', return_value=styles):
            ui._screen(screen, Mock(return_value=self.snapshot()), None, None)
        for frame in frames:
            self.assertIn((0, 0, ' ' * 47, 1), frame)
            self.assertIn((0, 2, '// A G E N T S', 1), frame)
            self.assertIn((0, 2, '//', 2), frame)
            self.assertIn((7, 0, ' ' * 47, 3), frame)
            self.assertIn((7, 2, '↑↓ scroll · h history · r refresh · q close', 3), frame)
            self.assertTrue(all(column == 2 for row, column, _, _ in frame if 1 <= row < 7))
            self.assertTrue(all(column + ui.cell_width(text) <= 47
                                for _, column, text, _ in frame))
        self.assertEqual([call for call in frames[0] if call[0] < 4],
                         [call for call in frames[1] if call[0] < 4])
        self.assertNotEqual([call for call in frames[0] if 4 <= call[0] < 7],
                            [call for call in frames[1] if 4 <= call[0] < 7])

    def test_resize_preserves_draw_bounds_and_exit(self):
        screen = Mock()
        dimensions = iter([(12, 60), (8, 48), (5, 24), (2, 3), (1, 1)])
        current = (0, 0)
        def resize():
            nonlocal current
            current = next(dimensions)
            return current
        def draw(row, column, text, style):
            height, columns = current
            self.assertLess(row, height)
            self.assertGreaterEqual(column, 0)
            self.assertLessEqual(column + ui.cell_width(text), columns - 1)
        screen.getmaxyx.side_effect = resize
        screen.addstr.side_effect = draw
        screen.getch.side_effect = [ui.curses.KEY_RESIZE] * 4 + [ord('q')]
        snapshot = self.snapshot()
        snapshot['agents'][0]['name'] = '界面 e\u0301 ' * 20
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'read_palette', return_value=ui.DEFAULT_PALETTE), \
             patch.object(ui, '_styles', return_value=dict.fromkeys(
                 [*ui.DEFAULT_PALETTE, 'header', 'header_prefix', 'footer'], 0)):
            ui._screen(screen, Mock(return_value=snapshot), None, None)
        self.assertEqual(screen.refresh.call_count, 5)

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
        self.assertIn('  Review the active theme palette', rendered)
        self.assertNotIn('  Recovered result', rendered)
        self.assertIn('▾ Recently completed (1) · h hide', rendered)
        on_refresh.assert_not_called()


if __name__ == '__main__':
    unittest.main()
