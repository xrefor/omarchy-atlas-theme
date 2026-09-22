"""Configure and launch the read-only ATLAS Frontier intelligence panel."""
import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import threading
import time

from . import backend, ui
from .tmux_panel import Panel


def launcher():
    return str(Path(__file__).resolve().parents[1] / 'bin/atlas-frontier')


def command(*args):
    return [sys.executable, launcher(), *args]


def tmux(*args):
    return subprocess.check_output(['tmux', *args], text=True,
                                   stderr=subprocess.PIPE, timeout=5).rstrip('\r\n')


def origin_pane(value=None):
    pane = value or os.environ.get('TMUX_PANE', '')
    if not os.environ.get('TMUX'):
        raise ValueError('Open the Frontier panel from a tmux session')
    actual, owner = tmux('display-message', '-p', '-t', pane,
                         '#{pane_id}\t#{@atlas_frontier_origin}').split('\t', 1)
    return owner or actual


class Collector:
    """Coalesce refreshes and keep network polling outside the curses thread."""

    def __init__(self, config_path=None, state_path=None, interval=15):
        self.interval = max(5, min(300, int(interval)))
        self.lock = threading.Lock()
        self.refresh = threading.Event()
        self.stop = threading.Event()
        self.snapshot = {'connected': False, 'error': 'Collector is starting',
                         'environment': 'NOT CONFIGURED'}
        try:
            self.monitor = backend.Monitor(config_path=config_path, state_path=state_path)
            self.snapshot['environment'] = self.monitor.config.environment
            self.snapshot['wallet'] = self.monitor.config.wallet
            self.snapshot['endpoint'] = self.monitor.config.graphql_url
        except (OSError, ValueError, backend.FrontierError) as error:
            self.monitor = None
            self.snapshot['error'] = str(error)
        self.thread = threading.Thread(target=self._run, name='atlas-frontier', daemon=True)
        self.thread.start()

    def _run(self):
        if self.monitor is None:
            return
        failures = 0
        while not self.stop.is_set():
            self.refresh.clear()
            try:
                value = self.monitor.poll()
            except (OSError, ValueError, backend.FrontierError) as error:
                value = {'connected': False, 'error': str(error),
                         'environment': self.monitor.config.environment,
                         'wallet': self.monitor.config.wallet,
                         'endpoint': self.monitor.config.graphql_url,
                         'retrieved_at': time.time()}
            with self.lock:
                self.snapshot = value
            failures = failures + 1 if value.get('error') else 0
            delay = min(300, self.interval * (2 ** min(failures, 4)))
            if isinstance(value.get('retry_after'), (int, float)):
                delay = max(delay, min(300, value['retry_after']))
            if failures:
                delay += random.uniform(0, min(5, delay * .1))
            self.refresh.wait(delay)

    def get(self):
        with self.lock:
            return dict(self.snapshot)

    def request_refresh(self):
        self.refresh.set()

    def close(self):
        self.stop.set()
        self.refresh.set()
        self.thread.join(timeout=2)
        if self.monitor is not None:
            self.monitor.close()


def configure(args):
    transport = backend.GraphQLTransport(args.endpoint, args.timeout)
    data = transport.query(backend.ENVIRONMENT_QUERY)
    chain = data.get('chainIdentifier') if isinstance(data, dict) else None
    if not isinstance(chain, str) or not chain:
        raise backend.FrontierError('The endpoint did not report a chain identifier')
    if args.expected_chain and args.expected_chain != chain:
        raise backend.FrontierError('The endpoint chain identifier does not match --expected-chain')
    watches = []
    for value in args.watch:
        identifier, separator, label = value.partition('=')
        watches.append({'id': identifier, 'label': label if separator else '',
                        'expected_type': None})
    origin_names = ('PlayerProfile', 'Character', 'OwnerCap', 'Assembly', 'Gate',
                    'StorageUnit', 'NetworkNode')
    origins = {}
    for value in args.type_origin:
        name, separator, identifier = value.partition('=')
        if separator:
            if name not in origin_names:
                raise ValueError(f'unknown type-origin name {name!r}')
            origins[name] = identifier
        else:
            origins.update({name: value for name in origin_names})
    config = backend.Config(wallet=args.wallet, graphql_url=args.endpoint,
        expected_chain_identifier=chain,
        published_world_package_ids=tuple(args.published_package),
        world_type_origins=origins,
        environment=args.environment, coin_type=args.eve_coin_type,
        character_id=args.character, watched_objects=tuple(watches), timeout=args.timeout)
    backend.FrontierReader(config, transport).probe_packages()
    path = Path(args.config).expanduser() if args.config else backend.default_config_path()
    backend.save_config(config, path)
    print(f'Frontier configuration saved to {path}')
    print(f'Chain identifier pinned: {chain}')
    print('The environment label is user-configured; package probes passed.')
    return 0


def status(args):
    path = Path(args.config).expanduser() if args.config else backend.default_config_path()
    config = backend.load_config(path)
    print('ATLAS / FRONTIER CONFIGURATION')
    print(f'Environment: {config.environment} (user configured)')
    print(f'Endpoint: {config.graphql_url}')
    print(f'Chain: {config.expected_chain_identifier}')
    print(f'Wallet: {config.wallet[:8]}…{config.wallet[-4:]}')
    print(f'Published package probes: {len(config.published_world_package_ids)} configured')
    print(f'Accepted type origins: {len(set(config.world_type_origins.values()))} defining IDs')
    print('EVE coin type: ' + ('configured' if config.coin_type else 'not configured'))
    return 0


def show(args):
    collector = Collector(args.config, args.state, args.interval)
    palette = Path.home() / '.config/atlas/frontier-palette.json'
    try:
        ui.run(collector.get, palette, collector.request_refresh)
    finally:
        collector.close()
    return 0


def snapshot(args):
    monitor = backend.Monitor(config_path=args.config, state_path=args.state)
    try:
        value = monitor.poll()
    finally:
        monitor.close()
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0 if value.get('connected') and not value.get('error') else 1


def toggle(args):
    origin = origin_pane(args.pane)
    manager = Panel(origin, command('show', *(('--config', args.config) if args.config else ())))
    manager.toggle()
    return 0


def parser():
    result = argparse.ArgumentParser(prog='atlas-frontier',
        description='Read-only EVE Frontier intelligence panel for ATLAS')
    commands = result.add_subparsers(dest='action', required=True)

    setup = commands.add_parser('configure', help='verify and save public monitor settings')
    setup.add_argument('--wallet', required=True, help='public 0x-prefixed Sui account address')
    setup.add_argument('--endpoint', required=True, help='Sui GraphQL endpoint')
    setup.add_argument('--published-package', action='append', required=True,
                       help='exact published Frontier package object ID to probe; repeat as needed')
    setup.add_argument('--type-origin', action='append', required=True,
                       metavar='[NAME=]DEFINING_ID',
                       help='defining package ID for Move types; one bare ID applies to all known types')
    setup.add_argument('--environment', required=True,
                       help='user-configured environment label shown by the panel')
    setup.add_argument('--expected-chain', help='optional independently known chain identifier')
    setup.add_argument('--eve-coin-type', help='optional exact canonical EVE Move coin type')
    setup.add_argument('--character', help='optional Smart Character ID when profile discovery is ambiguous')
    setup.add_argument('--watch', action='append', default=[], metavar='OBJECT_ID[=LABEL]',
                       help='additional Frontier assembly object to watch; repeat as needed')
    setup.add_argument('--timeout', type=float, default=10, help='request timeout in seconds (default: 10)')
    setup.add_argument('--config', help='alternative configuration path')
    setup.set_defaults(function=configure)

    check = commands.add_parser('status', help='show saved configuration without network access')
    check.add_argument('--config', help='alternative configuration path')
    check.set_defaults(function=status)

    display = commands.add_parser('show', help='open the panel in the current terminal')
    display.add_argument('--config', help='alternative configuration path')
    display.add_argument('--state', help='alternative evidence-state path')
    display.add_argument('--interval', type=int, default=15, help='poll interval, 5–300 seconds')
    display.set_defaults(function=show)

    once = commands.add_parser('snapshot', help='perform one poll and print normalized JSON')
    once.add_argument('--config', help='alternative configuration path')
    once.add_argument('--state', help='alternative evidence-state path')
    once.set_defaults(function=snapshot)

    panel = commands.add_parser('toggle', help='toggle the panel for an originating tmux pane')
    panel.add_argument('--pane', help='originating tmux pane ID (defaults to TMUX_PANE)')
    panel.add_argument('--config', help='alternative configuration path')
    panel.set_defaults(function=toggle)
    return result


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        return args.function(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, backend.FrontierError, subprocess.SubprocessError) as error:
        print(f'atlas-frontier: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
