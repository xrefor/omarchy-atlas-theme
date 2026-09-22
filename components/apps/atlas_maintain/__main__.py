"""Command-line entry point for the read-only ATLAS Maintain panel."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from .backend import Collector
from .tmux_panel import Panel
from . import ui


def executable(*arguments):
    command = Path(__file__).resolve().parents[1] / 'bin/atlas-maintain'
    return [str(command), *arguments]


def _tmux(*arguments):
    return subprocess.check_output(['tmux', *arguments], text=True,
                                   stderr=subprocess.PIPE, timeout=3).rstrip('\r\n')


def origin_pane(value):
    value = value or os.environ.get('TMUX_PANE', '')
    if not os.environ.get('TMUX'):
        raise ValueError('The Maintain panel toggle requires tmux; run atlas-maintain show instead')
    actual, owner = _tmux('display-message', '-p', '-t', value,
                          '#{pane_id}\t#{@atlas_maintain_origin}').split('\t', 1)
    return owner or actual


def show(_args):
    ui.run(Collector(), Path.home() / '.config/atlas/maintain-palette.json')
    return 0


def toggle(args):
    Panel(origin_pane(args.pane), executable('show')).toggle()
    return 0


def parser():
    result = argparse.ArgumentParser(
        prog='atlas-maintain', description='Read-only local maintenance panel for ATLAS')
    commands = result.add_subparsers(dest='action', required=True)
    display = commands.add_parser('show', help='open the panel in the current terminal')
    display.set_defaults(function=show)
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
        print(f'atlas-maintain: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
