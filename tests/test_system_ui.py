import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_system import ui
from atlas_panel import cell_width


SNAPSHOT = {
    'hostname': 'atlas', 'uptime_text': '2h 10m', 'kernel': 'test-kernel',
    'cpu_percent': None, 'load': [1.0, 2.0, 3.0],
    'memory': {'used': 512, 'total': 1024, 'percent': 50},
    'filesystem': {'used': 100, 'total': 1000, 'percent': 10},
    'network': {'received': 10, 'sent': 20, 'receive_rate': None, 'send_rate': None},
    'temperature': 81.5, 'battery': {'percent': 73, 'status': 'Discharging'},
    'processes': [{'pid': 42, 'command': 'worker', 'rss': 4096,
                   'cpu_seconds': 12.5, 'cpu_percent': 25.0}],
    'errors': [],
}


class SystemUiTests(unittest.TestCase):
    def test_overview_marks_initial_rates_and_respects_width(self):
        rows = ui.dashboard(SNAPSHOT, 32, 1)
        text = '\n'.join(line for line, _ in rows)
        self.assertIn('INITIALIZING', text)
        self.assertIn('Peak thermal zone', text)
        self.assertTrue(all(cell_width(line) <= 32 for line, _ in rows))

    def test_process_page_labels_current_cpu(self):
        rows = ui.dashboard(SNAPSHOT, 48, 2)
        text = '\n'.join(line for line, _ in rows)
        self.assertIn('current CPU and memory', text)
        self.assertIn('25.0%', text)
        self.assertIn('PID 42', text)
        self.assertIn('worker', text)

    def test_empty_snapshot_is_renderable(self):
        self.assertTrue(ui.dashboard({}, 20, 1))
        self.assertTrue(ui.dashboard({}, 20, 2))

    def test_kernel_and_process_controls_never_reach_output(self):
        snapshot = dict(SNAPSHOT, hostname='atlas\x1b[31m\nstation',
                        kernel='kernel\x00hidden',
                        processes=[dict(SNAPSHOT['processes'][0],
                                        command='worker\x1b[2J\nforged')])
        overview = '\n'.join(line for line, _ in ui.dashboard(snapshot, 80, 1))
        processes = '\n'.join(line for line, _ in ui.dashboard(snapshot, 80, 2))
        for text in (overview, processes):
            self.assertNotIn('\x1b', text)
            self.assertNotIn('\x00', text)
        self.assertIn('atlas station', overview)
        self.assertIn('kernelhidden', overview)
        self.assertIn('worker forged', processes)


if __name__ == '__main__':
    unittest.main()
