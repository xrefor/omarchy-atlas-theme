from pathlib import Path
import sys
import tempfile
import unittest

from components.apps.atlas_maintain.backend import (
    Collector, CommandResult, CommandRunner, LOCAL_UPGRADE_NOTE, latest_installed_kernel,
    parse_failed_units, parse_timers, parse_transaction, parse_upgrades,
)


class FakeRunner:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def run(self, argv, *, timeout, max_output):
        self.calls.append((tuple(argv), timeout, max_output))
        return self.results.get(tuple(argv), CommandResult(status='missing', returncode=None))


class MaintainBackendTests(unittest.TestCase):
    def test_parses_bounded_local_sources(self):
        log = '''[2026-09-20T10:00:00+0200] [ALPM] transaction started
[2026-09-20T10:00:01+0200] [ALPM] upgraded linux (1 -> 2)
[2026-09-20T10:00:02+0200] [ALPM] installed demo (1-1)
[2026-09-20T10:00:03+0200] [ALPM] transaction completed
'''
        transaction = parse_transaction(log)
        self.assertEqual(transaction['status'], 'completed')
        self.assertEqual(transaction['count'], 2)
        self.assertEqual(transaction['changes'][0]['package'], 'linux')
        self.assertEqual(parse_failed_units('● broken.service loaded failed failed Broken\n'),
                         ['broken.service'])
        timer = parse_timers(
            'Tue 2026-09-22 13:00:00 CEST  1h left  n/a  n/a  trim.timer trim.service\n')[0]
        self.assertEqual(timer['unit'], 'trim.timer')
        self.assertEqual(timer['activates'], 'trim.service')
        self.assertEqual(parse_upgrades('linux 1.0 -> 2.0\nnoise\n')[0]['available'], '2.0')

    def test_collects_without_refresh_or_mutating_commands(self):
        failed_system = ('systemctl', '--system', '--no-pager', '--plain', '--no-legend',
                         'list-units', '--all', '--state=failed')
        failed_user = ('systemctl', '--user', '--no-pager', '--plain', '--no-legend',
                       'list-units', '--all', '--state=failed')
        timer_system = ('systemctl', '--system', '--no-pager', '--plain', '--no-legend',
                        'list-timers', '--all')
        timer_user = ('systemctl', '--user', '--no-pager', '--plain', '--no-legend',
                      'list-timers', '--all')
        results = {
            failed_system: CommandResult('bad.service loaded failed failed Bad\n'),
            failed_user: CommandResult(''),
            timer_system: CommandResult('n/a n/a n/a n/a fstrim.timer fstrim.service\n'),
            timer_user: CommandResult(status='error', returncode=1),
            ('pacman', '-Qu'): CommandResult('linux 1 -> 2\n'),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = root / 'modules'
            modules.mkdir()
            (modules / '6.9.1-arch1-1').mkdir()
            (modules / '6.10.2-arch1-1').mkdir()
            (modules / 'latest').symlink_to('6.10.2-arch1-1')
            log = root / 'pacman.log'
            log.write_text('[x] [ALPM] transaction started\n[x] [ALPM] transaction completed\n')
            runner = FakeRunner(results)
            value = Collector(runner, modules=modules, pacman_log=log, clock=lambda: 123).collect()
        self.assertEqual(value['installed_kernel'], '6.10.2-arch1-1')
        self.assertEqual(value['failed']['system']['units'], ['bad.service'])
        self.assertEqual(value['timers']['system']['items'][0]['unit'], 'fstrim.timer')
        self.assertEqual(value['timers']['user']['status'], 'error')
        self.assertEqual(value['upgrades']['count'], 1)
        self.assertEqual(value['upgrades']['note'], LOCAL_UPGRADE_NOTE)
        commands = [call[0] for call in runner.calls]
        self.assertIn(('pacman', '-Qu'), commands)
        self.assertFalse(any('-Sy' in argument or argument in ('start', 'restart', 'enable')
                             for command in commands for argument in command))

    def test_missing_commands_and_files_are_explicit(self):
        runner = FakeRunner({})
        with tempfile.TemporaryDirectory() as directory:
            value = Collector(runner, modules=Path(directory) / 'missing',
                              pacman_log=Path(directory) / 'missing.log').collect()
        self.assertIsNone(value['installed_kernel'])
        self.assertEqual(value['upgrades']['status'], 'missing')
        self.assertIsNone(value['transaction'])
        self.assertEqual(value['failed']['system']['units'], [])
        self.assertEqual(value['failed']['user']['units'], [])
        self.assertEqual(value['timers']['system']['items'], [])
        self.assertEqual(value['upgrades']['items'], [])

    def test_latest_kernel_ignores_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '6.1').mkdir()
            (root / '99.0').symlink_to('6.1')
            self.assertEqual(latest_installed_kernel(root), '6.1')

    def test_runner_enforces_timeout_and_retained_output_limit(self):
        runner = CommandRunner()
        timed = runner.run([sys.executable, '-c', 'import time; time.sleep(1)'], timeout=.1)
        self.assertEqual(timed.status, 'timeout')
        large = runner.run([sys.executable, '-c', 'print("x" * 4096)'],
                           timeout=1, max_output=1024)
        self.assertEqual(large.status, 'truncated')
        self.assertEqual(len(large.output.encode()), 1024)


if __name__ == '__main__':
    unittest.main()
