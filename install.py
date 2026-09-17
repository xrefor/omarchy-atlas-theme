#!/usr/bin/env python3
"""Install, maintain, and remove ATLAS for Omarchy."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'lib'))
from atlas import palette, state, user


def preflight(root, home, components, offline=False):
    if 'shell' in components:
        shell=json.loads(user.read(home,'.config/omarchy/shell.json') or '{"version":1}')
        user.merge_shell(home,shell,root/'components/desktop')
    if offline:
        if home == Path.home().resolve():
            raise ValueError('--offline is only allowed with a separate --home staging directory')
        return
    if 'apps' in components:
        legacy=home/'.config/omarchy/hooks/theme-set.d/blackburn-system'
        if legacy.exists() and os.access(legacy,os.X_OK):
            raise ValueError('An active legacy application-theme hook would conflict with ATLAS. Restore/disable it before installing; see docs/MIGRATION.md')
    needed=['omarchy','omarchy-theme-color']
    if 'apps' in components:
        needed+=['bash','tmux','starship','foot','btop']
    if 'shell' in components:
        needed+=['bash','omarchy-shell','omarchy-system-lock','omarchy-system-wake','omarchy-monitor-state',
                 'omarchy-display-text-size','omarchy-hyprland-monitor-scaling','omarchy-brightness-display',
                 'omarchy-hyprland-session-locked','omarchy-hw-laptop-closed','omarchy-launch-screensaver',
                 'hyprctl','ttfx','jq','pgrep','pkill','stty','tty']
        pam=Path('/etc/pam.d/omarchy-lock-password')
        if not pam.is_file() or not pam.read_text().strip():
            raise ValueError('Shell plugins require Omarchy password PAM support; see docs/AUTH.md')
        for plugin in sorted((root/'components/desktop/plugins').iterdir()):
            subprocess.run(['omarchy','plugin','validate',str(plugin)],check=True,capture_output=True,text=True)
    missing=[name for name in needed if not shutil.which(name)]
    if missing: raise ValueError('Missing dependencies: '+', '.join(missing)+'. See docs/DEPENDENCIES.md')
    import yaml


def parse():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',default='install',choices=['install','sync','check','restore','recover','doctor','boot','boot-restore','boot-recover','boot-confirm'])
    parser.add_argument('--all',action='store_true',help='All user components; boot remains a separate explicit command')
    parser.add_argument('--components',default='theme',help='Comma-separated: theme,desktop,apps,shell,cli')
    parser.add_argument('--cli-groups',default='cli-core',help='Comma-separated cli-core,cli-tcpdump,cli-metasploit,cli-shodan,cli-codex, or all')
    parser.add_argument('--home',type=Path,default=Path.home(),help='User destination; use a temporary home for staging')
    parser.add_argument('--palette',type=Path,help='Palette for sync/check or staged generation')
    parser.add_argument('--dry-run',action='store_true',help='Preflight and print changes without writing')
    parser.add_argument('--offline',action='store_true',help='Skip running-session dependency checks in a separate staging home')
    parser.add_argument('--no-refresh',action='store_true',help='Do not refresh running tmux after palette synchronization')
    parser.add_argument('--root',type=Path,default=Path('/'),help='Filesystem root for boot staging/tests')
    parser.add_argument('--esp',type=Path,help='EFI system partition path for boot installation')
    for name in ['limine','plymouth','sddm']: parser.add_argument('--'+name,action='store_true',help='Select this boot component')
    return parser.parse_args()


def run(args):
    if args.action in ('boot','boot-restore','boot-recover','boot-confirm'):
        from atlas import boot
        boot.run(ROOT,args)
        return 0
    home=args.home.resolve()
    if any(c in str(home) for c in '\n\r\x00'):
        raise ValueError('Home directory contains control characters')
    if os.geteuid()==0 and args.action not in ('doctor','check') and not args.dry_run and not (args.offline and home!=Path.home().resolve()):
        raise ValueError('Run user installation as your normal user. Only the separate boot command needs root.')
    components=user.COMPONENTS.copy() if args.all else set(args.components.split(','))
    if components-user.COMPONENTS: raise ValueError('Unknown component: '+','.join(sorted(components-user.COMPONENTS)))
    if components & {'desktop','shell'}: components.add('theme')
    if args.action=='doctor':
        preflight(ROOT,home,components,args.offline)
        colors=palette.resolve(args.palette or ROOT/'colors.toml')
        print('ATLAS prerequisites passed for: '+', '.join(sorted(components)))
        for app in ('yazi','spotify_player','lazygit','lazydocker','zen-browser','nym-vpnd','nym-vpnc','nmap','tcpdump','msfconsole','shodan'):
            print(f'{app}: '+('available' if shutil.which(app) else 'optional application not installed'))
        print('Zen profiles discovered: '+str(len(user.profiles(home))))
        return
    dry=args.dry_run or args.action=='check'
    def operation():
        if args.action=='recover': return state.recover(home,dry)
        manifest=state.load(home)
        if args.action=='restore':
            if not manifest['files']: print('ATLAS has no managed user files.'); return
            # Omarchy generates current theme state outside this file manifest.
            if user.read(home,'.local/state/omarchy/current/theme.name').strip()=='atlas':
                raise ValueError('Select another Omarchy theme before restoring ATLAS user files')
            desired={rel:item['before'] for rel,item in manifest['files'].items()}
            state.transact(home,desired,dry=dry,restoring=True)
            if not dry and home == Path.home().resolve():
                print('Log out and back in to clear ATLAS font settings from the running desktop session.')
            return 0
        sync=args.action in ('sync','check')
        if sync:
            components_now=set(manifest.get('components',[]))
            if not components_now: raise ValueError('No ATLAS installation found')
            path=args.palette or home/'.local/state/omarchy/current/theme/colors.toml'
        else:
            components_now=components
            path=args.palette or ROOT/'colors.toml'
            preflight(ROOT,home,components,args.offline)
        colors=palette.resolve(path)
        desired=user.plan(ROOT,home,components_now,colors,syncing=sync,cli_groups={'all'} if args.all else set(args.cli_groups.split(',')))
        user.validate(desired)
        changed=state.transact(home,desired,components_now,dry=dry)
        if args.action=='check' and changed: return 1
        if sync and changed and not dry and not args.no_refresh and home==Path.home().resolve() and shutil.which('tmux'):
            subprocess.run(['tmux','source-file',str(home/'.config/atlas/tmux.conf')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if not sync and not dry:
            print('Installed ATLAS user components. Activate: omarchy theme set atlas')
            print('Open a new terminal and restart Zen to load their styling. Boot: sudo python3 install.py boot --dry-run')
    if dry: return operation()
    with state.lock(home): return operation()


if __name__=='__main__':
    try:
        raise SystemExit(run(parse()) or 0)
    except (ValueError,OSError,subprocess.SubprocessError,ImportError) as error:
        print(f'ATLAS: {error}',file=sys.stderr)
        raise SystemExit(1)
