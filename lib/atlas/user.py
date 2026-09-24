"""Build user-level installation plans from the bundle's explicit components."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import tomllib
from . import config, lock_style, palette, readability, settings, state

COMPONENTS = {'theme', 'desktop', 'apps', 'shell', 'cli'}


def retired_panel_file(rel):
    """Match only payload paths owned by removed terminal panels."""
    if rel in ('.local/bin/atlas-panel',
               '.local/share/atlas/components/apps/bin/atlas-panel'):
        return True
    for panel in ('system', 'maintain'):
        if rel in (f'.local/bin/atlas-{panel}',
                   f'.config/atlas/{panel}-palette.json',
                   f'.local/share/atlas/components/apps/bin/atlas-{panel}'):
            return True
        if rel.startswith(f'.local/share/atlas/components/apps/atlas_{panel}/'):
            return True
    return False


def read(home, rel):
    path = state.target(home, rel)
    if path.is_symlink() and not path.resolve().is_relative_to(home):
        raise ValueError(f'Refusing to read configuration outside target home: {rel}')
    return path.read_text() if path.exists() else ''


def files_under(root):
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        if path.is_symlink():
            raise ValueError(f'Bundle payload may not contain symlinks: {path}')
        if path.is_file():
            yield path


def profiles(home):
    found=[]
    # Native Zen profiles and standard Flatpak profile location.
    for base in ('.config/zen', '.zen', '.var/app/app.zen_browser.zen/.zen'):
        text = read(home, base + '/profiles.ini')
        if not text: continue
        ini = configparser.ConfigParser(interpolation=None)
        ini.read_string(text)
        for name in ini.sections():
            if not name.startswith('Profile') or not ini.has_option(name, 'Path'): continue
            path = Path(ini.get(name, 'Path'))
            path = home/base/path if ini.get(name, 'IsRelative', fallback='1') == '1' else path
            if not path.resolve().is_relative_to(home):
                raise ValueError('Zen profile is outside the selected home directory')
            if path.is_dir(): found.append(str(path.resolve().relative_to(home)))
    return sorted(set(found))


def foot_shell(text):
    # Foot starts in main even without a header, and permits reopening sections.
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.read_string('[main]\n' + text)
    return ini.get('main', 'shell', fallback='')


def set_foot_shell(text, shell):
    section='main'
    lines=[]
    replaced=False
    for line in text.splitlines(keepends=True):
        header=configparser.ConfigParser.SECTCRE.match(line.strip())
        if header: section=header.group('header')
        if section=='main' and re.match(r'\s*shell\s*=',line):
            line='shell='+shell+'\n'
            replaced=True
        lines.append(line)
    # The unnamed main section exists even in files starting with another section.
    return ''.join(lines) if replaced else 'shell='+shell+'\n'+text


def plan(root, home, components, colors, syncing=False, cli_groups=None):
    files={}
    app=root/'components/apps'
    desktop=root/'components/desktop'
    def put(rel, text, mode=0o644): files[rel]=state.value(text, mode)
    def get(rel):
        return state.text_value(files[rel]) if rel in files else read(home, rel)
    def source(path, rel, mode=None):
        data=path.read_bytes()
        put(rel, data, mode or (0o755 if path.stat().st_mode & 0o111 else 0o644))
    def tree(path, rel, mode=None):
        for item in files_under(path): source(item, str(Path(rel)/item.relative_to(path)), mode)
    def template(name): return palette.render(app/'templates'/name, colors)
    def merge_toml(rel, overlay, mode=0o644):
        current = tomllib.loads(get(rel))
        put(rel, config.toml(config.merge(current, overlay)), mode)
    def merge_yaml(rel, text):
        import yaml
        current=yaml.safe_load(get(rel)) or {}
        if not isinstance(current, dict): raise ValueError(f'Expected mapping in {rel}')
        put(rel, yaml.safe_dump(config.merge(current, yaml.safe_load(text)), sort_keys=False, allow_unicode=True))
    if components & {'theme', 'desktop'} and not syncing:
        put(readability.PREFERENCE, readability.current(home) + '\n')
    if 'theme' in components and not syncing:
        prefix='.config/omarchy/themes/atlas/'
        for name in ('colors.toml','icons.theme','keyboard.rgb','chromium.theme','preview.png','unlock.png','screensaver-mark.png','shell.toml','hyprland.lua','neovim.lua','gtk-3.0.css','gtk-4.0.css'):
            source(root/name, prefix+name)
        tree(root/'backgrounds', prefix+'backgrounds')
    if 'desktop' in components and not syncing:
        tree(desktop/'themed', '.config/omarchy/themed')
        tree(desktop/'terminals', '.config')
        # Terminal typography alone must not add the optional tmux workspace
        # or overwrite a recipient's existing shell command.
        existing=foot_shell(read(home,'.config/foot/foot.ini'))
        if existing:
            rel='.config/foot/foot.ini'
            put(rel,set_foot_shell(get(rel),existing))
        tree(desktop/'fontconfig', '.config/fontconfig')
        source(desktop/'shell.toml', '.config/omarchy/shell.toml')
        for version in ('3.0','4.0'):
            rel=f'.config/gtk-{version}/gtk.css'
            css=get(rel)
            imp=f'@import url("../../.local/state/omarchy/current/theme/gtk-{version}.css");'
            if imp not in css: put(rel, imp+'\n'+css)
            rel=f'.config/gtk-{version}/settings.ini'
            ini=configparser.ConfigParser(interpolation=None)
            ini.optionxform=str
            ini.read_string(get(rel))
            if not ini.has_section('Settings'): ini.add_section('Settings')
            ini.set('Settings','gtk-font-name','IBM Plex Sans 11')
            import io
            out=io.StringIO(); ini.write(out); put(rel,out.getvalue())
        rel='.config/uwsm/env'
        put(rel,config.block(get(rel),'FONTS','export FONTCONFIG_FILE="$HOME/.config/fontconfig/atlas.conf"'))
        rel='.config/hypr/looknfeel.lua'
        appearance='''hl.env("FONTCONFIG_FILE", os.getenv("HOME") .. "/.config/fontconfig/atlas.conf")
hl.env("PATH", os.getenv("HOME") .. "/.local/bin:" .. (os.getenv("PATH") or "/usr/bin"))'''
        try: opacity_path, percent = settings.opacity_info(home)
        except ValueError: opacity_path, percent = rel, settings.DEFAULT_OPACITY
        zen_opacity = 'o.window("^zen$", { opacity = "1.0 override 1.0 override 1.0 override" })'
        if opacity_path == rel:
            opacity = '1.0' if percent == 100 else f'{percent / 100:.2f}'
            # Move an existing simple rule into the managed block without duplicating it.
            current = settings.OPACITY_RULE.sub('', get(rel))
            appearance += f'\no.window(".*", {{ opacity = "{opacity} override {opacity} override 1.0 override" }})'
            appearance += '\n-- Keep Zen Browser fully opaque in every window state.\n' + zen_opacity
        else:
            current = get(rel)
            # Main-config rules load after looknfeel; keep the exception after
            # the existing catchall in that file as well.
            put(opacity_path, config.block(get(opacity_path), 'ZEN OPACITY', zen_opacity, '--'))
        put(rel,config.block(current,'APPEARANCE',appearance,'--'))
        rel='.config/hypr/bindings.lua'
        put(rel,config.block(get(rel),'FLOATING WINDOWS','''-- Super+T keeps its tile/float toggle, with a centered 75% floating size.
hl.unbind("SUPER + T")
o.bind("SUPER + T", "Toggle window floating/tiling", function()
  local window = hl.get_active_window()
  if not window then return end
  local was_floating = window.floating
  hl.dispatch(hl.dsp.window.float({ action = "toggle", window = window }))
  if was_floating or not window.floating then return end
  local monitor = window.monitor
  if not monitor then return end
  local width, height = monitor.width, monitor.height
  -- Monitor dimensions are physical pixels; dispatchers use logical pixels.
  if monitor.transform % 2 == 1 then width, height = height, width end
  hl.dispatch(hl.dsp.window.resize({
    x = math.floor(width / monitor.scale * 0.75),
    y = math.floor(height / monitor.scale * 0.75),
    relative = false,
    window = window,
  }))
  hl.dispatch(hl.dsp.window.center({ window = window }))
end)''','--'))
    if 'apps' in components:
        for rel, name in {
            '.config/starship.toml':'starship.toml',
            '.config/atlas/tmux.conf':'tmux.conf',
            '.config/atlas/terminal-colors.bash':'listings.bash',
            '.config/btop/themes/atlas-current.theme':'btop.theme',
        }.items(): put(rel,template(name))
        merge_toml('.config/yazi/theme.toml',tomllib.loads(template('yazi.toml')))
        put('.config/yazi/atlas.tmTheme', template('yazi.tmTheme'))
        spotify=tomllib.loads(get('.config/spotify-player/theme.toml'))
        incoming=tomllib.loads(template('spotify.toml'))
        for key, entries in incoming.items():
            if isinstance(entries,list):
                old=spotify.get(key,[])
                names={entry.get('name') for entry in entries if isinstance(entry,dict)}
                spotify[key]=[entry for entry in old if not isinstance(entry,dict) or entry.get('name') not in names]+entries
            else: spotify[key]=entries
        put('.config/spotify-player/theme.toml', config.toml(spotify))
        merge_yaml('.config/lazygit/config.yml',template('lazygit.yml'))
        merge_yaml('.config/lazydocker/config.yml',template('lazydocker.yml'))
        discordo_rel='.config/discordo/config.toml'
        discordo_path=state.target(home,discordo_rel)
        discordo_mode=stat.S_IMODE(discordo_path.stat().st_mode) if discordo_path.exists() else 0o600
        merge_toml(discordo_rel,tomllib.loads(template('discordo.toml')),discordo_mode)
        prof=profiles(home)
        for path in prof:
            put(path+'/chrome/atlas.css',template('zen.css'))
            put(path+'/chrome/atlas-content.css',template('zen-content.css'))
        put('.config/atlas/palette.bash',shell_palette(colors))
        panel_palette=json.dumps({key: colors[key] for key in
            ('background','lighter_background','foreground','dark_foreground','bright_foreground',
             'secondary','muted','accent','green','yellow','red')})+'\n'
        for panel in ('vpn','agents','projects','ports'):
            put(f'.config/atlas/{panel}-palette.json',panel_palette)
        revision=hashlib.sha256(json.dumps(colors,sort_keys=True).encode()).hexdigest()[:20]
        put('.config/atlas/revision',revision+'\n')
        if not syncing:
            # Archive extraction may discard execute bits; installed commands need them.
            tree(app/'bin','.local/bin',0o755)
            source(app/'shell.bash','.config/atlas/shell.bash')
            source(app/'atlas-prompt.py','.config/atlas/atlas-prompt.py')
            put('.config/yazi/plugins/mount.yazi/main.lua',template('mount-main.lua'))
            source(app/'mount-cross.lua','.config/yazi/plugins/mount.yazi/cross.lua')
            source(root/'LICENSES/mount.yazi-MIT.txt','.config/yazi/plugins/mount.yazi/LICENSE')
            source(app/'atlas-enter.lua','.config/yazi/plugins/atlas-enter.yazi/main.lua')
            source(app/'atlas-preview.lua','.config/yazi/plugins/atlas-preview.yazi/main.lua')
            merge_toml('.config/yazi/yazi.toml',{'mgr':{'ratio':[1,4,3],'sort_by':'natural','sort_dir_first':True,'show_hidden':False,'show_symlink':True,'linemode':'size'},'preview':{'max_width':800,'max_height':800,'image_filter':'triangle','image_quality':75}})
            keymap=tomllib.loads(get('.config/yazi/keymap.toml'))
            keys=keymap.setdefault('mgr',{}).setdefault('prepend_keymap',[])
            for on, run, desc in [('<Enter>','plugin atlas-enter','Enter directory or open file'),('T','plugin atlas-preview','Toggle expanded preview'),('M','plugin mount','ATLAS Drives'),(['g','m'],'plugin mount','ATLAS Drives'),(['g','d'],'cd ~/Downloads','Downloads')]:
                keys[:]=[key for key in keys if key.get('on') != on]
                keys.append({'on':on,'run':run,'desc':desc})
            put('.config/yazi/keymap.toml',config.toml(keymap))
            merge_toml('.config/spotify-player/app.toml',{'theme':'atlas','progress_bar_type':'Line'})
            rel='.config/btop/btop.conf'
            text=get(rel)
            for key,val in [('color_theme','"atlas-current"'),('rounded_corners','false'),('proc_gradient','false')]: text=config.setting(text,key,val)
            put(rel,text)
            rel='.config/foot/foot.ini'
            foot=get(rel)
            if not foot: foot='[main]\ninclude=~/.local/state/omarchy/current/theme/foot.ini\n'
            existing=foot_shell(foot)
            session=str(home/'.local/bin/atlas-session')
            if existing and shlex.split(existing) != [session]:
                raise ValueError('Foot already has a custom shell. Save/merge it before installing the ATLAS terminal workspace.')
            # Preserve an existing workspace command, including its formatting.
            if not existing: foot=set_foot_shell(foot,shlex.quote(session))
            put(rel,foot)
            rel='.bashrc'
            put(rel,config.block(get(rel),'SHELL','''export PATH="$HOME/.local/bin:$PATH"
source "$HOME/.config/atlas/shell.bash"
if command -v starship >/dev/null 2>&1; then eval "$(starship init bash)"; fi'''))
            source(app/'tmux.conf','.config/atlas/workspace.conf')
            rel='.config/tmux/tmux.conf'
            put(rel,config.block(get(rel),'WORKSPACE','source-file ~/.config/atlas/workspace.conf'))
            rel='.config/hypr/bindings.lua'
            put(rel,config.block(get(rel),'APPLICATIONS','''hl.unbind("SUPER + SHIFT + F")
o.bind("SUPER + SHIFT + F", "Files / Yazi", { launch = "atlas-files" })
hl.unbind("SUPER + SHIFT + ALT + M")
o.bind("SUPER + SHIFT + ALT + M", "Music / Spotify player", { tui = "spotify_player", focus = true })''','--'))
            for path in prof:
                for filename,css in [('userChrome.css','atlas.css'),('userContent.css','atlas-content.css')]:
                    rel=path+'/chrome/'+filename
                    text=get(rel)
                    imp=f'@import url("{css}");'
                    if imp not in text: put(rel,imp+'\n'+text)
                rel=path+'/user.js'
                put(rel,config.block(get(rel),'BROWSER CHROME','user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);','//'))
    if 'shell' in components and not syncing:
        put(lock_style.PREFERENCE, lock_style.current(home) + '\n')
        tree(desktop/'plugins','.config/omarchy/plugins')
        tree(desktop/'branding','.config/omarchy/branding')
        tree(desktop/'bin','.local/bin')
        rel='.config/omarchy/shell.json'
        shell=json.loads(get(rel) or '{"version":1}')
        shell=merge_shell(home, shell, desktop)
        put(rel,json.dumps(shell,indent=2)+'\n')
    if 'cli' in components and not syncing:
        spec=json.loads((root/'components/cli/install-map.json').read_text())
        allowed={'cli-core','cli-tcpdump','cli-metasploit','cli-shodan','cli-codex'}
        chosen=allowed if cli_groups=={'all'} else (set(cli_groups or [])|{'cli-core'})
        if chosen-allowed: raise ValueError('Unknown CLI group: '+','.join(sorted(chosen-allowed)))
        if spec.get('version')!=1 or not isinstance(spec.get('files'),list): raise ValueError('Unsupported CLI install map')
        seen=set()
        for item in spec['files']:
            if not isinstance(item,dict) or not all(isinstance(item.get(k),str) for k in ('source','target','mode','group')):
                raise ValueError('Invalid CLI map record')
            if item['mode'] not in ('0644','0755') or item['group'] not in allowed or item['target'] in seen:
                raise ValueError('Invalid CLI permissions/group or duplicate target')
            seen.add(item['target'])
            src=state.target(root/'components/cli',item['source'])
            state.target(home,item['target'])
            if src.is_symlink() or not src.is_file(): raise ValueError('CLI source must be a regular file')
            if item['group'] not in chosen: continue
            if item['target']=='.msf4/msfconsole.rc':
                put(item['target'],config.block(get(item['target']),'METASPLOIT',src.read_text()))
            else:
                source(src,item['target'],int(item['mode'],8))
        rel='.bashrc'
        put(rel,config.block(get(rel),'CLI PATH','export PATH="$HOME/.local/bin:$PATH"'))
    if not syncing:
        # Keep the runtime and explicit payload in user space so palette hooks and
        # removal work after the downloaded archive has been deleted.
        for directory in ('lib','components','backgrounds','assets','LICENSES'):
            tree(root/directory,'.local/share/atlas/'+directory)
        for name in ('install.py','settings.py','VERSION','colors.toml','icons.theme','keyboard.rgb','chromium.theme','preview.png','unlock.png','screensaver-mark.png','shell.toml','hyprland.lua','neovim.lua','gtk-3.0.css','gtk-4.0.css','LICENSE'):
            source(root/name,'.local/share/atlas/'+name)
        put('.local/bin/atlas-theme','#!/bin/sh\nexec python3 "$HOME/.local/share/atlas/install.py" "$@"\n',0o755)
        source(app/'bin/atlas-settings', '.local/bin/atlas-settings', 0o755)
        put(settings.MENU_PATH, config.menu_extension(get(settings.MENU_PATH), settings.menu_entries()))
        if 'apps' in components:
            put('.config/omarchy/hooks/theme-set.d/atlas-system','#!/bin/sh\nexec "$HOME/.local/bin/atlas-theme" sync\n',0o755)
    if 'apps' in components and not syncing:
        # Retire only journaled payloads, restoring anything predating ATLAS.
        # Keeping these records preserves normal drift protection and recovery
        # until the user performs a complete uninstall.
        for rel, record in state.load(home)['files'].items():
            if retired_panel_file(rel):
                files[rel] = record['before']
    return files


def shell_palette(colors):
    fzf=','.join(f'{key}:{colors[role]}' for key,role in {
        'fg':'foreground','bg':'background','hl':'accent','fg+':'bright_foreground',
        'bg+':'selection','hl+':'accent','border':'muted','label':'secondary',
        'info':'secondary','prompt':'accent','pointer':'accent','marker':'accent',
        'spinner':'accent','header':'secondary','gutter':'background',
        'preview-bg':'background','preview-fg':'foreground'}.items())
    text='# Generated from the active Omarchy palette.\n'
    text+='export FZF_DEFAULT_OPTS='+shlex.quote('--color='+fzf+' --border=sharp --layout=reverse --info=inline --pointer=› --marker=▎')+'\n'
    text+='export JQ_COLORS='+shlex.quote(':'.join('0;38;2;'+colors[k+'_sgr'] for k in ['secondary','accent','accent','foreground','green','foreground','foreground','secondary']))+'\n'
    text+="export SUDO_PROMPT=$'\\e[38;2;"+colors['accent_sgr']+'mAUTH / \\e[38;2;'+colors['foreground_sgr']+'m%p\\e[38;2;'+colors['accent_sgr']+"m →\\e[0m '\n"
    return text


def validate(files):
    import yaml
    for rel,item in files.items():
        # Retirement restores original content, which need not be valid config.
        if item['kind']!='file' or retired_panel_file(rel): continue
        if rel.endswith('.toml'): tomllib.loads(state.text_value(item))
        if rel.endswith(('.yml','.yaml')): yaml.safe_load(state.text_value(item))
        if rel.endswith('.json'): json.loads(state.text_value(item))
        if rel.endswith('.jsonc'): config.jsonc(state.text_value(item))


def merge_shell(home, shell, desktop):
    def plugin_id(item):
        if isinstance(item,str): return item
        if isinstance(item,dict) and isinstance(item.get('id'),str): return item['id']
        raise ValueError('Malformed plugin entry in shell.json')
    for key in ('plugins','disabledPlugins','cloneSourceRestores'):
        if not isinstance(shell.get(key,[]),list): raise ValueError(f'{key} must be an array in shell.json')
    for key in ('disabledPlugins','cloneSourceRestores'):
        if any(not isinstance(x,str) for x in shell.get(key,[])): raise ValueError(f'{key} must contain plugin IDs')
    sources={}
    for path in sorted((desktop/'plugins').glob('*/manifest.json')):
        item=json.loads(path.read_text()); sources[item['omarchy']['clonedFrom']]=item['id']
    if len(sources)!=4: raise ValueError('Shell payload is incomplete')
    aliases=sources
    layout=shell.get('bar',{}).get('layout',{})
    active={plugin_id(p) for p in shell.get('plugins',[])}
    for items in layout.values():
        if not isinstance(items,list): raise ValueError('Bar sections must be arrays')
        active.update(plugin_id(p) for p in items)
    disabled=set(shell.get('disabledPlugins',[]))
    conflicts=[]
    for p in (home/'.config/omarchy/plugins').glob('*/manifest.json'):
        if not p.resolve().is_relative_to(home): raise ValueError('Plugin manifest escapes user home')
        item=json.loads(p.read_text()); name=item.get('id')
        if name in active-disabled and item.get('omarchy',{}).get('clonedFrom') in sources and name not in aliases and name not in sources.values():
            conflicts.append(name)
    if conflicts:
        import shlex
        commands='\n'.join('  omarchy plugin disable '+shlex.quote(name) for name in sorted(conflicts))
        raise ValueError('Another enabled shell clone owns an ATLAS service. Conflicting plugins: '
                         +', '.join(sorted(conflicts))+'\nDisable these plugins, then rerun the installer:\n'+commands
                         +'\nTheir files are preserved. To keep them active, omit the shell component.')
    def remap(item):
        name=plugin_id(item)
        if name not in aliases: return item
        if isinstance(item,str): return aliases[name]
        return dict(item,id=aliases[name])
    reference=json.loads((desktop/'bar.json').read_text())
    if not layout:
        shell['bar']=reference
    else:
        # Keep the recipient's modules, placement and per-widget options.
        bar=shell.setdefault('bar',{})
        bar['transparent']=reference.get('transparent',False)
        for section,items in layout.items():
            seen=set(); result=[]
            for item in items:
                updated=remap(item); name=plugin_id(updated)
                if name=='atlas.monitor' and name in seen: continue
                seen.add(name); result.append(updated)
            layout[section]=result
    services=set(sources.values())-{'atlas.monitor'}
    result=[]; seen=set()
    for item in shell.get('plugins',[]):
        item=remap(item); name=plugin_id(item)
        if name in seen: continue
        seen.add(name); result.append(item)
    result += [{'id':name} for name in sorted(services-seen)]
    shell['plugins']=result
    service_sources=set(sources)-{'omarchy.monitor'}
    shell['disabledPlugins']=sorted((disabled|service_sources)-set(sources.values())-{'omarchy.monitor'})
    shell['cloneSourceRestores']=sorted(set(shell.get('cloneSourceRestores',[]))|services)
    return shell
