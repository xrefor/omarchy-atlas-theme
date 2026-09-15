import importlib.machinery
import pathlib
import tempfile
import unittest
from unittest.mock import Mock

vpn = importlib.machinery.SourceFileLoader('vpn', str(pathlib.Path(__file__).resolve().parents[1]/'components/apps/bin/atlas-vpn')).load_module()

class ProtocolTests(unittest.TestCase):
    def test_settings_readback_and_poisson_label(self):
        tunnel = ('IPv6: on\nTwo-hop: off\nMixnet traffic configuration: '
                  'average_packet_delay: Some(25), disable_poisson_rate: false, '
                  'disable_background_cover_traffic: false')
        self.assertEqual(vpn.setting_value(tunnel, 'average-packet-delay'), '25')
        self.assertEqual(vpn.display_setting(tunnel, 'average-packet-delay'), '25 ms')
        self.assertEqual(vpn.display_setting(tunnel, 'disable-real-traffic-poisson-rate'), 'on')
        session = Mock()
        session.command.side_effect = ['', tunnel.replace('false,', 'true,')]
        self.assertIn('saved', vpn.apply_setting(session, 'disable-real-traffic-poisson-rate', 'on'))
        self.assertEqual(vpn.display_setting(tunnel.replace('false,', 'true,'), 'disable-real-traffic-poisson-rate'), 'off')

    def test_custom_delay_validation_and_verification(self):
        for value in ('-1', 'auto', '1; disconnect', '4294967296', '1.5', ''):
            session = Mock()
            self.assertIn('Enter', vpn.apply_setting(session, 'average-packet-delay', value))
            session.command.assert_not_called()
        session = Mock()
        session.command.side_effect = ['', 'average_packet_delay: Some(25),']
        self.assertIn('saved', vpn.apply_setting(session, 'average-packet-delay', '25'))
        session = Mock()
        session.command.side_effect = ['Denied', 'average_packet_delay: None,']
        self.assertIn('Change failed: Denied', vpn.apply_setting(session, 'average-packet-delay', '25'))

    def test_refresh_during_connection_does_not_leave_stale_notice(self):
        data = {'status': '', 'tunnel': 'Two-hop: off', 'gateway': '', 'message': ''}
        pending = 'State: Connecting mix, selecting gateways, try #0'
        key, value = vpn.command_event('status', pending)
        data[key] = value
        data['status'] = 'State: Connected mix to 192.0.2.10'
        for detailed in (False, True):
            rendered = '\n'.join(line for line, _ in vpn.dashboard(data, 80, [], detailed))
            self.assertIn('Connected mix to 192.0.2.10', rendered)
            self.assertNotIn(pending, rendered)
            self.assertNotIn('COMMAND NOTICE', rendered)

    def test_command_status_and_errors_are_classified(self):
        self.assertEqual(vpn.command_event('connect', 'State: Connecting wg'),
                         ('status', 'State: Connecting wg'))
        self.assertEqual(vpn.command_event('connect', 'Permission denied'),
                         ('message', 'Permission denied'))
        self.assertEqual(vpn.command_event('connect', ''),
                         ('message', 'Connect requested'))

    def test_modes_use_verified_daemon_setting(self):
        for before, after, name in [('on', 'off', 'Mixnet'), ('off', 'on', 'dVPN')]:
            session = Mock()
            session.command.side_effect = ['Two-hop: '+before, '', 'Two-hop: '+after]
            self.assertIn(name+' selected', vpn.switch_mode(session))
            self.assertEqual(session.command.call_args_list[1].args,
                             ('tunnel set --two-hop '+after,))

    def test_mode_failure_and_unknown_setting(self):
        session = Mock()
        session.command.side_effect = ['Two-hop: on', 'Permission denied', 'Two-hop: on']
        self.assertIn('Mode change failed: Permission denied', vpn.switch_mode(session))
        session = Mock()
        session.command.return_value = 'Unavailable'
        self.assertIn('Mode unchanged', vpn.switch_mode(session))
        self.assertEqual(session.command.call_count, 1)

    def test_split_prompt_and_reuse(self):
        with tempfile.TemporaryDirectory() as root:
            fake = pathlib.Path(root)/'nym-vpnc'
            fake.write_text('''#!/usr/bin/env python3
import sys,time
sys.stdout.write('$');sys.stdout.flush();time.sleep(.05)
sys.stdout.write(' ');sys.stdout.flush()
for line in sys.stdin:
 print('State: Disconnected' if line.strip()=='status' else 'OK')
 sys.stdout.write('$ ');sys.stdout.flush()
''')
            fake.chmod(0o755)
            s = vpn.Session(str(fake))
            try:
                self.assertEqual(s.response(), '')
                self.assertEqual(s.command('status'), 'State: Disconnected')
                self.assertEqual(s.command('connect'), 'OK')
                self.assertEqual(s.command('status'), 'State: Disconnected')
            finally:
                s.close()
            self.assertIsNotNone(s.process.poll())

    def test_cli_exit_is_error(self):
        s = vpn.Session('/bin/false')
        try:
            with self.assertRaisesRegex(RuntimeError, 'session ended'):
                s.response(1)
        finally:
            s.close()

    def test_strip_control_sequences(self):
        self.assertEqual(vpn.clean('\x1b[31mState:\x1b[0m Disconnected\x00'), 'State: Disconnected')

if __name__ == '__main__':unittest.main()
