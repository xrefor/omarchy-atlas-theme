from pathlib import Path
import tempfile
import unittest

from components.apps.atlas_system.backend import Collector


class SystemBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas-system-')
        self.root = Path(self.temporary.name)
        self.proc = self.root / 'proc'
        self.sys = self.root / 'sys'
        (self.proc / 'net').mkdir(parents=True)
        (self.proc / '123').mkdir()
        (self.sys / 'class/thermal/thermal_zone0').mkdir(parents=True)
        battery = self.sys / 'class/power_supply/BAT0'
        battery.mkdir(parents=True)
        (battery / 'type').write_text('Battery\n')
        (battery / 'capacity').write_text('73\n')
        (battery / 'status').write_text('Discharging\n')
        (self.sys / 'class/thermal/thermal_zone0/temp').write_text('57000\n')
        (self.proc / 'meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 400 kB\n')
        (self.proc / 'uptime').write_text('3600.00 0.00\n')
        (self.proc / 'loadavg').write_text('1.00 2.00 3.00 1/10 1\n')
        self.write_cpu(100, 50)
        self.write_network(1000, 2000)
        fields = ['S'] + ['0'] * 21
        fields[11], fields[12], fields[19], fields[21] = '100', '50', '10', '4'
        (self.proc / '123/stat').write_text('123 (worker secret-free) ' + ' '.join(fields) + '\n')

    def tearDown(self):
        self.temporary.cleanup()

    def write_cpu(self, total, idle):
        active = total - idle
        (self.proc / 'stat').write_text(f'cpu  {active} 0 0 {idle} 0 0 0 0 0 0\n')

    def write_network(self, received, sent):
        (self.proc / 'net/dev').write_text(
            'Inter-| Receive | Transmit\n face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n'
            f' eth0: {received} 0 0 0 0 0 0 0 {sent} 0 0 0 0 0 0 0\n')

    def test_collects_and_rates_kernel_data(self):
        ticks = iter((10.0, 12.0))
        collector = Collector(self.proc, self.sys, self.root, clock=lambda: next(ticks))
        first = collector.collect()
        self.assertIsNone(first['cpu_percent'])
        self.assertIsNone(first['network']['receive_rate'])
        self.assertEqual(first['memory']['percent'], 60)
        self.assertEqual(first['temperature'], 57)
        self.assertEqual(first['battery'], {'percent': 73, 'status': 'Discharging'})
        self.assertEqual(first['processes'][0]['command'], 'worker secret-free')
        self.write_cpu(200, 80)
        self.write_network(1400, 2600)
        fields = ['S'] + ['0'] * 21
        fields[11], fields[12], fields[19], fields[21] = '120', '50', '10', '4'
        (self.proc / '123/stat').write_text('123 (worker secret-free) ' + ' '.join(fields) + '\n')
        second = collector.collect()
        self.assertAlmostEqual(second['cpu_percent'], 70)
        self.assertEqual(second['network']['receive_rate'], 200)
        self.assertEqual(second['network']['send_rate'], 300)
        self.assertAlmostEqual(second['processes'][0]['cpu_percent'], 10)

    def test_missing_sources_degrade_without_crashing(self):
        collector = Collector(self.root / 'missing-proc', self.root / 'missing-sys', self.root)
        value = collector.collect()
        self.assertIsNone(value['cpu_percent'])
        self.assertIn('CPU counters unavailable', value['errors'])
        self.assertEqual(value['processes'], [])


if __name__ == '__main__':
    unittest.main()
