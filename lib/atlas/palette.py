"""Resolve Omarchy's semantic palette and render ATLAS application templates."""
from pathlib import Path
import re
import subprocess
import tomllib


def resolve(path):
    raw = tomllib.loads(Path(path).read_text())
    result = subprocess.run(['omarchy-theme-color', '--file', str(path), '--all'],
                            text=True, capture_output=True, check=True)
    colors = dict(line.split('\t', 1) for line in result.stdout.splitlines() if '\t' in line)
    colors['secondary'] = raw.get('secondary', colors['light_foreground'])
    required = ('background foreground accent secondary muted selection selection_background '
                'selection_foreground lighter_background dark_background bright_foreground '
                'red green blue yellow magenta cyan bright_red bright_green bright_yellow '
                'bright_blue bright_magenta bright_cyan').split()
    for key in required:
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', colors.get(key, '')):
            raise ValueError(f'Invalid resolved color: {key}')
    for key, color in list(colors.items()):
        if re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            colors[key + '_strip'] = color[1:]
            colors[key + '_sgr'] = ';'.join(str(int(color[i:i+2], 16)) for i in (1, 3, 5))
    colors['mode'] = 'light' if colors.get('mode') == 'light' else 'dark'
    return colors


def render(path, colors):
    return re.sub(r'\{\{\s*(\w+)\s*\}\}', lambda match: colors[match[1]], Path(path).read_text())
