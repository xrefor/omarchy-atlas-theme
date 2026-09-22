"""Frontier panel presents observed facts separately from monitor inference."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_frontier import ui
from atlas_panel import cell_width


SNAPSHOT = {
    'connected': True,
    'environment': 'Stillness',
    'chain_label': 'Sui Testnet',
    'chain_id': '4c78adac',
    'endpoint': 'https://fullnode.testnet.sui.io:443',
    'checkpoint': '18492731',
    'retrieved_at': 1_000,
    'wallet': '0x' + '12' * 32,
    'character': {'name': 'Xrefor', 'tribe_id': 1842,
                  'address': '0x' + '12' * 32, 'verified': True},
    'capabilities_count': 2,
    'balance': {'status': 'unavailable', 'reason': 'coin type not configured'},
    'assemblies': [
        {'id': '0x' + 'ab' * 32, 'name': 'Network Node 04',
         'type_name': 'Network Node', 'state': 'ONLINE', 'monitor': 'UPDATED',
         'version': '1843', 'digest': 'digest', 'transaction': 'tx-digest',
         'execution_status': 'SUCCESS', 'checkpoint': '18492730',
         'cap_id': '0x' + 'cd' * 32, 'custodian': '0x' + '56' * 32,
         'controlled': True},
        {'id': '0x' + 'ef' * 32, 'name': 'Gate 02',
         'type_name': 'Gate', 'state': 'OFFLINE', 'monitor': 'UNCHANGED',
         'version': '90', 'digest': 'digest2', 'cap_id': '0x' + '34' * 32},
    ],
    'activity': [{'timestamp': 980, 'title': 'Network Node 04 changed',
                  'detail': 'Version 1842 → 1843', 'role': 'observed'}],
}


class FrontierUiTests(unittest.TestCase):
    def rendered(self, page=1, width=55):
        return ui.dashboard(SNAPSHOT, width, page=page, now=1_005)

    def test_overview_separates_observed_and_monitor_states(self):
        text = '\n'.join(line for line, _ in self.rendered())
        self.assertIn('Network Node 04', text)
        self.assertIn('ONLINE', text)
        self.assertIn('UPDATED · v1843', text)
        self.assertIn('Capabilities held', text)
        self.assertIn('EVE Token', text)
        self.assertIn('UNAVAILABLE', text)

    def test_infrastructure_retains_provenance_identifiers(self):
        text = '\n'.join(line for line, _ in self.rendered(page=2, width=60))
        self.assertIn('Observed', text)
        self.assertIn('Monitor', text)
        self.assertIn('Version', text)
        self.assertIn('Object', text)
        self.assertIn('Capability', text)
        self.assertIn('Digest', text)
        self.assertIn('Previous transaction', text)
        self.assertIn('Object checkpoint', text)

    def test_activity_states_that_history_is_local(self):
        text = '\n'.join(line for line, _ in self.rendered(page=3))
        self.assertIn('Local evidence history', text)
        self.assertIn('Network Node 04 changed', text)
        self.assertIn('Version 1842 → 1843', text)
        self.assertIn('[OBSERVED]', text)

    def test_multiple_capabilities_and_zero_facts_are_explicit(self):
        first = dict(SNAPSHOT['assemblies'][0], cap_id=None,
                     cap_ids=['0x' + 'aa' * 32, '0x' + 'bb' * 32],
                     facts={'Connected assemblies': 0})
        snapshot = dict(SNAPSHOT, assemblies=[first])
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 80, page=2, now=1_005))
        self.assertIn('MULTIPLE — CONTROL AMBIGUOUS', text)
        self.assertIn('Capability 1', text)
        self.assertIn('Connected assemblies', text)
        self.assertIn('0', text)

    def test_zero_identity_and_checkpoint_values_are_not_unavailable(self):
        character = dict(SNAPSHOT['character'], tribe_id=0)
        first = dict(SNAPSHOT['assemblies'][0], checkpoint=0)
        snapshot = dict(SNAPSHOT, character=character, checkpoint=0, assemblies=[first])
        overview = '\n'.join(line for line, _ in ui.dashboard(snapshot, 70, page=1, now=1_005))
        detail = '\n'.join(line for line, _ in ui.dashboard(snapshot, 70, page=2, now=1_005))
        self.assertIn('TRIBE 0', overview)
        self.assertRegex(overview, r'Checkpoint\s+0')
        self.assertRegex(detail, r'Object checkpoint\s+0')

    def test_every_page_is_bounded_at_sidebar_and_narrow_widths(self):
        for page in (1, 2, 3):
            for width in (1, 8, 24, 43, 55, 60, 100):
                with self.subTest(page=page, width=width):
                    rows = ui.dashboard(SNAPSHOT, width, page=page, now=1_005)
                    self.assertTrue(all(cell_width(line) <= width for line, _ in rows))

    def test_escape_sequences_and_control_characters_are_removed(self):
        dirty = dict(SNAPSHOT, environment='\x1b[31mStill\x00ness\x1b[0m')
        text = '\n'.join(line for line, _ in ui.dashboard(dirty, 60, now=1_005))
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\x00', text)
        self.assertIn('STILLNESS', text)

    def test_detail_evidence_and_section_controls_are_removed(self):
        assembly = dict(SNAPSHOT['assemblies'][0],
                        name='Node\x1b[31m\nForged',
                        digest='digest\x1b[2J\x00hidden',
                        transaction='tx\nforged')
        dirty = dict(SNAPSHOT, assemblies=[assembly])
        text = '\n'.join(line for line, _ in
                         ui.dashboard(dirty, 80, page=2, now=1_005))
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\x00', text)
        self.assertIn('NODE FORGED', text)
        self.assertIn('digesthidden', text)
        self.assertIn('tx forged', text)

    def test_unavailable_snapshot_is_honest(self):
        snapshot = {'connected': False, 'environment': 'Stillness',
                    'error': 'World package verification failed'}
        text = '\n'.join(line for line, _ in ui.dashboard(snapshot, 55, now=1_005))
        self.assertIn('DATA UNAVAILABLE', text)
        self.assertIn('World package verification failed', text)
        self.assertNotIn('ONLINE', text)
        self.assertIn('collection incomplete', text)


if __name__ == '__main__':
    unittest.main()
