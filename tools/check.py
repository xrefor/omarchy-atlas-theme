#!/usr/bin/env python3
"""Validate the distributable without changing the current desktop or boot."""
import ast
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
import yaml

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
ENV=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',NVIM_LOG_FILE=os.devnull)


def run(args,label):
    result=subprocess.run(args,cwd=ROOT,env=ENV,text=True,capture_output=True)
    if result.returncode:
        print(result.stdout[-10000:]);print(result.stderr[-10000:],file=sys.stderr)
        raise SystemExit(f'FAILED: {label}')
    print('PASS: '+label)
    return result


def source_files():
    excluded={'dist','__pycache__','.git','.pytest_cache','.venv'}
    for directory,dirs,files in os.walk(ROOT):
        dirs[:]=sorted(name for name in dirs if name not in excluded)
        for name in sorted(dirs+files):
            path=Path(directory)/name
            if path.is_symlink(): raise SystemExit('Symlink in release source: '+str(path))
        for name in sorted(files):
            yield Path(directory)/name


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable',action='store_true',help='Run headless checks; omit installed Omarchy/Neovim/QML integration')
    args=parser.parse_args()
    required=['git','bash','node','lua','omarchy-theme-color']
    if args.portable: required.append('tmux')
    missing=[command for command in required if not shutil.which(command)]
    if missing: raise SystemExit('Missing test dependencies: '+', '.join(missing)+'. See docs/VALIDATION.md.')
    ENV['ATLAS_TEST_PORTABLE']='1' if args.portable else '0'
    result=run([sys.executable,'-m','unittest','discover','-s','tests','-v'],'Python installer, boot and CLI tests')
    for line in result.stderr.splitlines():
        if line.startswith(('Ran ','OK')) or '... skipped ' in line: print(line)
    spec=importlib.util.spec_from_file_location('atlas_auth_checks',ROOT/'tests/test_auth_bundle.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    count=0
    for name in sorted(vars(mod)):
        if name.startswith('test_') and callable(getattr(mod,name)):
            getattr(mod,name)();count+=1
    print(f'PASS: {count} authentication boundary checks')
    for model in ('idle','matrix','monitor','polkit'):
        result=run(['node',f'tests/{model}_model_test.cjs'],model+' model behavior')
        for line in result.stdout.splitlines():
            if line.startswith(('ℹ tests ', '# tests ')): print(line)
    run(['lua','tests/mount_cross_test.lua'],'7 mocked drive-menu checks')
    run(['lua','tests/yazi_enter_test.lua'],'Yazi Enter navigation and file-opening behavior')
    run(['lua','tests/yazi_preview_test.lua'],'Yazi preview expansion and layout restoration')
    if args.portable:
        print('SKIP: Neovim UI integration (portable mode; needs installed editor plugins)')
    elif shutil.which('nvim'):
        result=run(['nvim','--headless','--clean','-i','NONE','-l','tests/neovim_ui_test.lua'],'Neovim UI integration')
        if 'SKIP:' in result.stdout + result.stderr: print((result.stdout + result.stderr).strip())
    else: print('SKIP: Neovim UI integration (Neovim not installed)')
    checked=0
    for path in source_files():
        suffix=path.suffix
        if suffix=='.py': ast.parse(path.read_text(),filename=str(path));checked+=1
        elif suffix=='.json': json.loads(path.read_text());checked+=1
        elif suffix=='.toml': tomllib.loads(path.read_text());checked+=1
        elif suffix in ('.yaml','.yml'): yaml.safe_load(path.read_text());checked+=1
        elif suffix in ('.svg','.tmTheme'): ET.fromstring(path.read_bytes());checked+=1
        with path.open('rb') as source: data=source.read(32)
        if suffix=='.bash' or data.startswith((b'#!/bin/bash',b'#!/usr/bin/env bash',b'#!/bin/sh')):
            run(['bash','-n',str(path)],str(path.relative_to(ROOT))+' shell syntax')
    print(f'PASS: {checked} structured source/configuration files')
    if args.portable:
        print('SKIP: Omarchy plugin validation (portable mode; needs installed Omarchy)')
    elif shutil.which('omarchy'):
        for plugin in sorted((ROOT/'components/desktop/plugins').iterdir()):
            run(['omarchy','plugin','validate',str(plugin)],plugin.name+' manifest')
    else: print('SKIP: Omarchy plugin validation (Omarchy not installed)')
    if args.portable:
        print('SKIP: QML lint (portable mode; needs installed Quickshell/Omarchy modules)')
    elif shutil.which('qmllint'):
        for qml in sorted((ROOT/'components/desktop/plugins').glob('*/*.qml')):
            run(['qmllint',str(qml)],str(qml.relative_to(ROOT))+' QML lint')
    else: print('SKIP: QML lint (qmllint not installed)')
    if shutil.which('tmux'):
        run([sys.executable, 'tests/vpn_tmux.py'], 'VPN panel mode/settings controls in isolated tmux')
    else: print('SKIP: VPN UI tests (tmux not installed)')
    # Root theme previews and templates must represent the same palette.
    sys.path.insert(0,str(ROOT/'lib'))
    from atlas import palette
    colors=palette.resolve(ROOT/'colors.toml')
    for name in ('shell.toml','hyprland.lua','neovim.lua','gtk-3.0.css','gtk-4.0.css'):
        expected=palette.render(ROOT/'components/desktop/themed'/(name+'.tpl'),colors)
        if (ROOT/name).read_text()!=expected: raise SystemExit('Regenerate stale root theme file: '+name)
    print('PASS: root theme matches the shared palette/templates')
    print('All checks completed. No live desktop or boot changes were made.')

if __name__=='__main__': main()
