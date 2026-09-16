import os
import sys
from rich.console import Console
from rich.table import Table
from . import backend


def main():
    os.umask(0o077)
    args = sys.argv[1:]
    os.environ.update(backend.environment())
    backend.setup()
    if not args or args == ['tui']:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print('Use nutcracker --help for commands, or run nutcracker in a terminal for the TUI.')
            return 0
        from .app import NutcrackerApp
        from .input import restore_caret
        try:
            NutcrackerApp().run()
        finally:
            restore_caret()
    elif args == ['doctor']:
        table = Table(title='ATLAS / NUTCRACKER', border_style='#3a342c', header_style='#ff5a12')
        table.add_column('Tool'); table.add_column('Purpose'); table.add_column('Status')
        for name, purpose, path in backend.tool_status():
            table.add_row(name, purpose, path or 'Not installed')
        console = Console()
        console.print(table)
        console.print('Config:', str(backend.CONFIG), markup=False)
        console.print('Workspace:', str(backend.DATA), markup=False)
        return int(any(not path for name, _, path in backend.tool_status() if name in ('jadx', 'java')))
    elif args == ['reports']:
        for path in backend.reports(): print(path)
    elif args == ['--help']:
        print('ATLAS / NUTCRACKER\n')
        print('  nutcracker             Open the ATLAS terminal interface')
        print('  nutcracker tui         Open the terminal interface')
        print('  nutcracker doctor      Check installed analysis tools')
        print('  nutcracker reports     List saved JSON and PDF reports\n')
        from .native import run
        run(args)
    else:
        from .native import run
        run(args[1:] if args[0] == 'native' else args)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
