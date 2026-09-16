"""Apply ATLAS presentation without changing Nutcracker's commands or results."""
import sys
import os
from pathlib import Path
from functools import wraps
import click
from rich.console import Console
from rich.theme import Theme
from rich.text import Text
from .backend import CONFIG, DATA

PALETTE = {
    'red': '#e84528', 'green': '#8a9a4a', 'yellow': '#f0a202',
    'cyan': '#a69b8c', 'blue': '#6a8aa0', 'magenta': '#a03c2a',
    'white': '#d6cfc4', 'bright_white': '#f2ebe0', 'dim': '#6e675c',
    'accent': '#ff5a12',
}


def run(args):
    import nutcracker_core.cli as upstream
    theme = Theme(PALETTE)
    seen = set()
    for name, module in list(sys.modules.items()):
        if not name.startswith('nutcracker_core') or module is None:
            continue
        for value in vars(module).values():
            if isinstance(value, Console) and id(value) not in seen:
                value.push_theme(theme)
                seen.add(id(value))

    def banner():
        from nutcracker_core.orchestrator import console
        title = Text('\nATLAS', style='bold accent')
        title.append(' / NUTCRACKER', style='#d6cfc4')
        console.print(title)
        console.print('Android application analysis\n', style='dim')
    upstream._print_banner = banner

    def defaults(command):
        for param in command.params:
            if param.name == 'config_path':
                param.default = str(CONFIG)
        if isinstance(command, click.Group):
            for child in command.commands.values():
                defaults(child)
        elif command.callback is not None:
            callback = command.callback
            @wraps(callback)
            def invoke(*positional, **kwargs):
                previous = Path.cwd()
                for param in command.params:
                    value = kwargs.get(param.name)
                    if isinstance(value, str) and value and (
                        isinstance(param.type, click.Path)
                        or param.name in ('config_path', 'report', 'scripts_dir')
                        or param.name in ('target', 'url') and Path(value).exists()
                    ):
                        path = Path(value).expanduser()
                        if not path.is_absolute() and click.get_current_context().get_parameter_source(param.name) == click.core.ParameterSource.DEFAULT:
                            path = DATA / path
                        kwargs[param.name] = str(path.resolve())
                os.chdir(DATA)
                try:
                    return callback(*positional, **kwargs)
                finally:
                    os.chdir(previous)
            command.callback = invoke
    defaults(upstream.cli)
    upstream.cli(args=args, prog_name='nutcracker')
