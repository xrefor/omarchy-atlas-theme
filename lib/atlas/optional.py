"""Interactive, opt-in installation of applications with ATLAS integrations."""
from pathlib import Path
import shutil
import subprocess
import sys

if __package__:
    from . import nym_cli
else:
    import nym_cli


APPS = (
    ('Yazi file manager', ('yazi',), ('yazi',), False),
    ('Spotify terminal player (requires Spotify login)', ('spotify_player',), ('spotify-player',), False),
    ('Lazygit', ('lazygit',), ('lazygit',), False),
    ('Lazydocker (requires a configured Docker service)', ('lazydocker',), ('lazydocker',), False),
    ('Zen Browser', ('zen-browser', 'zen'), ('zen-browser-bin',), True),
    ('NymVPN daemon and app (requires a Nym account; panel also needs matching nym-vpnc)',
     ('nym-vpnd',), ('nym-vpnd-bin', 'nym-vpn-app-bin'), True),
)


def available(command):
    return bool(shutil.which(command) or (Path.home()/'.local/bin'/command).is_file())


def install():
    if not sys.stdin.isatty():
        print('Optional applications skipped: run python3 lib/atlas/optional.py in a terminal to choose them.')
        return
    print('\nOptional applications for ATLAS integrations. Enter keeps each application uninstalled.')
    print('Selected packages use Omarchy package management; AUR choices are marked. Accounts remain separate.')
    for label, commands, packages, aur in APPS:
        if any(available(command) for command in commands):
            continue
        command = ['omarchy', 'pkg'] + (['aur'] if aur else []) + ['add', *packages]
        print('\n'+label+(' [AUR]' if aur else '')+'\n  '+' '.join(command))
        try:
            answer = input('Install? [y/N] ').strip().lower()
        except EOFError:
            return
        if answer not in ('y', 'yes'):
            continue
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print(f'Optional install failed: {error}. You can retry later; continuing ATLAS installation.')
    if available('nym-vpnd'):
        if not available('nym-vpnc'):
            nym_cli.offer()
        print('\nNymVPN setup: after installation, open Ctrl+Space then N for service startup and account setup.')
        if not available('nym-vpnc'):
            print('Tunnel controls still need nym-vpnc matching the daemon; service setup remains available. See docs/VPN.md.')


if __name__ == '__main__':
    try:
        install()
    except KeyboardInterrupt:
        print('\nOptional application selection cancelled.', file=sys.stderr)
        raise SystemExit(130)
