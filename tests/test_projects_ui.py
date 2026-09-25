"""Git Status panel rendering and ATLAS layout invariants."""
from pathlib import Path
import sys
import signal
import shutil
import subprocess
import tempfile
import threading
import time
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
import atlas_panel as panel
from atlas_panel import cell_width
from atlas_projects import ui


SNAPSHOT = {
    'discovery_state': 'ok', 'status_available': True, 'history_available': True,
    'divergence_available': True, 'remote_check': {'state': 'never', 'checked_at': None},
    'path': '/work/project/subdir', 'is_git': True, 'repo_root': '/work/project',
    'repo_name': 'project', 'branch': 'main', 'detached': False,
    'head': 'a' * 40, 'upstream': 'origin/main', 'ahead': 2, 'behind': 1,
    'counts': {'staged': 1, 'unstaged': 1, 'untracked': 1},
    'changes': [
        {'path': 'staged.txt', 'status': 'A.', 'staged': True,
         'unstaged': False, 'untracked': False},
        {'path': 'modified.txt', 'status': '.M', 'staged': False,
         'unstaged': True, 'untracked': False},
        {'path': 'new file.txt', 'status': '??', 'staged': False,
         'unstaged': False, 'untracked': True},
    ],
    'changes_total': 3, 'changes_omitted': 0,
    'commits': [{'hash': 'a' * 40, 'short_hash': 'aaaaaaa', 'timestamp': 1_700_000_000,
                 'subject': 'Keep project facts local'}],
    'worktrees': [{'path': '/work/project', 'head': 'a' * 40, 'branch': 'main'},
                  {'path': '/work/review', 'head': 'b' * 40, 'detached': True}],
    'errors': [],
}


class ProjectsUiTests(unittest.TestCase):
    def test_overview_shows_repository_status_and_changed_files(self):
        text = '\n'.join(line for line, _ in ui.dashboard(SNAPSHOT, 55, page=1))
        self.assertIn('// G I T   S T A T U S', text)
        self.assertRegex(text, r'Ahead of upstream\s+2')
        self.assertRegex(text, r'Upstream changes\s+1')
        self.assertIn('cached refs', text)
        self.assertIn('staged.txt', text)
        self.assertIn('new file.txt', text)

    def test_history_keeps_git_status_header_and_shows_local_sources(self):
        rows = ui.dashboard(SNAPSHOT, 60, page=2)
        text = '\n'.join(line for line, _ in rows)
        self.assertEqual(rows[0][0], '// G I T   S T A T U S')
        self.assertIn('HISTORY', rows[1][0])
        self.assertIn('/work/review', text)
        self.assertIn('Keep project facts local', text)
        self.assertIn('f checks the tracked remote', text)

    def test_non_git_state_is_functional_and_explicit(self):
        text = '\n'.join(line for line, _ in ui.dashboard(
            {'discovery_state': 'not_repo', 'path': '/work/plain', 'repo_name': 'plain', 'is_git': False, 'errors': []},
            48, page=1))
        self.assertIn('NO GIT REPOSITORY', text)
        self.assertIn('/work/plain', text)

    def test_every_page_is_bounded_at_sidebar_and_narrow_widths(self):
        dirty = dict(SNAPSHOT, repo_name='\x1b[31mproject\x00')
        for page in (1, 2):
            for width in (1, 8, 24, 43, 48, 55, 60, 100):
                with self.subTest(page=page, width=width):
                    rows = ui.dashboard(dirty, width, page=page)
                    self.assertTrue(all(cell_width(line) <= width for line, _ in rows))
                    self.assertNotIn('\x1b', '\n'.join(line for line, _ in rows))
                    self.assertNotIn('\x00', '\n'.join(line for line, _ in rows))

    def test_failures_never_claim_clean_or_empty_history(self):
        snapshot = dict(SNAPSHOT, status_available=False, history_available=False,
                        divergence_available=False, changes=[], commits=[], ahead=None, behind=None)
        overview = '\n'.join(line for line, _ in ui.dashboard(snapshot, 60))
        history = '\n'.join(line for line, _ in ui.dashboard(snapshot, 60, 2))
        self.assertNotIn('Working tree clean', overview)
        self.assertRegex(overview, r'Uncommitted files\s+UNKNOWN')
        self.assertRegex(overview, r'Ahead of upstream\s+UNKNOWN')
        self.assertNotIn('No commits yet', history)
        self.assertIn('Commit history unavailable', history)

    def test_remote_failure_preserves_last_success_but_stays_explicit(self):
        snapshot = dict(SNAPSHOT, remote_check={'state': 'failed', 'checked_at': 1700000000,
                                              'attempted_at': 1700000600, 'error': 'Network unavailable'})
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 60))
        self.assertRegex(text, r'Remote check\s+FAILED')
        self.assertIn('Last success', text)
        self.assertIn('Last attempt', text)
        self.assertIn('Network unavailable', text)

    def test_missing_upstream_detached_and_unknown_are_distinct(self):
        for update, expected in (({'upstream': None}, 'NO UPSTREAM'),
                                 ({'upstream': None, 'detached': True}, 'DETACHED HEAD'),
                                 ({'upstream': None, 'status_available': False}, 'UNKNOWN')):
            with self.subTest(expected=expected):
                text = '\n'.join(line for line, _ in ui.dashboard(dict(SNAPSHOT, **update), 60))
                self.assertRegex(text, r'Tracking\s+' + expected)

    def test_conflicts_and_unique_changed_file_count_are_visible(self):
        snapshot = dict(SNAPSHOT, changes_total=1,
                        counts={'staged': 1, 'unstaged': 1, 'untracked': 0, 'conflicts': 1})
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 48))
        self.assertRegex(text, r'Uncommitted files\s+1')
        self.assertIn('Resolve conflicts before handoff', text)


class FramedProjectsUiTests(unittest.TestCase):
    def test_shared_renderer_preserves_summary_labels_in_final_cells(self):
        class Screen:
            def __init__(self, columns):
                self.columns = columns
                self.erase()

            def erase(self):
                self.cells = [[' '] * self.columns for _ in range(30)]

            def getmaxyx(self):
                return (30, self.columns)

            def addstr(self, row, column, text, style):
                for character in text:
                    self.cells[row][column] = character
                    column += cell_width(character)

        styles = dict.fromkeys([*panel.DEFAULT_PALETTE, 'header', 'header_prefix', 'footer'], 0)
        for columns in (48, 60):
            with self.subTest(columns=columns):
                screen = Screen(columns)
                left, width = panel.layout(columns)
                rows = ui.dashboard(SNAPSHOT, width, style='framed')
                panel.draw_panel_frame(screen, rows, styles, 0, 'f remote · q close', style='framed')
                rendered = [''.join(line) for line in screen.cells]
                visible = '\n'.join(rendered)
                self.assertIn('TREE  3 changed', visible)
                self.assertIn('CACHED AHEAD  2   BEHIND  1', visible)
                self.assertIn('LAST SUCCESS  NEVER', visible)
                self.assertIn('┌', visible)
                self.assertIn('A.  staged.txt', '\n'.join(rendered))

    def test_checkout_and_cached_remote_facts_precede_files_at_sidebar_widths(self):
        snapshot = dict(SNAPSHOT, remote_check={'state': 'ok', 'checked_at': 1700000000})
        for width in (43, 55):
            with self.subTest(width=width):
                rows = ui.dashboard(snapshot, width, style='framed')
                lines = [line for line, _ in rows]
                self.assertIn('main', lines[1])
                text = '\n'.join(lines)
                self.assertIn('TREE  3 changed', text)
                self.assertIn('CACHED AHEAD  2   BEHIND  1', text)
                self.assertIn('REMOTE  SUCCEEDED', text)
                self.assertIn(ui._when(1700000000), text)
                first_file = next(index for index, line in enumerate(lines) if 'staged.txt' in line)
                self.assertLess(next(i for i, line in enumerate(lines)
                                     if 'LAST SUCCESS' in line), first_file)
                self.assertEqual(sum(line.startswith('┌') for line in lines), 3)
                for line, role in rows:
                    if role.startswith('card:'):
                        self.assertEqual(cell_width(line), width)

    def test_missing_counts_and_failed_queries_are_never_zero_or_clean(self):
        for update in ({'status_available': False, 'divergence_available': False},
                       {'changes_total': None, 'counts': {}, 'ahead': None, 'behind': None}):
            with self.subTest(update=update):
                lines = [line for line, _ in ui.dashboard(dict(SNAPSHOT, **update), 55,
                                                         style='framed')]
                text = '\n'.join(lines)
                self.assertIn('TREE  UNKNOWN', text)
                self.assertIn('CACHED AHEAD  UNKNOWN', text)
                self.assertIn('BEHIND  UNKNOWN', text)
                self.assertIn('CONFLICTS  UNKNOWN', text)
                self.assertIn('Changed files unavailable.', text)
                self.assertNotIn('CLEAN', text)
                self.assertNotIn('Working tree clean.', text)

    def test_remote_failure_and_previous_success_remain_distinct_on_both_pages(self):
        snapshot = dict(SNAPSHOT, remote_check={'state': 'failed', 'checked_at': 1700000000,
                                               'attempted_at': 1700000600,
                                               'error': 'Network unavailable'})
        for page in (1, 2):
            text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 43, page, style='framed'))
            self.assertIn('REMOTE  FAILED', text)
            self.assertIn('LAST SUCCESS  ' + ui._when(1700000000), text)
            self.assertIn('LAST ATTEMPT  ' + ui._when(1700000600), text)
            self.assertIn('Network unavailable', text)

    def test_conflicts_and_tracking_states_are_explicit(self):
        for update, expected in (({'upstream': None}, 'NO UPSTREAM'),
                                 ({'upstream': None, 'detached': True}, 'DETACHED HEAD'),
                                 ({'upstream': None, 'status_available': False}, 'UNKNOWN')):
            text = '\n'.join(line for line, _ in ui.dashboard(dict(SNAPSHOT, **update), 43,
                                                              style='framed'))
            self.assertIn('TRACKING  ' + expected, text)
        text = '\n'.join(line for line, _ in ui.dashboard(
            dict(SNAPSHOT, counts={'conflicts': 2}), 43, style='framed'))
        self.assertIn('CONFLICTS  2', text)
        self.assertIn('STAGED  UNKNOWN', text)

    def test_history_has_separate_commits_and_worktrees_and_keeps_failures(self):
        lines = [line for line, _ in ui.dashboard(SNAPSHOT, 55, 2, style='framed')]
        self.assertIn('HISTORY', lines[1])
        self.assertIn('main', lines[1])
        text = '\n'.join(lines)
        self.assertLess(text.index('RECENT LOCAL COMMITS'), text.index('WORKTREES'))
        self.assertIn('Keep project facts local', text)
        self.assertIn('/work/review', text)
        failed = '\n'.join(line for line, _ in ui.dashboard(
            dict(SNAPSHOT, history_available=False, commits=[]), 43, 2, style='framed'))
        self.assertIn('Commit history unavailable.', failed)
        self.assertNotIn('No commits yet.', failed)

    def test_framed_rows_are_bounded_and_long_file_paths_are_preserved_by_wrapping(self):
        path = 'src/' + '日本語/' * 10 + 'long filename.py'
        snapshot = dict(SNAPSHOT, changes=[{'status': '.M', 'path': path, 'unstaged': True}],
                        branch='\x1b[31mfeature\x00')
        for width in (0, 1, 8, 24, 43, 55, 60):
            for page in (1, 2):
                with self.subTest(width=width, page=page):
                    rows = ui.dashboard(snapshot, width, page, style='framed')
                    self.assertTrue(all(cell_width(line) <= width for line, _ in rows))
                    text = '\n'.join(line for line, _ in rows)
                    self.assertNotIn('\x1b', text)
                    self.assertNotIn('\x00', text)
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 43, style='framed'))
        self.assertIn('long filename.py', ' '.join(text.split()))
        self.assertNotIn('…', text)

    def test_classic_renderer_is_independent_of_installed_preference(self):
        with patch.object(ui, 'read_layout_style', return_value='framed'):
            for page, renderer in ((1, ui.overview), (2, ui.history)):
                rows = ui.dashboard(SNAPSHOT, 55, page)
                self.assertEqual(rows, [(ui.clip(line, 55), role)
                                        for line, role in renderer(SNAPSHOT, 55)])


@unittest.skipUnless(shutil.which('tmux'), 'tmux is not installed')
class FramedProjectsTerminalTests(unittest.TestCase):
    def test_real_terminal_preserves_summary_labels_on_both_pages_and_widths(self):
        with tempfile.TemporaryDirectory(prefix='atlas-git-ui-') as directory:
            base = Path(directory)
            socket, demo = base / 'tmux.sock', base / 'demo.py'
            apps = Path(__file__).resolve().parents[1] / 'components/apps'
            demo.write_text(
                'import sys\n'
                f'sys.path.insert(0, {str(apps)!r})\n'
                'import atlas_panel\n'
                'from atlas_projects import ui\n'
                'atlas_panel.read_layout_style = ui.read_layout_style = lambda: "framed"\n'
                f'snapshot = {SNAPSHOT!r}\n'
                'class Collector:\n'
                '    def collect(self): return snapshot\n'
                'ui.run(Collector())\n')

            def tm(*args):
                return subprocess.check_output(['tmux', '-S', str(socket), *args],
                                               text=True, stderr=subprocess.STDOUT)

            def capture_when(predicate):
                deadline, capture = time.monotonic() + 4, ''
                while time.monotonic() < deadline:
                    capture = tm('capture-pane', '-p')
                    if predicate(capture):
                        return capture
                    time.sleep(.05)
                self.fail('Expected Git Status content did not render:\n' + capture)

            try:
                try:
                    tm('-f', '/dev/null', 'new-session', '-d', '-x', '60', '-y', '35',
                       'python3', str(demo))
                except subprocess.CalledProcessError as error:
                    if 'Operation not permitted' in error.output or 'Permission denied' in error.output:
                        self.skipTest('sandbox does not allow a temporary tmux socket')
                    raise
                for columns in (60, 48):
                    tm('resize-window', '-x', str(columns), '-y', '35')
                    for page, expected in (('1', 'staged.txt'), ('2', 'Keep project facts local')):
                        tm('send-keys', page)
                        capture = capture_when(lambda text: expected in text and
                                               max(map(len, text.splitlines()), default=0) <= columns)
                        self.assertIn('TREE  3 changed', capture)
                        self.assertIn('CACHED AHEAD  2   BEHIND  1', capture)
                        self.assertIn('LAST SUCCESS  NEVER', capture)
                tm('send-keys', 'q')
            finally:
                subprocess.run(['tmux', '-S', str(socket), 'kill-server'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class BlockingCollector:
    path = '/work/test'

    def __init__(self):
        self.local_started = threading.Event()
        self.local_release = threading.Event()
        self.remote_started = threading.Event()
        self.remote_release = threading.Event()
        self.remote_finished = threading.Event()
        self.calls = []
        self.cancelled = False

    def collect(self):
        self.calls.append('local')
        self.local_started.set()
        self.local_release.wait(2)
        return dict(SNAPSHOT)

    def check_remote(self):
        self.calls.append('remote')
        self.remote_started.set()
        self.remote_release.wait(2)
        self.remote_finished.set()
        return dict(SNAPSHOT, remote_check={'state': 'ok'})

    def cancel(self):
        self.cancelled = True
        self.local_release.set()
        self.remote_release.set()


class WorkerTests(unittest.TestCase):
    def test_serializes_local_and_remote_and_coalesces_requests(self):
        collector = BlockingCollector()
        worker = ui._Worker(collector)
        self.addCleanup(worker.close)
        worker.request()
        self.assertTrue(collector.local_started.wait(1))
        for _ in range(5):
            worker.request('remote')
        self.assertTrue(worker.checking)
        self.assertEqual(collector.calls, ['local'])
        collector.local_release.set()
        self.assertTrue(collector.remote_started.wait(1))
        for _ in range(5):
            worker.request('remote')
            worker.request()
        collector.remote_release.set()
        self.assertTrue(collector.remote_finished.wait(1))
        deadline = time.monotonic() + 1
        while worker.checking and time.monotonic() < deadline:
            time.sleep(.001)
        self.assertEqual(collector.calls, ['local', 'remote'])
        self.assertEqual(worker.poll()['remote_check']['state'], 'ok')

    def test_collector_exception_replaces_previous_success(self):
        class Broken:
            def collect(self):
                raise OSError('query failed')
        worker = ui._Worker(Broken())
        self.addCleanup(worker.close)
        worker.request()
        deadline = time.monotonic() + 1
        result = None
        while result is None and time.monotonic() < deadline:
            result = worker.poll()
            time.sleep(.001)
        self.assertEqual(result['discovery_state'], 'unavailable')
        self.assertFalse(result['is_git'])
        self.assertNotIn('Working tree clean', str(ui.dashboard(result, 60)))

    def test_framed_controls_fit_and_end_uses_shared_visible_rows(self):
        for columns in (48, 60):
            screen = unittest.mock.Mock()
            screen.getmaxyx.return_value = (30, columns)
            screen.getch.side_effect = [ui.curses.KEY_END, ord('q')]
            worker = unittest.mock.Mock(checking=False)
            worker.poll.return_value = SNAPSHOT
            frames = []
            def frame(screen, rows, style, offset, footer):
                frames.append((offset, footer))
                return offset, 7, 70, columns - 5
            with patch.object(ui.curses, 'curs_set'), \
                    patch.object(ui, 'read_layout_style', return_value='framed'), \
                    patch.object(ui, 'styles', return_value={'foreground': 0}), \
                    patch.object(ui, 'draw_panel_frame', side_effect=frame):
                ui._screen_loop(screen, worker, None)
            self.assertEqual(frames[-1][0], 63)
            footer = frames[-1][1]
            self.assertEqual(len(footer), 2)
            self.assertTrue(all(cell_width(line) <= columns - 9 for line in footer))
            self.assertIn('f check remote', ' '.join(footer))

    def test_screen_navigation_and_close_while_fetch_blocks(self):
        collector = BlockingCollector()
        collector.local_release.set()
        keys = iter((ord('f'), ord('2'), ord('q')))
        rendered = []
        class Screen:
            def keypad(self, value): pass
            def timeout(self, value): pass
            def bkgd(self, *args): pass
            def refresh(self): pass
            def getmaxyx(self): return (30, 60)
            def getch(self):
                key = next(keys)
                if key == ord('2'):
                    if not collector.remote_started.wait(1):
                        raise AssertionError('remote worker did not start')
                return key
        def frame(screen, rows, style, offset, footer):
            rendered.append(rows)
            return (offset, 25, len(rows) - 4, 60)
        with patch.object(ui.curses, 'curs_set'), patch.object(ui, 'styles', return_value={'foreground': 0}), \
             patch.object(ui, 'draw_panel_frame', side_effect=frame):
            ui._screen(Screen(), collector, None)
        self.assertTrue(collector.cancelled)
        self.assertIn('HISTORY', rendered[-1][1][0])
        self.assertEqual(collector.calls, ['local', 'remote'])

    def test_terminal_signals_cancel_inflight_fetch_and_restore_handlers(self):
        for signum in (signal.SIGHUP, signal.SIGTERM):
            with self.subTest(signal=signum):
                collector = BlockingCollector()
                collector.local_release.set()
                handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGHUP, signal.SIGTERM)}

                def interrupted_loop(screen, worker, palette_path):
                    worker.request('remote')
                    self.assertTrue(collector.remote_started.wait(1))
                    signal.raise_signal(signum)
                    self.fail('signal did not unwind the screen')

                def wrapper(function, *args):
                    function(None, *args)

                with patch.object(ui.curses, 'wrapper', side_effect=wrapper), \
                     patch.object(ui, '_screen_loop', side_effect=interrupted_loop):
                    with self.assertRaises(SystemExit) as stopped:
                        ui.run(collector)
                self.assertEqual(stopped.exception.code, 128 + signum)
                self.assertTrue(collector.cancelled)
                self.assertTrue(collector.remote_finished.wait(1))
                for sig, handler in handlers.items():
                    self.assertEqual(signal.getsignal(sig), handler)


if __name__ == '__main__':
    unittest.main()
