from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_maintain import ui
from atlas_panel import cell_width


SNAPSHOT = {
    'running_kernel': '6.9.1-arch1-1',
    'installed_kernel': '6.10.2-arch1-1',
    'kernel_current': False,
    'failed': {
        'system': {'status': 'ok', 'units': ['broken.service']},
        'user': {'status': 'ok', 'units': []},
    },
    'timers': {
        'system': {'status': 'ok', 'items': [
            {'unit': 'trim.timer', 'activates': 'trim.service', 'schedule': 'tomorrow'},
        ]},
        'user': {'status': 'error', 'items': []},
    },
    'upgrades': {'status': 'ok', 'count': 1,
                 'items': [{'package': 'linux', 'current': '1', 'available': '2'}],
                 'note': 'Local sync database only · no network refresh'},
    'transaction': {'timestamp': '2026-09-20', 'status': 'completed', 'count': 1,
                    'changes': [{'action': 'upgraded', 'package': 'linux'}]},
}


class MaintainUiTests(unittest.TestCase):
    def test_every_page_keeps_maintain_header_and_width(self):
        for page in (1, 2, 3):
            rows = ui.dashboard(SNAPSHOT, 32, page)
            self.assertEqual(rows[0][0], '// M A I N T A I N')
            self.assertTrue(all(cell_width(line) <= 32 for line, _ in rows))

    def test_health_labels_local_database_and_read_only_behavior(self):
        text = '\n'.join(line for line, _ in ui.dashboard(SNAPSHOT, 60, 1))
        self.assertIn('Local sync database only', text)
        self.assertIn('Reboot needed', text)
        self.assertIn('Read-only view', text)

    def test_timer_and_issue_pages_render_evidence(self):
        timers = '\n'.join(line for line, _ in ui.dashboard(SNAPSHOT, 60, 2))
        issues = '\n'.join(line for line, _ in ui.dashboard(SNAPSHOT, 60, 3))
        self.assertIn('trim.timer', timers)
        self.assertIn('Unavailable · ERROR', timers)
        self.assertIn('broken.service', issues)
        self.assertIn('never restarts', issues)

    def test_empty_snapshot_degrades_cleanly(self):
        for page in (1, 2, 3):
            self.assertTrue(ui.dashboard({}, 20, page))

    def test_collection_error_is_visible_and_sanitized_on_every_page(self):
        snapshot = dict(SNAPSHOT, collection_error='Collection\x1b[31m\nfailed\x00')
        for page in (1, 2, 3):
            text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 72, page))
            self.assertIn('COLLECTION ERROR', text)
            self.assertIn('Collection failed', text)
            self.assertNotIn('\x1b', text)
            self.assertNotIn('\x00', text)


if __name__ == '__main__':
    unittest.main()
