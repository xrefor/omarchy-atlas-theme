"""Command-line entry point for the ATLAS Ports & Services panel."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .backend import Collector
from .elevation import SessionCollector
from .tmux_panel import Panel
from . import ui


def executable(*arguments):
    command = Path(__file__).resolve().parents[1] / 'bin/atlas-ports'
    return [str(command), *arguments]


def tmux(*arguments):
    value = subprocess.check_output(['tmux', *arguments], text=True,
                                    stderr=subprocess.PIPE, timeout=3)
    return value[:-1] if value.endswith('\n') else value


def origin_pane(value=None):
    pane = value or os.environ.get('TMUX_PANE', '')
    if not os.environ.get('TMUX'):
        raise ValueError('The Ports & Services panel toggle requires tmux; run atlas-ports show instead')
    actual, owner = tmux('display-message', '-p', '-t', pane,
                         '#{pane_id}\t#{@atlas_ports_origin}').split('\t', 1)
    return owner or actual


def show(args):
    collector = SessionCollector()
    ui.run(collector, Path.home() / '.config/atlas/ports-palette.json',
           inspect_details=collector.authenticate, stop_admin=collector.disable,
           authenticate_on_open=not args.user)
    return 0


def snapshot(args):
    print(json.dumps(Collector().collect(), indent=2, sort_keys=True))
    return 0


def toggle(args):
    Panel(origin_pane(args.pane), executable('show')).toggle()
    return 0


def parser():
    result = argparse.ArgumentParser(prog='atlas-ports',
        description='Ports & Services panel for ATLAS; local read-only socket information')
    commands = result.add_subparsers(dest='action', required=True)
    display = commands.add_parser('show', help='open the Ports & Services panel in this terminal')
    display.add_argument('--user', action='store_true', help='open without requesting administrator details')
    display.set_defaults(function=show)
    once = commands.add_parser('snapshot', help='print one local listener snapshot')
    once.set_defaults(function=snapshot)
    panel = commands.add_parser('toggle', help='toggle the Ports & Services panel for a tmux pane')
    panel.add_argument('--pane', help='originating tmux pane ID (defaults to TMUX_PANE)')
    panel.set_defaults(function=toggle)
    return result


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        return args.function(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'atlas-ports: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
