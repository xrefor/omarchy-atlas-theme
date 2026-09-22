"""Command-line entry point for the ATLAS System panel."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from .backend import Collector
from .tmux_panel import Panel
from . import ui


def executable(*arguments):
    command = Path(__file__).resolve().parents[1] / 'bin/atlas-system'
    return [str(command), *arguments]


def origin_pane(value):
    value = value or os.environ.get('TMUX_PANE', '')
    if not os.environ.get('TMUX'):
        raise ValueError('The System panel toggle requires tmux; run atlas-system show instead')
    result = subprocess.check_output(
        ['tmux', 'display-message', '-p', '-t', value,
         '#{pane_id}\t#{@atlas_system_origin}'],
        text=True, stderr=subprocess.PIPE, timeout=5).rstrip('\r\n')
    actual, separator, owner = result.partition('\t')
    origin = owner if separator and re.fullmatch(r'%\d+', owner) else actual
    if not re.fullmatch(r'%\d+', origin):
        raise ValueError('A valid tmux origin pane is required')
    return origin


def show(_args):
    collector = Collector()
    ui.run(collector, Path.home() / '.config/atlas/system-palette.json')
    return 0


def snapshot(_args):
    import json
    collector = Collector()
    collector.collect()
    # A short second sample gives rates meaning without retaining a daemon.
    import time
    time.sleep(.1)
    print(json.dumps(collector.collect(), indent=2, sort_keys=True))
    return 0


def toggle(args):
    Panel(origin_pane(args.pane), executable('show')).toggle()
    return 0


def parser():
    result = argparse.ArgumentParser(prog='atlas-system',
        description='Read-only local system panel for ATLAS')
    commands = result.add_subparsers(dest='action', required=True)
    display = commands.add_parser('show', help='open the panel in the current terminal')
    display.set_defaults(function=show)
    once = commands.add_parser('snapshot', help='print one normalized local snapshot as JSON')
    once.set_defaults(function=snapshot)
    panel = commands.add_parser('toggle', help='toggle the panel for an originating tmux pane')
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
        print(f'atlas-system: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
