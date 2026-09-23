"""Projects panel rendering and ATLAS layout invariants."""
from pathlib import Path
import sys
import signal
import threading
import time
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
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
        self.assertIn('// P R O J E C T S', text)
        self.assertRegex(text, r'Ahead of upstream\s+2')
        self.assertRegex(text, r'Upstream changes\s+1')
        self.assertIn('cached refs', text)
        self.assertIn('staged.txt', text)
        self.assertIn('new file.txt', text)

    def test_history_keeps_projects_header_and_shows_local_sources(self):
        rows = ui.dashboard(SNAPSHOT, 60, page=2)
        text = '\n'.join(line for line, _ in rows)
        self.assertEqual(rows[0][0], '// P R O J E C T S')
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
