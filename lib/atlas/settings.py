"""Small native-menu controls using existing config and the installer journal."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from . import layout, readability, state

MENU_PATH = '.config/omarchy/extensions/omarchy-menu.jsonc'
OPACITY_FILES = ('.config/hypr/looknfeel.lua', '.config/hypr/hyprland.lua')
# Only the bundle's simple all-window rule is editable. Specific app rules stay
# in their original order, including the creator's opaque Zen exception.
OPACITY_RULE = re.compile(r'(?m)^o\.window\("\.\*", \{ opacity = "(?P<value>0\.\d+|1\.0) override (?P=value) override 1\.0 override" \}\)$')
PRESETS = (80, 87, 95, 100)
DEFAULT_OPACITY = 100


def read(home, rel):
    path = state.target(home, rel)
    if path.is_symlink() and not path.resolve().is_relative_to(home):
        raise ValueError(f'Configuration leaves the selected home: {rel}')
    return path.read_text() if path.exists() else ''


def opacity_info(home):
    found = []
    for rel in OPACITY_FILES:
        for match in OPACITY_RULE.finditer(read(home, rel)):
            found.append((rel, round(float(match['value']) * 100)))
    if len(found) != 1:
        raise ValueError('Expected one ATLAS opacity rule; custom or multiple rules need manual review')
    return found[0]


def menu_entries():
    terminal = 'omarchy launch tui atlas-settings '
    entries = {
        'atlas': {'icon': '󰛲', 'label': 'ATLAS', 'description': 'Appearance, component status and maintenance', 'aliases': ['atlas-settings']},
        'atlas.wallpaper': {'icon': '', 'label': 'Wallpaper', 'action': 'atlas-settings wallpaper'},
        'atlas.opacity': {'icon': '󰂵', 'label': 'Window opacity', 'description': 'Fullscreen and app-specific exceptions stay opaque'},
        'atlas.readability': {'label': 'Neovim comments', 'description': 'Choose standard or brighter comments; applies when you return to Neovim'},
        'atlas.readability.standard': {'label': 'Standard', 'action': 'atlas-settings readability standard', 'checked': 'atlas-settings readability-is standard'},
        'atlas.readability.readable': {'label': 'Brighter', 'action': 'atlas-settings readability readable', 'checked': 'atlas-settings readability-is readable'},
        'atlas.layout': {'label': 'Terminal layout', 'description': 'Switch terminal framing; pane controls stay the same'},
        'atlas.layout.classic': {'label': 'Classic', 'action': 'atlas-settings layout classic', 'checked': 'atlas-settings layout-is classic'},
        'atlas.layout.framed': {'label': 'Framed', 'action': 'atlas-settings layout framed', 'checked': 'atlas-settings layout-is framed'},
        'atlas.lock': {'icon': '', 'label': 'Lock screen', 'description': 'Choose the style for your next lock', 'when': 'command -v atlas-lock-style >/dev/null'},
        'atlas.lock.terminal': {'label': 'Terminal', 'action': 'atlas-lock-style terminal', 'checked': 'atlas-lock-style is terminal'},
        'atlas.lock.classic': {'label': 'Classic', 'action': 'atlas-lock-style classic', 'checked': 'atlas-lock-style is classic'},
        'atlas.status': {'icon': '', 'label': 'Component status', 'action': terminal + 'status --pause'},
        'atlas.diagnostics': {'icon': '󰒓', 'label': 'Diagnostics', 'description': 'Check local dependencies and changed configuration', 'action': terminal + 'diagnostics --pause'},
        'atlas.help': {'icon': '󰋖', 'label': 'Shortcuts & help', 'action': terminal + 'help --pause'},
        'atlas.restore': {'icon': '󰁯', 'label': 'Restore files…', 'description': 'Review managed files and saved originals before confirming', 'action': terminal + 'restore --pause'},
    }
    for percent in PRESETS:
        entries[f'atlas.opacity.p{percent}'] = {
            'label': f'{percent}%' + (' · Default' if percent == DEFAULT_OPACITY else ' · Opaque' if percent == 100 else ''),
            'action': f'atlas-settings opacity {percent}',
            'checked': f'atlas-settings opacity-is {percent}',
        }
    return entries


def hyprland_check():
    subprocess.run(['hyprctl', 'reload'], check=True, capture_output=True, text=True, timeout=15)
    result = subprocess.run(['hyprctl', 'configerrors'], check=True, capture_output=True, text=True, timeout=15)
    if result.stdout.strip():
        raise ValueError('Hyprland configuration errors: ' + result.stdout.strip())


def set_opacity(home, percent, live=True):
    if percent not in PRESETS: raise ValueError('Choose 80, 87, 95 or 100 percent')
    with state.lock(home):
        rel, current = opacity_info(home)
        if current == percent: return
        # Establish a clean baseline before touching a live configuration.
        if live: hyprland_check()
        path = state.target(home, rel)
        before = state.snapshot(path)
        if before['kind'] != 'file': raise ValueError('Opacity config must be a regular file')
        number = '1.0' if percent == 100 else f'{percent / 100:.2f}'
        replacement = f'o.window(".*", {{ opacity = "{number} override {number} override 1.0 override" }})'
        after = state.value(OPACITY_RULE.sub(lambda _: replacement, read(home, rel)), before['mode'])
        state.transact(home, {rel: after})
        try:
            if live: hyprland_check()
        except (ValueError, OSError, subprocess.SubprocessError):
            state.transact(home, {rel: before})
            if live: hyprland_check()
            raise


def status(home):
    manifest = state.load(home)
    active = read(home, '.local/state/omarchy/current/theme.name').strip() or 'Unknown'
    print(f'ATLAS / component status\n\nActive theme: {active}')
    font = re.search(r'(?m)^font\s*=\s*(.+)$', read(home, '.config/foot/foot.ini'))
    print('Terminal font: ' + (font[1] if font else 'Foot default / not configured'))
    try: print(f'Window opacity: {opacity_info(home)[1]}% (fullscreen and app exceptions retain their rules)')
    except ValueError: print('Window opacity: custom / not controlled by ATLAS')
    bg = state.target(home, '.local/state/omarchy/current/background')
    print('Wallpaper: ' + (bg.resolve().name if bg.exists() else 'Not detected'))
    try: print('Neovim comments: ' + readability.current(home))
    except ValueError: print('Neovim comments: custom / invalid preference')
    try: print('Terminal layout: ' + layout.current(home))
    except ValueError: print('Terminal layout: custom / invalid preference')
    print()
    probes = {
        'theme': '.config/omarchy/themes/atlas/colors.toml',
        'desktop': '.config/omarchy/themed/neovim.lua.tpl',
        'apps': '.config/atlas/workspace.conf',
        'shell': '.config/omarchy/plugins/atlas.lock/manifest.json',
        'cli': '.local/lib/atlas-cli/atlas_cli/__init__.py',
    }
    for component, path in probes.items():
        installed = component in manifest['components']
        detected = state.target(home, path).exists()
        label = 'Managed by installer' if installed else 'Detected (outside installer)' if detected else 'Not detected'
        if not installed and not detected and component == 'apps':
            if state.target(home, '.config/blackburn/tmux.conf').exists():
                label = 'Legacy integration detected'
        if not installed and not detected and component == 'shell':
            clones = []
            for candidate in (home / '.config/omarchy/plugins').glob('*/manifest.json'):
                info = json.loads(read(home, str(candidate.relative_to(home))))
                if info.get('omarchy', {}).get('clonedFrom') in ('omarchy.lock', 'omarchy.idle', 'omarchy.polkit', 'omarchy.monitor'):
                    clones.append(info['id'])
            if clones: label = 'Custom Omarchy clones detected'
        print(f'{component.capitalize():10} {label}')
    print(f'\nSaved originals: {len(manifest["files"])} managed files')
    if not manifest['components']:
        print('This existing desktop is not a full bundle installation; restoration covers only managed files.')


def diagnostics(home):
    status(home)
    print('\nLocal checks (no uploads)')
    manifest = state.load(home)
    drift = [rel for rel, record in manifest['files'].items()
             if state.snapshot(state.target(home, rel)) != record['installed']]
    pending = state.metadata(home, 'pending.json').exists()
    print('Transaction: ' + ('Interrupted; run atlas-theme recover' if pending else 'No interrupted transaction'))
    print('Managed configuration: ' + (f'{len(drift)} later edits' if drift else 'Matches saved installation'))
    for rel in drift: print('  ' + rel)
    if drift: print('Save and reconcile these edits before updating or restoring; ATLAS will preserve them.')
    for command in ('omarchy', 'hyprctl', 'foot', 'nvim', 'yazi', 'tmux', 'starship', 'btop'):
        print(f'{command}: ' + ('Available' if shutil.which(command) else 'Not installed'))
    legacy = state.target(home, '.config/omarchy/hooks/theme-set.d/blackburn-system')
    if legacy.exists(): print('Legacy theme hook detected; consult docs/MIGRATION.md before a full bundle install.')
    return 1 if drift or pending else 0


def restore(root, home):
    manifest = state.load(home)
    if not manifest['files']:
        print('There are no managed ATLAS files to restore.')
        return 0
    print(f'ATLAS / restore\n\nRestore the saved originals of {len(manifest["files"])} managed files.')
    print('Files created by ATLAS will be removed. Later manual edits block restoration.\n')
    for rel, record in manifest['files'].items():
        print(('REMOVE  ' if record['before']['kind'] == 'absent' else 'RESTORE ') + rel)
    if read(home, '.local/state/omarchy/current/theme.name').strip() == 'atlas':
        print('\nSelect another theme from Omarchy → Style → Theme, then reopen Restore.')
        return 1
    args = [sys.executable, str(root / 'install.py'), 'restore', '--home', str(home)]
    preview = subprocess.run(args + ['--dry-run'], check=False)
    if preview.returncode: return preview.returncode
    if not sys.stdin.isatty():
        print('\nReopen this action in a terminal to confirm restoration.')
        return 1
    if input('\nType RESTORE to apply, or Enter to cancel: ').strip() != 'RESTORE':
        print('Cancelled.'); return 0
    result = subprocess.run(args, check=False)
    if result.returncode == 0 and home == Path.home().resolve():
        hyprland_check()
        print('Log out and back in to load restored configuration and clear session font settings.')
    return result.returncode


def main(root):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='menu', choices=['menu', 'wallpaper', 'opacity', 'opacity-is', 'readability', 'readability-is', 'layout', 'layout-is', 'status', 'diagnostics', 'help', 'restore'])
    parser.add_argument('value', nargs='?')
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--pause', action='store_true', help='Keep reports visible when launched from the menu')
    args = parser.parse_args()
    if args.action in ('opacity', 'opacity-is'):
        if args.value not in tuple(map(str, PRESETS)):
            parser.error(args.action + ' requires 80, 87, 95 or 100')
    elif args.action in ('readability', 'readability-is'):
        if args.value not in readability.PRESETS:
            parser.error(args.action + ' requires standard or readable')
    elif args.action in ('layout', 'layout-is'):
        if args.value not in layout.PRESETS:
            parser.error(args.action + ' requires classic or framed')
    elif args.value is not None:
        parser.error(args.action + ' does not take a value')
    home = args.home.resolve()
    code = 0
    try:
        if args.action in ('menu', 'wallpaper'):
            if home != Path.home().resolve(): raise ValueError('Menu actions require the current home')
            if args.action == 'menu':
                subprocess.run(['omarchy', 'menu', 'summon', 'atlas'], check=True)
            else:
                selection = subprocess.run(['omarchy', 'theme', 'bg-switcher'], capture_output=True, text=True, check=False)
                if selection.returncode == 0 and selection.stdout.strip():
                    subprocess.run(['omarchy', 'theme', 'bg', 'set', selection.stdout.strip()], check=True)
        elif args.action == 'opacity-is':
            try: return int(opacity_info(home)[1] != int(args.value))
            except ValueError: return 1
        elif args.action == 'opacity':
            set_opacity(home, int(args.value), live=home == Path.home().resolve())
        elif args.action == 'readability-is':
            return int(readability.current(home) != args.value)
        elif args.action == 'readability':
            print('ATLAS Neovim comments: ' + readability.select(home, args.value))
        elif args.action == 'layout-is':
            return int(layout.current(home) != args.value)
        elif args.action == 'layout':
            print('ATLAS terminal layout: ' + layout.select(home, args.value, live=home == Path.home().resolve()))
            print('Reopen existing panels once after a code update. Layout changes then follow panel refreshes.')
        elif args.action == 'status': status(home)
        elif args.action == 'diagnostics': code = diagnostics(home)
        elif args.action == 'restore': code = restore(root, home)
        elif args.action == 'help':
            print('ATLAS / everyday shortcuts\n\nCtrl+Space → f  Files (Yazi)\nEnter          Enter a folder / open a file\nRight or l     Enter a folder\nLeft or h      Parent folder\nT              Expand / restore Yazi preview\nCtrl+Space → c  New terminal tab\nCtrl+Space → g  Git Status\nCtrl+Space → p  Ports & Services\nCtrl+Space → a  Agent panel\nCtrl+Space → n  NymVPN panel\n\nNeovim: Space opens the key guide; :q closes the current window.\n\nAppearance: Omarchy → ATLAS, or run atlas-settings.\nOpacity: 100% (default, fully opaque); 80%, 87% and 95% are also available.\nNeovim comments: Standard or Brighter (refreshes on focus).\nTerminal layout: atlas-settings layout framed / classic.\nFonts stay at the configured size; ATLAS uses 9 pt.\n\nDiagnostics are local and preserve manual edits.\nRestore shows the affected files before asking for confirmation.')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'ATLAS: {error}', file=sys.stderr)
        code = 1
        if args.action == 'opacity' and home == Path.home().resolve() and shutil.which('notify-send'):
            subprocess.run(['notify-send', 'ATLAS settings', str(error)], check=False)
    if args.pause and sys.stdin.isatty():
        try: input('\nPress Enter to close… ')
        except (EOFError, KeyboardInterrupt): pass
    return code
