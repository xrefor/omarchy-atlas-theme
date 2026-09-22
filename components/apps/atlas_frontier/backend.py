"""Evidence-preserving, read-only EVE Frontier GraphQL monitor."""
from dataclasses import asdict, dataclass
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from urllib import error, parse, request

CONFIG_VERSION = 2
STATE_VERSION = 1
MAX_CONFIG_BYTES = 64 * 1024
MAX_STATE_BYTES = MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_PAGES = 20
ADDRESS = re.compile(r'0x[0-9a-fA-F]{64}\Z')
CHAIN_ID = re.compile(r'[A-Za-z0-9._:-]{1,128}\Z')

ENVIRONMENT_QUERY = '''query Environment {
  chainIdentifier
  checkpoint { sequenceNumber digest timestamp }
}'''
PACKAGE_QUERY = '''query PackageProbe($package: SuiAddress!) {
  object(address: $package) {
    address
    asMovePackage {
      version digest
      typeOrigins { module struct definingId }
      character: module(name: "character") { name }
      access: module(name: "access") { name }
      assembly: module(name: "assembly") { name }
      gate: module(name: "gate") { name }
      storage: module(name: "storage_unit") { name }
      node: module(name: "network_node") { name }
    }
  }
}'''
PROFILES_QUERY = '''query Profiles($owner: SuiAddress!, $type: String!, $after: String) {
  address(address: $owner) {
    objects(first: 50, after: $after, filter: {type: $type}) {
      pageInfo { hasNextPage endCursor }
      nodes { address version digest contents { type { repr } json }
        previousTransaction { digest effects { status timestamp checkpoint { sequenceNumber digest timestamp } } }
      }
    }
  }
}'''
SNAPSHOT_QUERY = '''query Snapshot($address: SuiAddress!) {
  object(address: $address) {
    address version digest owner { __typename }
    previousTransaction {
      digest effects { status timestamp checkpoint { sequenceNumber digest timestamp } }
    }
    asMoveObject { contents { type { repr } json } }
  }
}'''
CAPS_QUERY = '''query Caps($character: SuiAddress!, $type: String!, $after: String) {
  objects(first: 50, after: $after,
          filter: {owner: $character, ownerKind: OBJECT, type: $type}) {
    pageInfo { hasNextPage endCursor }
    nodes {
      address version digest owner { __typename }
      previousTransaction { digest effects { status timestamp checkpoint { sequenceNumber digest timestamp } } }
      asMoveObject { contents { type { repr } json } }
    }
  }
}'''
BALANCE_QUERY = '''query EveBalance($wallet: SuiAddress!, $coinType: String!) {
  address(address: $wallet) {
    balance(coinType: $coinType) {
      totalBalance coinBalance addressBalance coinType { repr }
    }
  }
  coinMetadata(coinType: $coinType) { name symbol decimals }
}'''


class FrontierError(Exception): pass
class GraphQLError(FrontierError): pass
class RateLimitError(GraphQLError):
    def __init__(self, retry_after=None):
        self.retry_after = retry_after
        suffix = f'; retry after {retry_after}s' if retry_after is not None else ''
        super().__init__('GraphQL endpoint rate limited the monitor' + suffix)


def _address(value, label='address'):
    if not isinstance(value, str) or not ADDRESS.fullmatch(value):
        raise ValueError(f'{label} must be a 0x-prefixed 32-byte Sui address')
    return value.lower()


def _endpoint(value):
    if not isinstance(value, str): raise ValueError('graphql_url must be a URL')
    url = parse.urlsplit(value)
    loopback = url.hostname in ('localhost', '127.0.0.1', '::1')
    if url.scheme != 'https' and not (url.scheme == 'http' and loopback):
        raise ValueError('graphql_url must use HTTPS (HTTP is allowed only for loopback)')
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('graphql_url must be a plain endpoint without credentials, query, or fragment')
    return value.rstrip('/')


def _move_type(value, label='Move type'):
    if (not isinstance(value, str) or len(value) > 1024 or any(ch.isspace() for ch in value)
            or value.count('::') < 2):
        raise ValueError(f'{label} must be an exact Move type')
    package, module, remainder = value.split('::', 2)
    _address(package, f'{label} package')
    identifier = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
    if not identifier.fullmatch(module) or not remainder or remainder.startswith(':'):
        raise ValueError(f'{label} must be an exact Move type')
    return value


@dataclass(frozen=True)
class Config:
    wallet: str
    graphql_url: str
    expected_chain_identifier: str
    published_world_package_ids: tuple[str, ...]
    world_type_origins: dict[str, str]
    environment: str = 'stillness'
    version: int = CONFIG_VERSION
    character_id: str | None = None
    watched_objects: tuple[dict, ...] = ()
    coin_type: str | None = None
    timeout: float = 10.0
    history_limit: int = 200

    def __post_init__(self):
        if self.version != CONFIG_VERSION: raise ValueError(f'unsupported config version {self.version!r}')
        object.__setattr__(self, 'wallet', _address(self.wallet, 'wallet'))
        object.__setattr__(self, 'graphql_url', _endpoint(self.graphql_url))
        if not isinstance(self.expected_chain_identifier, str) or not CHAIN_ID.fullmatch(self.expected_chain_identifier):
            raise ValueError('expected_chain_identifier is invalid')
        packages = tuple(self.published_world_package_ids) if isinstance(
            self.published_world_package_ids, (list, tuple)) else ()
        if not packages or len(packages) > 16:
            raise ValueError('published_world_package_ids must contain 1 to 16 package object IDs')
        packages = tuple(_address(value, 'published world package ID') for value in packages)
        if len(set(packages)) != len(packages):
            raise ValueError('published_world_package_ids contains duplicates')
        object.__setattr__(self, 'published_world_package_ids', packages)
        required_origins = {'PlayerProfile', 'Character', 'OwnerCap', 'Assembly',
                            'Gate', 'StorageUnit', 'NetworkNode'}
        if not isinstance(self.world_type_origins, dict):
            raise ValueError('world_type_origins must map world struct names to defining IDs')
        unknown = set(self.world_type_origins) - required_origins
        missing = required_origins - set(self.world_type_origins)
        if unknown or missing:
            detail = []
            if missing: detail.append('missing ' + ', '.join(sorted(missing)))
            if unknown: detail.append('unknown ' + ', '.join(sorted(unknown)))
            raise ValueError('world_type_origins has ' + '; '.join(detail))
        origins = {name: _address(self.world_type_origins[name], f'{name} type-origin ID')
                   for name in sorted(required_origins)}
        object.__setattr__(self, 'world_type_origins', origins)
        if self.character_id is not None:
            object.__setattr__(self, 'character_id', _address(self.character_id, 'character_id'))
        watches = []
        for item in self.watched_objects if isinstance(self.watched_objects, (list, tuple)) else ():
            if not isinstance(item, dict):
                raise ValueError('watched_objects entries must be objects')
            identifier = _address(item.get('id'), 'watched object ID')
            label = item.get('label') or ''
            if not isinstance(label, str) or len(label) > 96:
                raise ValueError('watched object label must contain at most 96 characters')
            expected = item.get('expected_type')
            if expected is not None:
                expected = _move_type(expected, 'watched expected_type')
            watches.append({'id': identifier, 'label': ' '.join(label.split()),
                            'expected_type': expected})
        if len(watches) > 100 or len({item['id'] for item in watches}) != len(watches):
            raise ValueError('watched_objects must contain at most 100 unique IDs')
        object.__setattr__(self, 'watched_objects', tuple(watches))
        if not isinstance(self.environment, str) or not self.environment.strip() or len(self.environment) > 64:
            raise ValueError('environment must be a non-empty name of at most 64 characters')
        if self.coin_type is not None: _move_type(self.coin_type, 'coin_type')
        if not isinstance(self.timeout, (int, float)) or not 0 < self.timeout <= 30:
            raise ValueError('timeout must be greater than zero and at most 30 seconds')
        if not isinstance(self.history_limit, int) or not 1 <= self.history_limit <= 1000:
            raise ValueError('history_limit must be between 1 and 1000')

    def world_type(self, name):
        modules = {'PlayerProfile': 'character', 'Character': 'character',
                   'OwnerCap': 'access', 'Assembly': 'assembly', 'Gate': 'gate',
                   'StorageUnit': 'storage_unit', 'NetworkNode': 'network_node'}
        return f'{self.world_type_origins[name]}::{modules[name]}::{name}'


def default_config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'atlas/frontier.json'


def default_state_path():
    return Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'atlas/frontier.json'


def _read_json(path, limit):
    path = Path(path)
    try: fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        if isinstance(exc, FileNotFoundError): raise
        raise FrontierError(f'cannot read {path.name}: {exc}') from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise FrontierError('file must be a regular file owned by this user')
        if info.st_size > limit: raise FrontierError('file exceeds its size limit')
        with os.fdopen(fd, 'rb', closefd=False) as source: raw = source.read(limit + 1)
        if len(raw) > limit: raise FrontierError('file exceeds its size limit')
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FrontierError(f'cannot read {path.name}: {exc}') from exc
    finally: os.close(fd)
    if not isinstance(value, dict): raise FrontierError(f'{path.name} must contain a JSON object')
    return value


def _atomic_json(path, value, mode=0o600):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as target:
            target.write(raw); target.flush(); os.fsync(target.fileno())
        os.replace(temporary, path); temporary = None
        try:
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        except OSError: pass
    finally:
        if temporary:
            try: os.unlink(temporary)
            except OSError: pass


def save_config(config, path=None):
    if not isinstance(config, Config): config = Config(**config)
    value = asdict(config)
    value['published_world_package_ids'] = list(config.published_world_package_ids)
    _atomic_json(path or default_config_path(), value)
    return config


def configure(*, wallet, graphql_url, expected_chain_identifier,
              published_world_package_ids, world_type_origins, path=None, **values):
    return save_config(Config(wallet=wallet, graphql_url=graphql_url,
        expected_chain_identifier=expected_chain_identifier,
        published_world_package_ids=published_world_package_ids,
        world_type_origins=world_type_origins, **values), path)


def load_config(path=None):
    data = _read_json(path or default_config_path(), MAX_CONFIG_BYTES)
    if 'world_package_ids' in data:
        raise FrontierError('legacy Frontier config is ambiguous after package upgrades; replace '
            'world_package_ids with published_world_package_ids and explicit world_type_origins')
    try: return Config(**data)
    except (TypeError, ValueError) as exc: raise FrontierError(f'invalid Frontier configuration: {exc}') from exc


class GraphQLTransport:
    class _NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise GraphQLError('GraphQL endpoint attempted a redirect')

    def __init__(self, endpoint, timeout=10.0, max_response=MAX_RESPONSE_BYTES):
        self.endpoint = _endpoint(endpoint)
        if not 0 < timeout <= 30: raise ValueError('invalid timeout')
        if not 1024 <= max_response <= MAX_RESPONSE_BYTES: raise ValueError('invalid response size limit')
        self.timeout, self.max_response = timeout, max_response
        self.opener = request.build_opener(self._NoRedirect)

    def query(self, operation, variables=None):
        payload = json.dumps({'query': operation, 'variables': variables or {}}).encode()
        req = request.Request(self.endpoint, data=payload, method='POST', headers={
            'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                length = response.headers.get('Content-Length')
                if length and int(length) > self.max_response: raise GraphQLError('GraphQL response exceeds the size limit')
                raw = response.read(self.max_response + 1)
        except error.HTTPError as exc:
            if exc.code == 429:
                try: retry_after = max(0, min(300, int(exc.headers.get('Retry-After', ''))))
                except (TypeError, ValueError): retry_after = None
                raise RateLimitError(retry_after) from exc
            raise GraphQLError(f'GraphQL HTTP error {exc.code}') from exc
        except GraphQLError: raise
        except (error.URLError, OSError, ValueError) as exc: raise GraphQLError(f'GraphQL request failed: {exc}') from exc
        if len(raw) > self.max_response: raise GraphQLError('GraphQL response exceeds the size limit')
        try: result = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc: raise GraphQLError('GraphQL returned invalid JSON') from exc
        if not isinstance(result, dict): raise GraphQLError('GraphQL returned an invalid response')
        if result.get('errors'):
            messages = [x.get('message') for x in result['errors'] if isinstance(x, dict) and isinstance(x.get('message'), str)]
            raise GraphQLError('GraphQL error: ' + '; '.join(messages[:3])[:480])
        if not isinstance(result.get('data'), dict): raise GraphQLError('GraphQL response has no data')
        return result['data']


def _type(node):
    try:
        contents = node.get('contents') or node['asMoveObject']['contents']
        return contents['type']['repr']
    except (KeyError, TypeError, AttributeError): return None


def _json(node):
    try: value = (node.get('contents') or node['asMoveObject']['contents'])['json']
    except (KeyError, TypeError): raise FrontierError('parsed Move object fields are unavailable')
    if not isinstance(value, dict): raise FrontierError('parsed Move object fields are unavailable')
    return value


def _id(value):
    if isinstance(value, str) and ADDRESS.fullmatch(value): return value.lower()
    if isinstance(value, dict):
        for key in ('id', 'bytes'):
            found = _id(value.get(key))
            if found: return found
    return None


def _page(connection, label):
    if not isinstance(connection, dict) or not isinstance(connection.get('nodes'), list):
        raise FrontierError(f'{label} returned an invalid page')
    info = connection.get('pageInfo')
    if not isinstance(info, dict): raise FrontierError(f'{label} returned no page information')
    return connection['nodes'], bool(info.get('hasNextPage')), info.get('endCursor')


def _name(fields):
    metadata = fields.get('metadata')
    if isinstance(metadata, dict):
        metadata = metadata.get('fields', metadata)
        value = metadata.get('name') if isinstance(metadata, dict) else None
        if isinstance(value, str) and value.strip(): return ' '.join(value.split())[:96]
    return None


def _state(fields):
    assembly_status = fields.get('status')
    value = assembly_status.get('status') if isinstance(assembly_status, dict) else None
    value = value.get('@variant') if isinstance(value, dict) else None
    return value.upper() if isinstance(value, str) and value.upper() in ('ONLINE', 'OFFLINE') else 'UNAVAILABLE'


def _evidence(node):
    tx = node.get('previousTransaction') if isinstance(node.get('previousTransaction'), dict) else {}
    effects = tx.get('effects') if isinstance(tx.get('effects'), dict) else {}
    checkpoint = effects.get('checkpoint') if isinstance(effects.get('checkpoint'), dict) else {}
    return {'version': str(node.get('version', '')), 'digest': str(node.get('digest', '')),
            'transaction': tx.get('digest'), 'execution_status': effects.get('status'),
            'timestamp': _timestamp(effects.get('timestamp')), 'checkpoint': checkpoint.get('sequenceNumber'),
            'checkpoint_digest': checkpoint.get('digest')}


def _timestamp(value):
    if isinstance(value, (int, float)): return float(value)
    if isinstance(value, str):
        try: return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except (ValueError, OverflowError): pass
    return None


class FrontierReader:
    REQUIRED_MODULES = {'character', 'access', 'assembly', 'gate',
                        'storage_unit', 'network_node'}
    ASSEMBLY_TYPES = {('assembly', 'Assembly'), ('gate', 'Gate'),
                      ('storage_unit', 'StorageUnit'),
                      ('network_node', 'NetworkNode')}

    def __init__(self, config, transport=None):
        self.config = config
        self.transport = transport or GraphQLTransport(config.graphql_url, config.timeout)

    def environment(self):
        data = self.transport.query(ENVIRONMENT_QUERY)
        chain, checkpoint = data.get('chainIdentifier'), data.get('checkpoint')
        if not isinstance(chain, str) or not isinstance(checkpoint, dict): raise FrontierError('environment identity is unavailable')
        if chain != self.config.expected_chain_identifier: raise FrontierError('chain identifier does not match configuration')
        sequence = checkpoint.get('sequenceNumber')
        if not isinstance(sequence, (str, int)) or not str(sequence).isdigit(): raise FrontierError('checkpoint sequence is unavailable')
        return chain, {**checkpoint, 'sequenceNumber': int(sequence)}

    def probe_packages(self):
        expected_origins = {
            ('character', 'PlayerProfile'): self.config.world_type_origins['PlayerProfile'],
            ('character', 'Character'): self.config.world_type_origins['Character'],
            ('access', 'OwnerCap'): self.config.world_type_origins['OwnerCap'],
            ('assembly', 'Assembly'): self.config.world_type_origins['Assembly'],
            ('gate', 'Gate'): self.config.world_type_origins['Gate'],
            ('storage_unit', 'StorageUnit'): self.config.world_type_origins['StorageUnit'],
            ('network_node', 'NetworkNode'): self.config.world_type_origins['NetworkNode'],
        }
        for package in self.config.published_world_package_ids:
            value = self.transport.query(PACKAGE_QUERY, {'package': package}).get('object')
            if not isinstance(value, dict) or _id(value.get('address')) != package:
                raise FrontierError(f'configured world package {package} is unavailable')
            value = value.get('asMovePackage')
            if not isinstance(value, dict):
                raise FrontierError(f'configured world object {package} is not a Move package')
            names = {module.get('name') for key in
                     ('character', 'access', 'assembly', 'gate', 'storage', 'node')
                     if isinstance((module := value.get(key)), dict)}
            missing = self.REQUIRED_MODULES - names
            if missing: raise FrontierError(f'world package is missing required modules: {", ".join(sorted(missing))}')
            origins = value.get('typeOrigins')
            if not isinstance(origins, list):
                raise FrontierError('world package type origins are unavailable')
            observed = {(item.get('module'), item.get('struct')): _id(item.get('definingId'))
                        for item in origins if isinstance(item, dict)}
            mismatched = [f'{module}::{struct}' for (module, struct), defining_id
                          in expected_origins.items() if observed.get((module, struct)) != defining_id]
            if mismatched:
                raise FrontierError('world package type origins do not match configuration: '
                                    + ', '.join(mismatched))

    def _paginate(self, operation, variables, path, label):
        cursor, rows, seen = None, [], set()
        for _ in range(MAX_PAGES):
            value = self.transport.query(operation, {**variables, 'after': cursor})
            for part in path: value = value.get(part) if isinstance(value, dict) else None
            nodes, more, next_cursor = _page(value, label); rows.extend(nodes)
            if not more: return rows
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen:
                raise FrontierError(f'{label} pagination did not advance')
            seen.add(next_cursor); cursor = next_cursor
        raise FrontierError(f'{label} pagination exceeded the page limit')

    def profile(self):
        if self.config.character_id:
            node = self.snapshot(self.config.character_id)
            if _type(node) != self.config.world_type('Character'):
                raise FrontierError('configured character does not match the Character type origin')
            return self.config.character_id
        exact = self.config.world_type('PlayerProfile')
        rows = self._paginate(PROFILES_QUERY, {'owner': self.config.wallet, 'type': exact},
                              ('address', 'objects'), 'profile enumeration')
        matches = [row for row in rows if _type(row) == exact]
        if not matches: raise FrontierError('no PlayerProfile of a configured package was found')
        if len(matches) != 1: raise FrontierError('multiple PlayerProfiles of configured packages were found')
        identifier = _id(_json(matches[0]).get('character_id'))
        if not identifier: raise FrontierError('PlayerProfile has no valid character_id')
        return identifier

    def snapshot(self, identifier, exact_type=None):
        node = self.transport.query(SNAPSHOT_QUERY, {'address': identifier}).get('object')
        if not isinstance(node, dict) or _id(node.get('address')) != identifier: raise FrontierError('object snapshot is unavailable')
        if exact_type is not None and _type(node) != exact_type: raise FrontierError('object type does not match the configured package')
        return node

    def caps(self, character_id):
        caps = []
        seen_caps = {}
        owner_cap = self.config.world_type('OwnerCap')
        prefix = owner_cap + '<'
        rows = self._paginate(CAPS_QUERY, {'character': character_id,
            'type': owner_cap.rsplit('::', 1)[0]}, ('objects',), 'OwnerCap enumeration')
        assembly_types = {self.config.world_type(name) for name in
                          ('Assembly', 'Gate', 'StorageUnit', 'NetworkNode')}
        known_target_types = assembly_types | {self.config.world_type('Character')}
        for node in rows:
            object_type = _type(node)
            if not (isinstance(object_type, str) and object_type.startswith(prefix)
                    and object_type.endswith('>')): continue
            target_type = object_type[len(prefix):-1]
            if target_type not in known_target_types: continue
            target, cap = _id(_json(node).get('authorized_object_id')), _id(node.get('address'))
            if not target or not cap: raise FrontierError('OwnerCap is missing an object identifier')
            if cap in seen_caps:
                if seen_caps[cap] != target:
                    raise FrontierError('one OwnerCap returned conflicting authorized objects')
                continue
            seen_caps[cap] = target
            caps.append({'id': cap, 'object_id': target, 'target_type': target_type,
                         'is_assembly': target_type in assembly_types})
        return caps

    def balance(self):
        if not self.config.coin_type:
            return {'status': 'UNAVAILABLE', 'amount': None, 'symbol': 'EVE',
                    'reason': 'coin type is not configured'}
        data = self.transport.query(BALANCE_QUERY,
                                    {'wallet': self.config.wallet, 'coinType': self.config.coin_type})
        try: balance = data['address']['balance']
        except (KeyError, TypeError): balance = None
        if not isinstance(balance, dict) or not str(balance.get('totalBalance', '')).isdigit(): raise FrontierError('coin balance is unavailable')
        try: returned = balance['coinType']['repr']
        except (KeyError, TypeError): returned = None
        if returned != self.config.coin_type: raise FrontierError('coin balance type does not match configuration')
        metadata = data.get('coinMetadata')
        decimals = None
        if metadata is not None:
            if not isinstance(metadata, dict): raise FrontierError('coin metadata is invalid')
            if (metadata.get('symbol') != 'EVE' or metadata.get('name') != 'EVE Token'
                    or metadata.get('decimals') != 9):
                raise FrontierError('coin metadata does not match EVE Token')
            decimals = 9
        return {'status': 'available', 'amount': str(balance['totalBalance']),
                'symbol': 'EVE', 'reason': None, 'coin_type': self.config.coin_type,
                'decimals': decimals, 'raw_units': decimals is None}


def _namespace(config, chain, character_id):
    origins = ','.join(f'{name}={origin}' for name, origin in
                       sorted(config.world_type_origins.items()))
    value = '\0'.join((chain, config.environment, ','.join(config.published_world_package_ids),
                       origins,
                       config.wallet, character_id, config.coin_type or '')).encode()
    return hashlib.sha256(value).hexdigest()


def _assembly_type(value, config):
    parts = value.split('::') if isinstance(value, str) else []
    known = {('assembly', 'Assembly'): 'Assembly', ('gate', 'Gate'): 'Gate',
             ('storage_unit', 'StorageUnit'): 'Storage Unit',
             ('network_node', 'NetworkNode'): 'Network Node'}
    if len(parts) != 3:
        return None, None
    type_name = known.get(tuple(parts[1:]))
    if not type_name or value != config.world_type(type_name.replace(' ', '')):
        return None, None
    return parts[1], type_name


def _ids(value):
    if not isinstance(value, list): return []
    return [identifier for item in value if (identifier := _id(item))]


def short_id(value):
    return value if not isinstance(value, str) or len(value) <= 14 else value[:8] + '…' + value[-4:]


def _facts(fields, module):
    """Decode only documented non-location fields for an exact known type."""
    facts = {}
    owner_cap = _id(fields.get('owner_cap_id'))
    energy_source = _id(fields.get('energy_source_id'))
    if owner_cap: facts['Owner capability'] = owner_cap
    if energy_source: facts['Energy source'] = energy_source
    if module == 'gate':
        linked = _id(fields.get('linked_gate_id'))
        if linked: facts['Linked gate'] = linked
    elif module == 'storage_unit':
        inventory = _ids(fields.get('inventory_keys'))
        facts['Inventory keys'] = len(inventory)
    elif module == 'network_node':
        connected = _ids(fields.get('connected_assembly_ids'))
        facts['Connected assemblies'] = len(connected)
        for label, key in (('Fuel', 'fuel'), ('Energy source data', 'energy_source')):
            value = fields.get(key)
            if isinstance(value, (dict, list, str, int, float, bool)):
                facts[label] = json.dumps(value, sort_keys=True, separators=(',', ':'))[:1024]
    return facts


class Monitor:
    def __init__(self, config_path=None, state_path=None, *, config=None, transport=None, clock=time.time):
        self.config = config or load_config(config_path)
        self.state_path = Path(state_path or default_state_path())
        self.reader = FrontierReader(self.config, transport); self.clock = clock
        self._packages_checked_at = None

    def _baseline(self, namespace):
        try: state = _read_json(self.state_path, MAX_STATE_BYTES)
        except FileNotFoundError: return {}, {'version': STATE_VERSION, 'namespaces': {}}
        if state.get('version') != STATE_VERSION or not isinstance(state.get('namespaces'), dict):
            raise FrontierError('local Frontier history has an unsupported format')
        value = state['namespaces'].get(namespace, {})
        return value if isinstance(value, dict) else {}, state

    def poll(self):
        started = now = self.clock()
        result = {'connected': False, 'error': None, 'warnings': [], 'environment': self.config.environment,
            'chain_id': None, 'endpoint': self.config.graphql_url, 'checkpoint': None,
            'checkpoint_digest': None, 'checkpoint_timestamp': None, 'retrieved_at': None,
            'request_duration': None, 'indexer_lag': None,
            'character': {'verified': False}, 'capabilities_count': None,
            'controlled_assemblies_count': None,
            'assemblies': [], 'balance': {'status': 'UNAVAILABLE', 'amount': None,
            'symbol': 'EVE', 'reason': 'not retrieved'}, 'activity': [],
            'baseline_created': False}
        baseline = {}
        try:
            chain, checkpoint = self.reader.environment()
            result.update(connected=True, chain_id=chain, checkpoint=checkpoint['sequenceNumber'],
                checkpoint_digest=checkpoint.get('digest'), checkpoint_timestamp=_timestamp(checkpoint.get('timestamp')),
                indexer_lag=None)
            base_namespace = _namespace(self.config, chain, '')
            _, state = self._baseline('')
            last_characters = state.get('last_characters')
            if isinstance(last_characters, dict):
                previous_character = _id(last_characters.get(base_namespace))
                if previous_character:
                    previous_namespace = _namespace(self.config, chain, previous_character)
                    value = state['namespaces'].get(previous_namespace, {})
                    baseline = value if isinstance(value, dict) else {}
            if self._packages_checked_at is None or now - self._packages_checked_at >= 300:
                self.reader.probe_packages()
                self._packages_checked_at = now
            character_id = self.reader.profile()
            namespace = _namespace(self.config, chain, character_id)
            value = state['namespaces'].get(namespace, {})
            baseline = value if isinstance(value, dict) else {}
            character = self.reader.snapshot(character_id, self.config.world_type('Character'))
            fields = _json(character); address = _id(fields.get('character_address'))
            if address != self.config.wallet: raise FrontierError('character address does not match the configured wallet')
            result['character'] = {'id': character_id, 'name': _name(fields) or 'UNAVAILABLE',
                'tribe_id': fields.get('tribe_id', 'UNAVAILABLE'), 'address': address,
                'verified': True, **_evidence(character)}
            caps = self.reader.caps(character_id); result['capabilities_count'] = len(caps)
            assembly_caps = [cap for cap in caps if cap['is_assembly']]
            result['controlled_assemblies_count'] = len({cap['object_id'] for cap in assembly_caps})
            previous = baseline.get('objects', {}) if isinstance(baseline.get('objects'), dict) else {}
            previous_caps = baseline.get('caps', {}) if isinstance(baseline.get('caps'), dict) else {}
            prior_events = baseline.get('events', []) if isinstance(baseline.get('events'), list) else []
            first = not bool(baseline); result['baseline_created'] = first
            current_caps = {cap['id']: cap['object_id'] for cap in caps}
            new_events = []
            targets = {}
            for cap in assembly_caps:
                target = targets.setdefault(cap['object_id'], {'id': cap['object_id'],
                    'label': '', 'expected_type': cap['target_type'], 'caps': [],
                    'controlled': True, 'watched': False})
                target['caps'].append(cap['id'])
            for watch in self.config.watched_objects:
                target = targets.setdefault(watch['id'], {'id': watch['id'],
                    'label': '', 'expected_type': watch.get('expected_type'), 'caps': [],
                    'controlled': False, 'watched': True})
                target['watched'] = True
                target['label'] = watch.get('label') or target['label']
                if watch.get('expected_type'):
                    target['expected_type'] = watch['expected_type']
            current = {identifier: value for identifier, value in previous.items()
                       if identifier in targets}
            for identifier, target in targets.items():
                old = previous.get(identifier)
                row = {'id': identifier, 'name': target['label'] or identifier,
                    'type': None, 'type_name': 'Object', 'state': 'UNAVAILABLE',
                    'monitor': 'UNAVAILABLE', 'baseline_created': not isinstance(old, dict),
                    'version': None, 'digest': None, 'transaction': None,
                    'execution_status': None, 'checkpoint': None,
                    'checkpoint_digest': None, 'timestamp': None,
                    'cap_id': target['caps'][0] if len(target['caps']) == 1 else None,
                    'cap_ids': target['caps'], 'custodian': character_id if target['controlled'] else None,
                    'controlled': target['controlled'], 'watched': target['watched'],
                    'changed_fields': [], 'facts': {}, 'reason': None,
                    'last_known': old if isinstance(old, dict) else None}
                try:
                    node = self.reader.snapshot(identifier)
                    evidence = _evidence(node); object_type = _type(node)
                    row.update(evidence, type=object_type)
                    if target.get('expected_type') and object_type != target['expected_type']:
                        raise FrontierError('object type does not match configured capability/watch type')
                    module, type_name = _assembly_type(object_type, self.config)
                    if not type_name:
                        raise FrontierError('object type is outside the supported assembly schema')
                    fields = _json(node)
                    if len(target['caps']) > 1:
                        raise FrontierError('multiple capabilities authorize this object; control is ambiguous')
                    changed = [] if not isinstance(old, dict) else [key for key in
                        ('version', 'digest', 'transaction') if old.get(key) != evidence.get(key)]
                    monitor = 'UPDATED' if changed else 'UNCHANGED'
                    row.update(name=target['label'] or _name(fields) or type_name,
                        type_name=type_name, state=_state(fields), monitor=monitor,
                        changed_fields=changed, facts=_facts(fields, module), reason=None)
                    current[identifier] = {**evidence, 'type': object_type,
                        'name': row['name'], 'seen_at': now}
                    if monitor == 'UPDATED':
                        new_events.append({'timestamp': evidence['timestamp'] or now,
                            'title': f'{row["name"]} changed', 'detail': ', '.join(changed),
                            'role': 'observed'})
                except (FrontierError, GraphQLError) as exc:
                    row['reason'] = str(exc)
                    result['warnings'].append(f'{short_id(identifier)}: {exc}')
                result['assemblies'].append(row)
            if not first and isinstance(baseline.get('caps'), dict):
                for cap_id, target in current_caps.items():
                    old_target = previous_caps.get(cap_id)
                    if old_target is None:
                        new_events.append({'timestamp': now, 'title': 'Control capability now held',
                            'detail': target, 'role': 'derived'})
                    elif old_target != target:
                        new_events.append({'timestamp': now, 'title': 'Control capability target changed',
                            'detail': f'{old_target} → {target}', 'role': 'derived'})
                for cap_id, target in previous_caps.items():
                    if cap_id not in current_caps:
                        old = previous.get(target, {})
                        new_events.append({'timestamp': now, 'title': 'Control capability no longer held',
                            'detail': str(old.get('name') or target), 'role': 'derived'})
            result['activity'] = (new_events + [event for event in prior_events
                                  if isinstance(event, dict)])[:self.config.history_limit]
            try: result['balance'] = self.reader.balance()
            except FrontierError as exc: result['balance']['reason'] = str(exc); result['warnings'].append(str(exc))
            state['namespaces'][namespace] = {'updated_at': now, 'character_id': character_id,
                'checkpoint': checkpoint['sequenceNumber'], 'objects': current,
                'caps': current_caps, 'events': result['activity']}
            state.setdefault('last_characters', {})[base_namespace] = character_id
            try:
                _atomic_json(self.state_path, state)
            except OSError as exc:
                result['warnings'].append(
                    f'HISTORY_WRITE_FAILED: current observations are live; local history was not saved: {exc}')
        except (FrontierError, GraphQLError, OSError) as exc:
            result['connected'] = False
            result['error'] = str(exc)
            if isinstance(exc, RateLimitError): result['retry_after'] = exc.retry_after
            previous = baseline.get('objects', {}) if isinstance(baseline.get('objects'), dict) else {}
            if not result['assemblies']:
                for identifier, known in previous.items():
                    if not isinstance(known, dict): continue
                    _, type_name = _assembly_type(known.get('type'), self.config)
                    result['assemblies'].append({'id': identifier,
                        'name': known.get('name') or type_name or identifier,
                        'type': known.get('type'), 'type_name': type_name or 'Object',
                        'state': 'UNAVAILABLE', 'monitor': 'UNAVAILABLE',
                        'version': None, 'digest': None, 'transaction': None,
                        'execution_status': None, 'checkpoint': None, 'timestamp': None,
                        'cap_id': None, 'custodian': None, 'controlled': False,
                        'watched': False, 'facts': {}, 'reason': str(exc),
                        'last_known': known})
            if not result['activity'] and isinstance(baseline.get('events'), list):
                result['activity'] = [event for event in baseline['events']
                                      if isinstance(event, dict)][:self.config.history_limit]
        finished = self.clock()
        result['retrieved_at'] = finished
        result['request_duration'] = max(0, finished - started)
        stamp = result.get('checkpoint_timestamp')
        result['indexer_lag'] = max(0, finished - stamp) if isinstance(stamp, (int, float)) else None
        return result

    def close(self): return None
