"""GraphQL parsing and evidence semantics for the Frontier monitor."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('frontier_backend', ROOT / 'components/apps/atlas_frontier/backend.py')
backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)

WALLET = '0x' + '11' * 32
PACKAGE = '0x' + '22' * 32
PROFILE = '0x' + '33' * 32
CHARACTER = '0x' + '44' * 32
CAP = '0x' + '55' * 32
ASSEMBLY = '0x' + '66' * 32
COIN = '0x' + '77' * 32 + '::eve::EVE'
URL = 'https://graphql.testnet.sui.io/graphql'
TYPE_ORIGINS = {name: PACKAGE for name in
    ('PlayerProfile', 'Character', 'OwnerCap', 'Assembly', 'Gate',
     'StorageUnit', 'NetworkNode')}


class FakeTransport:
    def __init__(self, handler): self.handler, self.calls = handler, []
    def query(self, operation, variables=None):
        self.calls.append((operation, variables or {})); return self.handler(operation, variables or {})


def move_node(identifier, object_type, fields, version='1', digest='digest-1', tx='tx-1'):
    return {'address': identifier, 'version': version, 'digest': digest,
        'owner': {'__typename': 'Shared'},
        'previousTransaction': {'digest': tx, 'effects': {'status': 'SUCCESS',
            'timestamp': '2026-09-20T00:00:00Z', 'checkpoint': {
            'sequenceNumber': '899', 'digest': 'checkpoint-899',
            'timestamp': '2026-09-20T00:00:00Z'}}},
        'asMoveObject': {'contents': {'type': {'repr': object_type}, 'json': fields}}}


def move_object_node(identifier, object_type, fields, version='1', digest='digest-1', tx='tx-1'):
    node = move_node(identifier, object_type, fields, version, digest, tx)
    node['contents'] = node.pop('asMoveObject')['contents']
    return node


class Scenario:
    def __init__(self, config, assembly=None, cap_pages=None, chain='stillness-chain'):
        self.config, self.chain = config, chain
        self.assembly = assembly or move_node(ASSEMBLY, config.world_type('Assembly'), {
            'id': ASSEMBLY, 'status': {'status': {'@variant': 'ONLINE'}},
            'metadata': {'name': 'Relay One'}}, '7', 'assembly-digest', 'assembly-tx')
        self.cap_pages = cap_pages

    def __call__(self, operation, variables):
        if operation == backend.ENVIRONMENT_QUERY:
            return {'chainIdentifier': self.chain, 'checkpoint': {'sequenceNumber': '900',
                    'digest': 'checkpoint-900', 'timestamp': '2026-09-20T00:00:01Z'}}
        if operation == backend.PACKAGE_QUERY:
            modules = {'PlayerProfile': 'character', 'Character': 'character',
                       'OwnerCap': 'access', 'Assembly': 'assembly', 'Gate': 'gate',
                       'StorageUnit': 'storage_unit', 'NetworkNode': 'network_node'}
            return {'object': {'address': variables['package'], 'asMovePackage': {
                    'typeOrigins': [{'module': module, 'struct': name,
                        'definingId': self.config.world_type_origins[name]}
                        for name, module in modules.items()],
                    'character': {'name': 'character'}, 'access': {'name': 'access'},
                    'assembly': {'name': 'assembly'}, 'gate': {'name': 'gate'},
                    'storage': {'name': 'storage_unit'}, 'node': {'name': 'network_node'}}}}
        if operation == backend.PROFILES_QUERY:
            profile = move_object_node(PROFILE, self.config.world_type('PlayerProfile'),
                                       {'character_id': CHARACTER})
            return {'address': {'objects': {'nodes': [profile], 'pageInfo': {
                    'hasNextPage': False, 'endCursor': None}}}}
        if operation == backend.SNAPSHOT_QUERY:
            if variables['address'] == CHARACTER:
                node = move_node(CHARACTER, self.config.world_type('Character'), {
                    'character_address': WALLET, 'tribe_id': 42, 'metadata': {'name': 'Rook'}})
            else: node = self.assembly
            return {'object': node}
        if operation == backend.CAPS_QUERY:
            if self.cap_pages is not None: return {'objects': self.cap_pages[variables.get('after')]}
            cap_type = (self.config.world_type('OwnerCap') + '<' +
                        self.config.world_type('Assembly') + '>')
            cap = move_node(CAP, cap_type, {'authorized_object_id': ASSEMBLY})
            return {'objects': {'nodes': [cap], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}
        if operation == backend.BALANCE_QUERY:
            return {'address': {'balance': {'totalBalance': '0', 'coinBalance': '0',
                    'addressBalance': '0', 'coinType': {'repr': COIN}}},
                    'coinMetadata': {'name': 'EVE Token', 'symbol': 'EVE', 'decimals': 9}}
        raise AssertionError(operation)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'state/frontier.json'
        self.config = backend.Config(wallet=WALLET, graphql_url=URL,
            expected_chain_identifier='stillness-chain', published_world_package_ids=(PACKAGE,),
            world_type_origins=TYPE_ORIGINS)

    def monitor(self, scenario=None, config=None):
        config = config or self.config; fake = FakeTransport(scenario or Scenario(config))
        return backend.Monitor(config=config, state_path=self.state, transport=fake,
                               clock=lambda: 100.0), fake

    def test_config_validates_public_identity_and_safe_endpoint(self):
        for bad in ('11' * 32, '0x1234', '0x' + 'zz' * 32):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'Sui address'):
                backend.Config(wallet=bad, graphql_url=URL,
                    expected_chain_identifier='chain', published_world_package_ids=(PACKAGE,),
                    world_type_origins=TYPE_ORIGINS)
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            backend.Config(wallet=WALLET, graphql_url='http://example.com/graphql',
                expected_chain_identifier='chain', published_world_package_ids=(PACKAGE,),
                world_type_origins=TYPE_ORIGINS)
        self.assertEqual(backend.Config(wallet=WALLET, graphql_url='http://127.0.0.1:8000/graphql',
            expected_chain_identifier='chain', published_world_package_ids=(PACKAGE,),
            world_type_origins=TYPE_ORIGINS).graphql_url,
            'http://127.0.0.1:8000/graphql')
        with self.assertRaisesRegex(ValueError, 'credentials'):
            backend.Config(wallet=WALLET, graphql_url='https://u:p@example/graphql',
                expected_chain_identifier='chain', published_world_package_ids=(PACKAGE,),
                world_type_origins=TYPE_ORIGINS)
        for bad_type in (PACKAGE + '::eve', PACKAGE + '::bad module::EVE',
                         PACKAGE + '::::EVE'):
            with self.subTest(bad_type=bad_type), self.assertRaisesRegex(ValueError, 'exact Move type'):
                backend.Config(wallet=WALLET, graphql_url=URL,
                    expected_chain_identifier='chain', published_world_package_ids=(PACKAGE,),
                    world_type_origins=TYPE_ORIGINS, coin_type=bad_type)

    def test_rate_limit_preserves_bounded_retry_after(self):
        transport = backend.GraphQLTransport(URL)
        limited = backend.error.HTTPError.__new__(backend.error.HTTPError)
        Exception.__init__(limited, URL, 429, 'limited')
        limited.code, limited.msg = 429, 'limited'
        limited.hdrs, limited.filename, limited.fp = {'Retry-After': '17'}, URL, None
        class Opener:
            def open(self, *_args, **_kwargs):
                raise limited
        transport.opener = Opener()
        with self.assertRaises(backend.RateLimitError) as caught:
            transport.query(backend.ENVIRONMENT_QUERY)
        self.assertEqual(caught.exception.retry_after, 17)
        caught.exception.__traceback__ = None

    def test_private_versioned_config_roundtrip_and_symlink_rejection(self):
        path = Path(self.temp.name) / 'config/frontier.json'
        backend.save_config(self.config, path)
        self.assertEqual(backend.load_config(path), self.config)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        data = json.loads(path.read_text()); self.assertEqual(data['version'], 2)
        self.assertNotIn('secret', json.dumps(data).lower())
        link = Path(self.temp.name) / 'link.json'; link.symlink_to(path)
        with self.assertRaises(backend.FrontierError): backend.load_config(link)
        data['version'] = 3; path.write_text(json.dumps(data))
        with self.assertRaisesRegex(backend.FrontierError, 'unsupported config'): backend.load_config(path)

    def test_legacy_package_config_is_rejected_as_ambiguous(self):
        path = Path(self.temp.name) / 'legacy.json'
        path.write_text(json.dumps({'version': 1, 'wallet': WALLET,
            'graphql_url': URL, 'expected_chain_identifier': 'stillness-chain',
            'world_package_ids': [PACKAGE]}))
        with self.assertRaisesRegex(backend.FrontierError,
                'legacy Frontier config is ambiguous'):
            backend.load_config(path)

    def test_upgraded_published_package_and_type_origin_are_not_conflated(self):
        published = '0x' + 'aa' * 32
        origin = '0x' + 'bb' * 32
        origins = {name: origin for name in TYPE_ORIGINS}
        config = backend.Config(wallet=WALLET, graphql_url=URL,
            expected_chain_identifier='stillness-chain',
            published_world_package_ids=(published,), world_type_origins=origins)
        monitor, fake = self.monitor(Scenario(config), config)
        result = monitor.poll()
        self.assertTrue(result['connected'], result['error'])
        self.assertEqual(result['assemblies'][0]['type'],
                         f'{origin}::assembly::Assembly')
        package_variables = next(value for operation, value in fake.calls
                                 if operation == backend.PACKAGE_QUERY)
        profile_variables = next(value for operation, value in fake.calls
                                 if operation == backend.PROFILES_QUERY)
        cap_variables = next(value for operation, value in fake.calls
                             if operation == backend.CAPS_QUERY)
        self.assertEqual(package_variables['package'], published)
        self.assertEqual(profile_variables['type'],
                         f'{origin}::character::PlayerProfile')
        self.assertEqual(cap_variables['type'], f'{origin}::access')

    def test_published_package_must_report_every_configured_type_origin(self):
        scenario = Scenario(self.config)
        def handler(operation, variables):
            data = scenario(operation, variables)
            if operation == backend.PACKAGE_QUERY:
                data['object']['asMovePackage']['typeOrigins'][0]['definingId'] = '0x' + '99' * 32
            return data
        result = backend.Monitor(config=self.config, state_path=self.state,
            transport=FakeTransport(handler), clock=lambda: 100).poll()
        self.assertIn('type origins do not match', result['error'])
        self.assertFalse(result['character']['verified'])

    def test_query_documents_are_named_and_read_only(self):
        documents = (backend.ENVIRONMENT_QUERY, backend.PACKAGE_QUERY, backend.PROFILES_QUERY,
                     backend.SNAPSHOT_QUERY, backend.CAPS_QUERY, backend.BALANCE_QUERY)
        self.assertEqual([doc.split()[1].split('(')[0] for doc in documents],
                         ['Environment', 'PackageProbe', 'Profiles', 'Snapshot', 'Caps', 'EveBalance'])
        self.assertTrue(all('mutation' not in doc.lower() for doc in documents))
        self.assertIn('ownerKind: OBJECT', backend.CAPS_QUERY)

    def test_complete_first_poll_is_unchanged_and_creates_baseline(self):
        result = self.monitor()[0].poll()
        self.assertTrue(result['connected'], result['error']); self.assertIsNone(result['error'])
        self.assertEqual(result['checkpoint'], 900); self.assertTrue(result['character']['verified'])
        self.assertEqual((result['character']['name'], result['character']['tribe_id']), ('Rook', 42))
        self.assertEqual(result['capabilities_count'], 1)
        self.assertTrue(result['baseline_created'])
        self.assertEqual(result['assemblies'][0]['monitor'], 'UNCHANGED')
        self.assertEqual(result['assemblies'][0]['state'], 'ONLINE')
        self.assertEqual(result['activity'], [])
        self.assertEqual(result['balance']['reason'], 'coin type is not configured')

    def test_chain_mismatch_hard_stops_before_package_or_account_queries(self):
        monitor, fake = self.monitor(Scenario(self.config, chain='wrong-chain'))
        result = monitor.poll()
        self.assertFalse(result['connected']); self.assertIn('chain identifier', result['error'])
        self.assertEqual(len(fake.calls), 1); self.assertFalse(self.state.exists())

    def test_package_module_probe_precedes_profile_claims(self):
        scenario = Scenario(self.config)
        def handler(operation, variables):
            if operation == backend.PACKAGE_QUERY:
                return {'object': {'address': PACKAGE,
                        'asMovePackage': {'character': {'name': 'character'}}}}
            return scenario(operation, variables)
        monitor = backend.Monitor(config=self.config, state_path=self.state,
            transport=FakeTransport(handler), clock=lambda: 100)
        result = monitor.poll()
        self.assertIn('missing required modules:', result['error'])
        self.assertIn('access', result['error'])
        self.assertFalse(result['character']['verified'])
        operations = [operation for operation, _ in monitor.reader.transport.calls]
        self.assertLess(operations.index(backend.PACKAGE_QUERY),
                        operations.index(backend.PROFILES_QUERY) if backend.PROFILES_QUERY in operations
                        else len(operations))

    def test_package_probe_is_cached_for_five_minutes(self):
        monitor, fake = self.monitor()
        self.assertTrue(monitor.poll()['connected'])
        self.assertTrue(monitor.poll()['connected'])
        package_calls = [operation for operation, _ in fake.calls
                         if operation == backend.PACKAGE_QUERY]
        self.assertEqual(len(package_calls), 1)

    def test_profile_character_and_control_types_are_exact(self):
        scenario = Scenario(self.config)
        def wrong_profile(operation, variables):
            data = scenario(operation, variables)
            if operation == backend.PROFILES_QUERY:
                data['address']['objects']['nodes'][0]['contents']['type']['repr'] = f'{PACKAGE}::character::Other'
            return data
        result = backend.Monitor(config=self.config, state_path=self.state,
            transport=FakeTransport(wrong_profile), clock=lambda: 100).poll()
        self.assertIn('no PlayerProfile', result['error'])

        def wrong_character(operation, variables):
            data = scenario(operation, variables)
            if operation == backend.SNAPSHOT_QUERY and variables['address'] == CHARACTER:
                data['object']['asMoveObject']['contents']['type']['repr'] = f'{PACKAGE}::character::Other'
            return data
        result = backend.Monitor(config=self.config, state_path=self.state,
            transport=FakeTransport(wrong_character), clock=lambda: 100).poll()
        self.assertIn('type does not match', result['error'])

    def test_character_wallet_must_match(self):
        scenario = Scenario(self.config)
        def handler(operation, variables):
            data = scenario(operation, variables)
            if operation == backend.SNAPSHOT_QUERY and variables['address'] == CHARACTER:
                data['object']['asMoveObject']['contents']['json']['character_address'] = '0x' + '99' * 32
            return data
        result = backend.Monitor(config=self.config, state_path=self.state,
            transport=FakeTransport(handler), clock=lambda: 100).poll()
        self.assertIn('character address does not match', result['error'])

    def test_explicit_character_bypasses_ambiguous_profile_but_still_verifies_wallet(self):
        config = backend.Config(wallet=WALLET, graphql_url=URL,
            expected_chain_identifier='stillness-chain', published_world_package_ids=(PACKAGE,),
            world_type_origins=TYPE_ORIGINS,
            character_id=CHARACTER)
        monitor, fake = self.monitor(Scenario(config), config)
        result = monitor.poll()
        self.assertTrue(result['character']['verified'], result['error'])
        self.assertFalse(any(operation == backend.PROFILES_QUERY for operation, _ in fake.calls))

    def test_cap_pagination_is_complete_before_comparison(self):
        cap_type = f'{PACKAGE}::access::OwnerCap<{PACKAGE}::assembly::Assembly>'
        cap = move_node(CAP, cap_type, {'authorized_object_id': ASSEMBLY})
        pages = {None: {'nodes': [], 'pageInfo': {'hasNextPage': True, 'endCursor': 'next'}},
                 'next': {'nodes': [cap], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}
        monitor, fake = self.monitor(Scenario(self.config, cap_pages=pages))
        self.assertEqual(monitor.poll()['capabilities_count'], 1)
        cursors = [variables['after'] for operation, variables in fake.calls if operation == backend.CAPS_QUERY]
        self.assertEqual(cursors, [None, 'next'])

    def test_partial_cap_enumeration_never_implies_transfer_or_replaces_baseline(self):
        self.monitor()[0].poll()
        pages = {None: {'nodes': [], 'pageInfo': {'hasNextPage': True, 'endCursor': 'same'}},
                 'same': {'nodes': [], 'pageInfo': {'hasNextPage': True, 'endCursor': 'same'}}}
        result = self.monitor(Scenario(self.config, cap_pages=pages))[0].poll()
        self.assertIn('pagination did not advance', result['error']); self.assertEqual(result['activity'], [])
        state = json.loads(self.state.read_text()); objects = next(iter(state['namespaces'].values()))['objects']
        self.assertIn(ASSEMBLY, objects)

    def test_nonassembly_owner_cap_is_counted_but_not_presented_as_assembly(self):
        cap_type = f'{PACKAGE}::access::OwnerCap<{PACKAGE}::character::Character>'
        cap = move_node(CAP, cap_type, {'authorized_object_id': CHARACTER})
        pages = {None: {'nodes': [cap], 'pageInfo': {
            'hasNextPage': False, 'endCursor': None}}}
        result = self.monitor(Scenario(self.config, cap_pages=pages))[0].poll()
        self.assertEqual(result['capabilities_count'], 1)
        self.assertEqual(result['assemblies'], [])

    def test_configured_watch_is_fetched_without_control_capability(self):
        watched = '0x' + '88' * 32
        config = backend.Config(wallet=WALLET, graphql_url=URL,
            expected_chain_identifier='stillness-chain', published_world_package_ids=(PACKAGE,),
            world_type_origins=TYPE_ORIGINS,
            watched_objects=({'id': watched, 'label': 'Home gate'},))
        scenario = Scenario(config)
        def handler(operation, variables):
            if operation == backend.SNAPSHOT_QUERY and variables['address'] == watched:
                return {'object': move_node(watched, f'{PACKAGE}::gate::Gate', {
                    'status': {'status': {'@variant': 'ONLINE'}}}, '2', 'gate-digest', 'gate-tx')}
            return scenario(operation, variables)
        result = backend.Monitor(config=config, state_path=self.state,
            transport=FakeTransport(handler), clock=lambda: 100).poll()
        watched_row = next(row for row in result['assemblies'] if row['id'] == watched)
        self.assertEqual(watched_row['name'], 'Home gate')
        self.assertTrue(watched_row['watched']); self.assertFalse(watched_row['controlled'])
        self.assertEqual(watched_row['state'], 'ONLINE')

    def test_one_unavailable_watch_does_not_hide_other_evidence(self):
        missing = '0x' + '99' * 32
        config = backend.Config(wallet=WALLET, graphql_url=URL,
            expected_chain_identifier='stillness-chain', published_world_package_ids=(PACKAGE,),
            world_type_origins=TYPE_ORIGINS,
            watched_objects=({'id': missing, 'label': 'Missing gate'},))
        scenario = Scenario(config)
        def handler(operation, variables):
            if operation == backend.SNAPSHOT_QUERY and variables['address'] == missing:
                return {'object': None}
            return scenario(operation, variables)
        result = backend.Monitor(config=config, state_path=self.state,
            transport=FakeTransport(handler), clock=lambda: 100).poll()
        self.assertTrue(result['connected'], result['error'])
        self.assertEqual(len(result['assemblies']), 2)
        unavailable = next(row for row in result['assemblies'] if row['id'] == missing)
        self.assertEqual(unavailable['monitor'], 'UNAVAILABLE')
        self.assertIn('snapshot', unavailable['reason'])
        self.assertEqual(next(row for row in result['assemblies'] if row['id'] == ASSEMBLY)['state'], 'ONLINE')

    def test_later_critical_failure_exposes_only_explicit_last_known_values(self):
        self.monitor()[0].poll()
        scenario = Scenario(self.config)
        def handler(operation, variables):
            if operation == backend.PACKAGE_QUERY:
                return {'object': None}
            return scenario(operation, variables)
        result = backend.Monitor(config=self.config, state_path=self.state,
            transport=FakeTransport(handler), clock=lambda: 110).poll()
        self.assertFalse(result['connected'])
        self.assertEqual(result['assemblies'][0]['monitor'], 'UNAVAILABLE')
        self.assertEqual(result['assemblies'][0]['last_known']['version'], '7')
        self.assertIsNone(result['assemblies'][0]['version'])
        self.assertEqual(result['activity'], [])

    def test_updates_and_complete_control_removal_have_distinct_roles(self):
        self.monitor()[0].poll()
        changed = move_node(ASSEMBLY, f'{PACKAGE}::assembly::Assembly', {
            'status': {'status': {'@variant': 'OFFLINE'}},
            'metadata': {'name': 'Relay One'}}, '8', 'new-digest', 'new-tx')
        update = self.monitor(Scenario(self.config, assembly=changed))[0].poll()
        self.assertEqual(update['assemblies'][0]['monitor'], 'UPDATED')
        self.assertEqual(update['assemblies'][0]['changed_fields'], ['version', 'digest', 'transaction'])
        self.assertEqual(update['activity'][0]['role'], 'observed')
        empty = {None: {'nodes': [], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}
        removed = self.monitor(Scenario(self.config, cap_pages=empty))[0].poll()
        self.assertEqual(removed['activity'][0]['role'], 'derived')
        self.assertEqual(removed['activity'][0]['title'], 'Control capability no longer held')

    def test_state_decoder_does_not_invent_status_from_legacy_fields(self):
        assembly = move_node(ASSEMBLY, f'{PACKAGE}::assembly::Assembly', {
            'is_online': True, 'metadata': {'name': 'Relay One'}}, '7')
        result = self.monitor(Scenario(self.config, assembly=assembly))[0].poll()
        self.assertEqual(result['assemblies'][0]['state'], 'UNAVAILABLE')

    def test_activity_history_survives_unchanged_polls(self):
        self.monitor()[0].poll()
        changed = move_node(ASSEMBLY, f'{PACKAGE}::assembly::Assembly', {
            'status': {'status': {'@variant': 'OFFLINE'}},
            'metadata': {'name': 'Relay One'}}, '8', 'new-digest', 'new-tx')
        update = self.monitor(Scenario(self.config, assembly=changed))[0].poll()
        self.assertEqual(update['assemblies'][0]['state'], 'OFFLINE')
        unchanged = self.monitor(Scenario(self.config, assembly=changed))[0].poll()
        self.assertEqual(unchanged['assemblies'][0]['monitor'], 'UNCHANGED')
        self.assertEqual(unchanged['activity'][0]['title'], 'Relay One changed')

    def test_switching_character_starts_a_distinct_baseline_without_transfer_alerts(self):
        first = backend.Config(wallet=WALLET, graphql_url=URL,
            expected_chain_identifier='stillness-chain',
            published_world_package_ids=(PACKAGE,), world_type_origins=TYPE_ORIGINS,
            character_id=CHARACTER)
        self.monitor(Scenario(first), first)[0].poll()
        other_character = '0x' + 'aa' * 32
        second = backend.Config(wallet=WALLET, graphql_url=URL,
            expected_chain_identifier='stillness-chain',
            published_world_package_ids=(PACKAGE,), world_type_origins=TYPE_ORIGINS,
            character_id=other_character)
        scenario = Scenario(second, cap_pages={None: {'nodes': [], 'pageInfo': {
            'hasNextPage': False, 'endCursor': None}}})
        def handler(operation, variables):
            if operation == backend.SNAPSHOT_QUERY and variables['address'] == other_character:
                return {'object': move_node(other_character, second.world_type('Character'), {
                    'character_address': WALLET, 'tribe_id': 43,
                    'metadata': {'name': 'Rook Two'}})}
            return scenario(operation, variables)
        result = backend.Monitor(config=second, state_path=self.state,
            transport=FakeTransport(handler), clock=lambda: 100).poll()
        self.assertTrue(result['baseline_created'])
        self.assertEqual(result['activity'], [])
        self.assertEqual(len(json.loads(self.state.read_text())['namespaces']), 2)

    def test_history_write_failure_keeps_current_observations_live(self):
        original = backend._atomic_json
        def fail_write(*_args, **_kwargs):
            raise OSError('read-only filesystem')
        backend._atomic_json = fail_write
        try:
            result = self.monitor()[0].poll()
        finally:
            backend._atomic_json = original
        self.assertTrue(result['connected'])
        self.assertIsNone(result['error'])
        self.assertEqual(result['assemblies'][0]['state'], 'ONLINE')
        self.assertTrue(any('HISTORY_WRITE_FAILED' in warning
                            for warning in result['warnings']))
        self.assertFalse(self.state.exists())

    def test_optional_exact_coin_balance_and_mismatch(self):
        config = backend.Config(wallet=WALLET, graphql_url=URL, expected_chain_identifier='stillness-chain',
            published_world_package_ids=(PACKAGE,), world_type_origins=TYPE_ORIGINS,
            coin_type=COIN)
        monitor, fake = self.monitor(Scenario(config), config)
        result = monitor.poll()
        self.assertEqual(result['balance']['amount'], '0')
        self.assertEqual(result['balance']['status'], 'available')
        self.assertEqual(result['balance']['decimals'], 9)
        variables = next(value for operation, value in fake.calls if operation == backend.BALANCE_QUERY)
        self.assertEqual(variables, {'wallet': WALLET, 'coinType': COIN})
        scenario = Scenario(config)
        def handler(operation, variables):
            data = scenario(operation, variables)
            if operation == backend.BALANCE_QUERY: data['address']['balance']['coinType']['repr'] = PACKAGE + '::eve::Fake'
            return data
        result = backend.Monitor(config=config, state_path=self.state,
            transport=FakeTransport(handler), clock=lambda: 100).poll()
        self.assertEqual(result['balance']['status'], 'UNAVAILABLE')
        self.assertIn('does not match', result['balance']['reason'])

        def no_metadata(operation, variables):
            data = scenario(operation, variables)
            if operation == backend.BALANCE_QUERY: data['coinMetadata'] = None
            return data
        raw = backend.Monitor(config=config, state_path=Path(self.temp.name) / 'raw-state.json',
            transport=FakeTransport(no_metadata), clock=lambda: 100).poll()['balance']
        self.assertTrue(raw['raw_units']); self.assertIsNone(raw['decimals'])

    def test_state_namespace_includes_environment_and_package_identity(self):
        self.monitor()[0].poll()
        other = backend.Config(wallet=WALLET, graphql_url=URL,
            expected_chain_identifier='stillness-chain', published_world_package_ids=(PACKAGE,),
            world_type_origins=TYPE_ORIGINS, environment='other')
        result = self.monitor(Scenario(other), other)[0].poll()
        self.assertTrue(result['baseline_created']); self.assertEqual(result['assemblies'][0]['monitor'], 'UNCHANGED')
        self.assertEqual(len(json.loads(self.state.read_text())['namespaces']), 2)


if __name__ == '__main__': unittest.main()
