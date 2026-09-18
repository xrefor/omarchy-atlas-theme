"""Service setup tests never contact systemd, sudo, Nym, or a real account."""
import importlib.machinery
import pathlib
import queue
import subprocess
import unittest
from unittest.mock import Mock, patch

vpn = importlib.machinery.SourceFileLoader(
    'vpn_service', str(pathlib.Path(__file__).resolve().parents[1] / 'components/apps/bin/atlas-vpn')
).load_module()


def state(active='inactive', enabled='disabled', load='loaded', error=''):
    return {'LoadState': load, 'ActiveState': active,
            'SubState': 'running' if active == 'active' else 'dead',
            'UnitFileState': enabled, 'error': error}


class ServiceTests(unittest.TestCase):
    def test_status_is_bounded_read_only_and_preserves_independent_states(self):
        result = Mock(returncode=0, stderr='', stdout=(
            'ActiveState=active\nSubState=running\nLoadState=loaded\nUnitFileState=disabled\n'))
        with patch.object(vpn.subprocess, 'run', return_value=result) as run:
            self.assertEqual(vpn.read_service(), state('active'))
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['/usr/bin/systemctl', '--system', '--no-pager', 'show',
                                  'nym-vpnd.service', '--property=LoadState,ActiveState,SubState,UnitFileState'])
        self.assertEqual(kwargs['timeout'], 3)

    def test_unavailable_missing_and_masked_remain_distinct(self):
        self.assertIn('not installed', vpn.service_blocker(state(load='not-found')))
        self.assertIn('masked', vpn.service_blocker(state(load='masked')))
        self.assertIn('masked', vpn.service_blocker(state(enabled='masked-runtime')))
        with patch.object(vpn.subprocess, 'run', side_effect=FileNotFoundError('systemctl')):
            self.assertIn('Unable to read', vpn.service_blocker(vpn.read_service()))
        with patch.object(vpn.subprocess, 'run', side_effect=subprocess.TimeoutExpired('systemctl', 3)):
            self.assertIn('Unable to read', vpn.service_blocker(vpn.read_service()))

    def test_start_and_enable_use_only_fixed_service_then_open_user_app(self):
        for action, commands, after in (
                ('start', ['start', 'nym-vpnd.service'], state('active')),
                ('enable', ['enable', '--now', 'nym-vpnd.service'], state('active', 'enabled'))):
            with self.subTest(action=action), \
                    patch.object(vpn, 'read_service', side_effect=[state(), after]) as read, \
                    patch.object(vpn.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
                    patch.object(vpn, 'open_app', return_value='App opened') as app:
                actual, message = vpn.change_service(action)
                self.assertEqual(actual, after)
                self.assertIn('App opened', message)
                self.assertEqual(read.call_count, 2)
                run.assert_called_once_with(
                    ['/usr/bin/sudo', '--', '/usr/bin/systemctl', '--system', '--no-pager'] + commands,
                    capture_output=True, text=True, timeout=120)
                app.assert_called_once_with()

    def test_failed_or_partial_change_never_opens_app(self):
        cases = [
            ('start', Mock(returncode=1, stderr='Denied', stdout=''), state()),
            ('start', Mock(returncode=0), state()),
            ('enable', Mock(returncode=0), state('active')),
            ('enable', Mock(returncode=0), state('active', 'enabled-runtime')),
            ('enable', Mock(returncode=0), state('inactive', 'enabled')),
        ]
        for action, result, after in cases:
            with self.subTest(action=action, after=after), \
                    patch.object(vpn, 'read_service', side_effect=[state(), after]), \
                    patch.object(vpn.subprocess, 'run', return_value=result), \
                    patch.object(vpn, 'open_app') as app:
                actual, message = vpn.change_service(action)
                self.assertEqual(actual, after)
                self.assertRegex(message, 'failed|could not be verified')
                app.assert_not_called()

    def test_cancel_timeout_and_exec_failure_reread_without_app(self):
        for error in (KeyboardInterrupt(), subprocess.TimeoutExpired('sudo', 120), FileNotFoundError('sudo')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(vpn, 'read_service', side_effect=[state(), state('active')]) as read, \
                    patch.object(vpn.subprocess, 'run', side_effect=error), \
                    patch.object(vpn, 'open_app') as app:
                actual, message = vpn.change_service('start')
                self.assertEqual(actual['ActiveState'], 'active')
                self.assertRegex(message, 'cancelled|failed')
                self.assertEqual(read.call_count, 2)
                app.assert_not_called()

    def test_blocked_or_unknown_actions_cannot_run_privileged_command(self):
        for action, before in [('stop', state()), ('start', state(load='not-found')),
                               ('start', state(enabled='masked')), ('enable', state(enabled='static')),
                               ('start', state(error='Failed to connect to bus'))]:
            with self.subTest(action=action, before=before), \
                    patch.object(vpn, 'read_service', return_value=before), \
                    patch.object(vpn.subprocess, 'run') as run, \
                    patch.object(vpn, 'open_app') as app:
                _, message = vpn.change_service(action)
                self.assertTrue(message)
                run.assert_not_called()
                app.assert_not_called()

    def test_app_is_unprivileged_detached_and_missing_or_failed_is_readable(self):
        process = Mock()
        process.wait.return_value = 0
        with patch.object(vpn.os.path, 'isfile', return_value=True), \
                patch.object(vpn.os, 'access', return_value=True), \
                patch.object(vpn.os, 'geteuid', return_value=1000), \
                patch.object(vpn.subprocess, 'Popen', return_value=process) as popen:
            self.assertIn('Log in or sign up', vpn.open_app())
            popen.assert_called_once_with(['/usr/bin/nym-vpn-app'], stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          start_new_session=True)
            process.wait.return_value = 1
            self.assertIn('exited with status 1', vpn.open_app())
        with patch.object(vpn.os.path, 'isfile', return_value=False), \
                patch.object(vpn.os, 'geteuid', return_value=1000), \
                patch.object(vpn.subprocess, 'Popen') as popen:
            self.assertIn('missing', vpn.open_app())
            popen.assert_not_called()
        with patch.object(vpn.os, 'geteuid', return_value=0), patch.object(vpn.subprocess, 'Popen') as popen:
            self.assertIn('without sudo', vpn.open_app())
            popen.assert_not_called()

    def test_confirmation_describes_persistence_and_possible_nym_autoconnect(self):
        start = '\n'.join(row for row, _ in vpn.service_rows(state(), 100, None, confirm='start'))
        enable = '\n'.join(row for row, _ in vpn.service_rows(state(), 100, None, confirm='enable'))
        self.assertIn('keep its existing startup setting', start)
        self.assertIn('every boot', enable)
        self.assertIn('auto-connect', enable)
        self.assertIn('CLI is missing', enable)

    def run_panel(self, initial, keys, binary=None, changed=None, backend_error=False):
        screen = Mock()
        screen.getmaxyx.return_value = (40, 100)
        screen.getch.side_effect = [ord(key) for key in keys]
        backend = Mock()
        backend.events = queue.Queue()
        if backend_error:
            backend.events.put(('error', 'Nym session ended'))
        with patch.object(vpn, 'read_service', return_value=initial), \
                patch.object(vpn, 'find_cli', return_value=binary), \
                patch.object(vpn, 'styles', return_value=dict.fromkeys(
                    [*vpn.ROW_ROLES.values(), 'header', 'header_prefix', 'footer'], 0)), \
                patch.multiple(vpn.curses, curs_set=Mock(), color_pair=Mock(return_value=0),
                               def_prog_mode=Mock(), endwin=Mock(), reset_prog_mode=Mock()), \
                patch.object(vpn, 'Backend', return_value=backend) as factory, \
                patch.object(vpn, 'change_service', return_value=changed or (initial, 'Done')) as change, \
                patch.object(vpn, 'open_app', return_value='App opened') as app:
            vpn.panel(screen, binary)
            return factory, change, app

    def test_stopped_missing_cli_panel_read_and_cancel_do_not_mutate_or_launch(self):
        for keys in ('qq', '2nqq', '1\x1bqq', 'rqq'):
            with self.subTest(keys=keys):
                backend, change, app = self.run_panel(state(), keys)
                backend.assert_not_called()
                change.assert_not_called()
                app.assert_not_called()

    def test_confirmed_setup_is_only_action_and_explicit_app_key_works_without_cli(self):
        backend, change, app = self.run_panel(state(), '2yqq', changed=(state('active', 'enabled'), 'Done'))
        change.assert_called_once_with('enable')
        app.assert_not_called()  # change_service owns the successful launch.
        backend.assert_not_called()
        _, change, app = self.run_panel(state(), 'oqq')
        change.assert_not_called()
        app.assert_called_once_with()

    def test_active_enabled_dashboard_opens_app_only_on_request(self):
        backend, change, app = self.run_panel(state('active', 'enabled'), 'oq', binary='fake-cli')
        backend.assert_called_once_with('fake-cli')
        change.assert_not_called()
        app.assert_called_once_with()

    def test_service_action_recovers_a_failed_cli_session(self):
        backend, change, app = self.run_panel(
            state('active'), '2yqq', binary='fake-cli',
            changed=(state('active', 'enabled'), 'Done'), backend_error=True)
        self.assertEqual(backend.call_count, 2)
        self.assertEqual(backend.return_value.close.call_count, 2)
        change.assert_called_once_with('enable')
        app.assert_not_called()


if __name__ == '__main__':
    unittest.main()
