"""Command-line entry point for the ATLAS Projects handoff panel."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .backend import Collector
from .tmux_panel import Panel
from . import ui


def executable(*arguments):
    command = Path(__file__).resolve().parents[1] / 'bin/atlas-projects'
    return [str(command), *arguments]


def tmux(*arguments):
    value = subprocess.check_output(['tmux', *arguments], text=True,
                                    stderr=subprocess.PIPE, timeout=3)
    return value[:-1] if value.endswith('\n') else value


def origin_pane(value=None):
    pane = value or os.environ.get('TMUX_PANE', '')
    if not os.environ.get('TMUX'):
        raise ValueError('The Projects panel toggle requires tmux; run atlas-projects show --path PATH instead')
    actual, owner = tmux('display-message', '-p', '-t', pane,
                         '#{pane_id}\t#{@atlas_projects_origin}').split('\t', 1)
    return owner or actual


def show(args):
    collector = Collector(args.path)
    ui.run(collector, Path.home() / '.config/atlas/projects-palette.json')
    return 0


def snapshot(args):
    print(json.dumps(Collector(args.path).collect(), indent=2, sort_keys=True))
    return 0


def toggle(args):
    Panel(origin_pane(args.pane), executable('show')).toggle()
    return 0


def parser():
    result = argparse.ArgumentParser(prog='atlas-projects',
        description='Git handoff panel for ATLAS; remote checks are explicit')
    commands = result.add_subparsers(dest='action', required=True)
    display = commands.add_parser('show', help='open a project panel in this terminal')
    display.add_argument('--path', required=True, help='project path to inspect')
    display.set_defaults(function=show)
    once = commands.add_parser('snapshot', help='print one normalized project snapshot')
    once.add_argument('--path', required=True, help='project path to inspect')
    once.set_defaults(function=snapshot)
    panel = commands.add_parser('toggle', help='toggle the project panel for a tmux pane')
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
        print(f'atlas-projects: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
