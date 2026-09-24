"""Ports panel rendering, input and asynchronous collection behavior."""
from pathlib import Path
import curses
import signal
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_panel import cell_width, draw_panel_frame, read_palette
from atlas_ports import ui


SNAPSHOT = {'available': True, 'errors': [], 'omitted': 0, 'listeners': [
    {'id': 'tcp1', 'protocol': 'tcp', 'address': '127.0.0.1', 'port': 3000,
     'endpoint': '127.0.0.1:3000', 'scope': 'loopback', 'service': 'web.service',
     'uid': 1000, 'account': 'alice',
     'owners': [{'name': 'node', 'pid': 42, 'service': 'web.service'}]},
    {'id': 'udp1', 'protocol': 'udp', 'address': '::', 'port': 5353,
     'endpoint': '[::]:5353', 'scope': 'wildcard', 'service': None, 'owners': [],
     'uid': 65534, 'account': None},
]}


def rendered(snapshot=SNAPSHOT, width=60, page=1, query=''):
    return '\n'.join(row for row, _ in ui.dashboard(snapshot, width, page, query))


class Screen:
    def __init__(self, keys=(), size=(30, 60)):
        self.keys = iter(keys)
        self.size = size
        self.draws = []
    def keypad(self, value): pass
    def timeout(self, value): pass
    def bkgd(self, *args): pass
    def refresh(self): pass
    def clearok(self, value): pass
    def erase(self): self.draws = []
    def getmaxyx(self): return self.size
    def get_wch(self): return next(self.keys)
    def addstr(self, row, col, text, style):
        height, width = self.size
        assert 0 <= row < height
        assert col + cell_width(text) < width
        self.draws.append((row, col, text))


class PortsUiTests(unittest.TestCase):
    def test_default_tcp_and_other_pages(self):
        text = rendered()
        self.assertIn('// P O R T S   &   S E R V I C E S', text)
        self.assertIn('127.0.0.1:3000', text)
        self.assertIn('node · PID 42', text)
        self.assertEqual(text.count('web.service'), 1)
        self.assertNotIn('5353', text)
        self.assertIn('5353', rendered(page=2))
        self.assertNotIn('3000', rendered(page=2))
        self.assertIn('3000', rendered(page=3))
        self.assertIn('5353', rendered(page=3))
        self.assertIn('Process / PID restricted or unavailable', rendered(page=2))
        self.assertIn('ALL INTERFACES', rendered(page=2))

    def test_account_names_and_numeric_fallback_are_explicit(self):
        self.assertIn('Account  alice · UID 1000', rendered())
        self.assertIn('Account  UID 65534', rendered(page=2))
        data = dict(SNAPSHOT, listeners=[dict(SNAPSHOT['listeners'][0], uid=0, account='root')])
        self.assertIn('Account  root · UID 0', rendered(data))

    def test_admin_live_labels_and_unknown_process_details(self):
        data = dict(SNAPSHOT, elevated=True, captured_at=1700000000)
        text = rendered(data, page=2)
        self.assertIn('ADMIN LIVE', text)
        self.assertIn('Updated', text)
        self.assertIn('Refreshing · r returns to your account', text)
        self.assertIn('Process / PID unavailable', text)
        self.assertNotIn('restricted', text)

    def test_filter_uses_full_fields_case_insensitively(self):
        for query in ('3000', '127.0.0', 'NODE', 'WEB.Service', '42', 'ALICE', '1000'):
            with self.subTest(query=query):
                self.assertIn('127.0.0.1:3000', rendered(query=query))
        self.assertIn('No matching sockets', rendered(query='unknown'))

    def test_unavailable_is_distinct_from_empty_and_loading(self):
        text = rendered({'available': False, 'errors': ['ss failed']})
        self.assertIn('Socket data unavailable', text)
        self.assertIn('ss failed', text)
        self.assertNotIn('No listening', text)
        self.assertIn('No listening', rendered(dict(SNAPSHOT, listeners=[])))
        self.assertIn('LOADING', rendered({'loading': True}))
        self.assertIn('REFRESHING', rendered(dict(SNAPSHOT, loading=True)))

    def test_partial_collection_does_not_claim_missing_protocol_is_empty(self):
        data = dict(SNAPSHOT, listeners=SNAPSHOT['listeners'][:1],
                    partial=True, errors=['Socket query exceeded its time limit'])
        text = rendered(data, page=2)
        self.assertIn('PARTIAL', text)
        self.assertIn('No matches in collected data', text)
        self.assertNotIn('No UDP sockets', text)
        self.assertIn('time limit', text)

    def test_sanitizes_and_clips_all_pages(self):
        listener = dict(SNAPSHOT['listeners'][0], endpoint='\x1b[31m界' * 50 + '\x00',
                        owners=[{'name': 'bad\x1b[2J\x00', 'pid': 5}])
        data = dict(SNAPSHOT, listeners=[listener], errors=['\x1b[31mbad\x00'], omitted=10)
        for page in (1, 2, 3):
            for width in (0, 1, 8, 24, 43, 48, 55, 60):
                rows = ui.dashboard(data, width, page, '\x1b[31m')
                self.assertTrue(all(cell_width(text) <= width for text, _ in rows))
                self.assertNotIn('\x1b', str(rows))
                self.assertNotIn('\x00', str(rows))

    def test_shared_frame_handles_short_and_narrow_terminals(self):
        colors = {key: 0 for key in read_palette()}
        colors.update(header=0, header_prefix=0, footer=0)
        for height in (0, 1, 2, 4, 5, 12, 30):
            for columns in (0, 1, 8, 48, 60):
                screen = Screen(size=(height, columns))
                width = ui.layout(columns)[1]
                rows = ui.dashboard(SNAPSHOT, width, 3)
                offset, available, count, _ = draw_panel_frame(screen, rows, colors, 999, 'footer')
                self.assertEqual(offset, max(0, count - available))
                if height >= 5 and columns >= 48:
                    self.assertTrue(any(row == 0 and 'PORTS' in text.replace(' ', '') for row, _, text in screen.draws))
                    self.assertTrue(any(row == height - 1 and text == 'footer' for row, _, text in screen.draws))

    def test_filter_edit_cancel_clear_navigation_and_refresh(self):
        class Worker:
            active = False
            requests = 0
            def request(self): self.requests += 1
            def poll(self): return SNAPSHOT
            def wait_idle(self): return True
            def invalidate(self): pass
        worker = Worker()
        frames = []
        keys = ['2', '/', 'q', '\x1b', '3', '/', 'N', 'O', 'D', 'E', '\n',
                '/', '\x15', '\n', curses.KEY_END, curses.KEY_HOME, 'r', 'q']
        def frame(screen, rows, style, offset, footer):
            frames.append((rows, offset, footer))
            return (offset, 2, len(rows) - 4, 55)
        with patch.object(ui.curses, 'curs_set'), patch.object(ui, 'styles', return_value={'foreground': 0}), \
             patch.object(ui, 'draw_panel_frame', side_effect=frame):
            ui._screen_loop(Screen(keys), worker, None)
        self.assertIn('UDP', frames[1][0][1][0])
        self.assertIn('No matching', str(frames[3]))
        self.assertIn('5353', str(frames[4]))
        self.assertIn('Filter: NODE', str(frames[11]))
        self.assertNotIn('5353', str(frames[11]))
        self.assertIn('5353', str(frames[-1]))
        self.assertGreater(frames[-3][1], 0)
        self.assertEqual(frames[-2][1], 0)
        self.assertEqual(worker.requests, 2)


class BlockingCollector:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.calls = 0
        self.cancelled = False
    def collect(self):
        self.calls += 1
        self.started.set()
        self.release.wait(2)
        self.finished.set()
        return SNAPSHOT
    def cancel(self):
        self.cancelled = True
        self.release.set()


class WorkerTests(unittest.TestCase):
    def test_coalesces_refresh_and_cancels(self):
        collector = BlockingCollector()
        worker = ui._Worker(collector)
        self.addCleanup(worker.close)
        worker.request()
        self.assertTrue(collector.started.wait(1))
        for _ in range(10):
            worker.request()
        self.assertEqual(collector.calls, 1)
        self.assertIsNone(worker.poll())
        worker.close()
        self.assertTrue(collector.finished.wait(1))
        worker.request()
        self.assertEqual(collector.calls, 1)
        self.assertIsNone(worker.poll())

    def test_invalidating_discards_queued_and_later_inflight_admin_results(self):
        collector = BlockingCollector()
        worker = ui._Worker(collector)
        self.addCleanup(worker.close)
        worker.results.put(dict(SNAPSHOT, elevated=True))
        worker.request()
        self.assertTrue(collector.started.wait(1))
        worker.invalidate()
        self.assertIsNone(worker.poll())
        collector.release.set()
        self.assertTrue(worker.wait_idle(1))
        self.assertIsNone(worker.poll())
        worker.request()
        self.assertTrue(worker.wait_idle(1))
        self.assertEqual(worker.poll(), SNAPSHOT)

    def test_wait_idle_bounds_auth_wait_until_collection_finishes(self):
        collector = BlockingCollector()
        worker = ui._Worker(collector)
        self.addCleanup(worker.close)
        worker.request()
        self.assertTrue(collector.started.wait(1))
        self.assertFalse(worker.wait_idle(.01))
        collector.release.set()
        self.assertTrue(worker.wait_idle(1))
        self.assertTrue(collector.finished.is_set())
        self.assertEqual(worker.poll(), SNAPSHOT)

    def test_exceptions_are_reported(self):
        class Broken:
            def collect(self): raise OSError('query failed')
            def cancel(self): pass
        worker = ui._Worker(Broken())
        self.addCleanup(worker.close)
        worker.request()
        deadline = time.monotonic() + 1
        result = None
        while result is None and time.monotonic() < deadline:
            result = worker.poll()
            time.sleep(.001)
        self.assertFalse(result['available'])
        self.assertIn('query failed', rendered(result))

    def test_ui_remains_responsive_during_collection(self):
        collector = BlockingCollector()
        frames = []
        def frame(screen, rows, style, offset, footer):
            self.assertTrue(collector.started.wait(1))
            frames.append(rows)
            return (offset, 20, len(rows) - 4, 55)
        with patch.object(ui.curses, 'curs_set'), patch.object(ui, 'styles', return_value={'foreground': 0}), \
             patch.object(ui, 'draw_panel_frame', side_effect=frame):
            ui._screen(Screen(['2', '/', 'q', '\x1b', 'q']), collector, None)
        self.assertIn('UDP', frames[1][1][0])
        self.assertTrue(collector.cancelled)

    def test_signals_cancel_collector_and_restore_handlers(self):
        for signum in (signal.SIGHUP, signal.SIGTERM):
            collector = BlockingCollector()
            previous = signal.getsignal(signum)
            def loop(screen, worker, path, inspect_details=None, stop_admin=None, authenticate_on_open=False):
                worker.request()
                self.assertTrue(collector.started.wait(1))
                signal.raise_signal(signum)
            with patch.object(ui.curses, 'wrapper', side_effect=lambda fn, *args: fn(None, *args)), \
                 patch.object(ui, '_screen_loop', side_effect=loop):
                with self.assertRaises(SystemExit):
                    ui.run(collector)
            self.assertTrue(collector.cancelled)
            self.assertEqual(signal.getsignal(signum), previous)


class ElevationTests(unittest.TestCase):
    def test_terminal_is_restored_after_success_cancel_failure_and_signal(self):
        results = [dict(SNAPSHOT, elevated=True, captured_at=1700000000),
                   KeyboardInterrupt(), OSError('sudo failed'), SystemExit(129)]
        for result in results:
            with self.subTest(result=type(result).__name__):
                screen = Screen()
                callback = unittest.mock.Mock()
                if isinstance(result, BaseException):
                    callback.side_effect = result
                else:
                    callback.return_value = result
                with patch.object(ui.curses, 'def_prog_mode') as save, \
                     patch.object(ui.curses, 'endwin') as end, \
                     patch.object(ui.curses, 'reset_prog_mode') as reset, \
                     patch.object(ui.curses, 'curs_set') as cursor, \
                     patch.object(screen, 'keypad') as keypad, \
                     patch.object(screen, 'timeout') as timeout, \
                     patch.object(screen, 'clearok') as clear, patch('builtins.print'):
                    if isinstance(result, SystemExit):
                        with self.assertRaises(SystemExit):
                            ui._inspect_details(screen, callback)
                    else:
                        value = ui._inspect_details(screen, callback)
                        self.assertEqual(value['available'], isinstance(result, dict))
                        if isinstance(result, KeyboardInterrupt):
                            self.assertIn('cancelled', str(value))
                    save.assert_not_called()
                    end.assert_not_called()
                    reset.assert_not_called()
                    cursor.assert_called_once_with(0)
                    keypad.assert_called_once_with(True)
                    timeout.assert_called_once_with(100)
                    clear.assert_called_once_with(True)

    def run_loop(self, keys, details, admin_results=None, authenticate_on_open=False):
        class Worker:
            active = False
            requests = 0
            current = SNAPSHOT
            pending = None
            def request(self):
                self.requests += 1
                if self.current.get('elevated') and admin_results:
                    self.current = admin_results.pop(0)
                self.pending = self.current
                if not self.current.get('elevated') and self.current.get('notices'):
                    self.current = SNAPSHOT
            def poll(self):
                result, self.pending = self.pending, None
                return result
            def wait_idle(self): return True
            def invalidate(self): self.pending = None
            def disable(self): self.current = SNAPSHOT
        worker = Worker()
        frames = []
        def frame(screen, rows, style, offset, footer):
            if footer != 'Waiting for desktop authentication…':
                frames.append((rows, footer, worker.requests, offset))
            return (offset, 20, len(rows) - 4, 55)
        def authenticate(screen, callback):
            result = details.pop(0)
            worker.current = result if result.get('elevated') else SNAPSHOT
            return result
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'styles', return_value={'foreground': 0}), \
             patch.object(ui, 'draw_panel_frame', side_effect=frame), \
             patch.object(ui, '_inspect_details', side_effect=authenticate) as inspect, \
             patch.object(ui.time, 'monotonic', side_effect=range(0, 100, 3)):
            ui._screen_loop(Screen(keys), worker, None, lambda: None, worker.disable, authenticate_on_open)
        return frames, inspect

    def test_open_authenticates_once_before_polling_and_cancel_stays_in_user_mode(self):
        for details in (dict(SNAPSHOT, elevated=True),
                        {'available': False, 'errors': ['Authentication cancelled.']}):
            with self.subTest(elevated=details.get('elevated', False)):
                frames, inspect = self.run_loop(['j', 'q'], [details],
                                               authenticate_on_open=True)
                inspect.assert_called_once()
                self.assertEqual(frames[0][2], 0)
                self.assertEqual('ADMIN LIVE' in str(frames[1]), bool(details.get('elevated')))
                if not details.get('elevated'):
                    self.assertIn('Authentication cancelled.', str(frames[1]))
                    self.assertIn('127.0.0.1:3000', str(frames[1]))

    def test_admin_live_refreshes_changed_sockets_without_reauthentication(self):
        first = dict(SNAPSHOT, elevated=True, captured_at=1700000000,
                     listeners=[dict(SNAPSHOT['listeners'][0], endpoint='ADMIN:9000')])
        second = dict(first, listeners=[dict(SNAPSHOT['listeners'][0], endpoint='NEW:9001')])
        frames, inspect = self.run_loop(['a', 'j', 'r', 'q'], [first], [first, second])
        self.assertIn('ADMIN LIVE', str(frames[1]))
        self.assertIn('ADMIN:9000', str(frames[1]))
        self.assertIn('NEW:9001', str(frames[2]))
        self.assertIn('a auth', frames[1][1])
        self.assertIn('r user', frames[1][1])
        self.assertIn('/ filter', frames[1][1])
        self.assertEqual([frame[2] for frame in frames], [1, 2, 3, 4])
        self.assertNotIn('ADMIN LIVE', str(frames[3]))
        self.assertIn('127.0.0.1:3000', str(frames[3]))
        inspect.assert_called_once()

    def test_expired_admin_session_returns_to_user_with_visible_notice(self):
        first = dict(SNAPSHOT, elevated=True, captured_at=1700000000)
        expired = dict(SNAPSHOT, elevated=False, notices=['Sudo access expired. Press a to authenticate.'])
        frames, inspect = self.run_loop(['a', 'j', 'j', 'r', 'q'], [first], [first, expired])
        self.assertIn('ADMIN LIVE', str(frames[1]))
        self.assertNotIn('ADMIN LIVE', str(frames[2]))
        self.assertIn('Sudo access expired', str(frames[2]))
        self.assertEqual(frames[2][3], 0)
        self.assertIn('Sudo access expired', str(frames[3]))
        self.assertEqual(str(frames[3]).count('Sudo access expired'), 1)
        self.assertNotIn('Sudo access expired', str(frames[4]))
        inspect.assert_called_once()

    def test_failed_or_cancelled_details_keep_live_data_and_show_notice(self):
        for error in ('Sudo details cancelled.', 'sudo failed'):
            frames, _ = self.run_loop(['a', 'j', 'q'],
                                     [{'available': False, 'errors': [error]}])
            self.assertIn(error, str(frames[1]))
            self.assertIn('127.0.0.1:3000', str(frames[1]))
            self.assertNotIn('ADMIN LIVE', str(frames[1]))
            self.assertEqual(frames[-1][2], 3)

    def test_authentication_begins_only_after_live_collection_finishes(self):
        collector = BlockingCollector()
        class ReleasingScreen(Screen):
            def get_wch(self):
                key = super().get_wch()
                if key == 'a':
                    collector.release.set()
                return key
        frames = []
        def frame(screen, rows, style, offset, footer):
            self.assertTrue(collector.started.wait(1))
            frames.append(rows)
            return (offset, 20, len(rows) - 4, 55)
        def authenticate(screen, callback):
            self.assertTrue(collector.finished.is_set())
            elevated = dict(SNAPSHOT, elevated=True, captured_at=1700000000)
            collector.collect = lambda: elevated
            return elevated
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'styles', return_value={'foreground': 0}), \
             patch.object(ui, 'draw_panel_frame', side_effect=frame), \
             patch.object(ui, '_inspect_details', side_effect=authenticate) as inspect:
            ui._screen(ReleasingScreen(['a', 'q']), collector, None, lambda: None)
        inspect.assert_called_once()
        self.assertEqual(collector.calls, 1)
        self.assertIn('ADMIN LIVE', str(frames[-1]))

    def test_return_to_user_invalidates_before_and_after_disabling_admin(self):
        events = []
        worker = unittest.mock.Mock(active=True)
        worker.poll.return_value = dict(SNAPSHOT, elevated=True)
        worker.invalidate.side_effect = lambda: events.append('invalidate')
        def disable(): events.append('disable')
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'styles', return_value={'foreground': 0}), \
             patch.object(ui, 'draw_panel_frame', return_value=(0, 20, 5, 55)):
            ui._screen_loop(Screen(['r', 'q']), worker, None, lambda: None, disable)
        self.assertEqual(events, ['invalidate', 'disable', 'invalidate'])

    def test_busy_live_worker_prevents_authentication(self):
        worker = unittest.mock.Mock(active=True)
        worker.poll.return_value = SNAPSHOT
        worker.wait_idle.return_value = False
        frames = []
        def frame(screen, rows, style, offset, footer):
            frames.append(rows)
            return (offset, 20, len(rows) - 4, 55)
        with patch.object(ui.curses, 'curs_set'), \
             patch.object(ui, 'styles', return_value={'foreground': 0}), \
             patch.object(ui, 'draw_panel_frame', side_effect=frame), \
             patch.object(ui, '_inspect_details') as inspect:
            ui._screen_loop(Screen(['a', 'q']), worker, None, lambda: None)
        inspect.assert_not_called()
        self.assertIn('Live collection is still finishing', str(frames[-1]))

    def test_failed_repeat_drops_admin_data_and_returns_to_user(self):
        first = dict(SNAPSHOT, elevated=True, captured_at=1700000000,
                     listeners=[dict(SNAPSHOT['listeners'][0], endpoint='ADMIN:9000')])
        frames, _ = self.run_loop(['a', 'a', 'q'],
                                 [first, {'available': False, 'errors': ['Cancelled']}])
        self.assertNotIn('ADMIN:9000', str(frames[-1]))
        self.assertNotIn('ADMIN LIVE', str(frames[-1]))
        self.assertIn('127.0.0.1:3000', str(frames[-1]))
        self.assertIn('Cancelled', str(frames[-1]))
        self.assertEqual(frames[-1][2], 3)

    def test_another_authentication_requires_another_explicit_action(self):
        first = dict(SNAPSHOT, elevated=True, captured_at=1700000000)
        second = dict(first, listeners=[dict(SNAPSHOT['listeners'][0], endpoint='SECOND:9000')])
        frames, inspect = self.run_loop(['a', 'a', 'q'], [first, second])
        self.assertEqual(inspect.call_count, 2)
        self.assertEqual(frames[-1][2], 3)
        self.assertIn('SECOND:9000', str(frames[-1]))


if __name__ == '__main__':
    unittest.main()
