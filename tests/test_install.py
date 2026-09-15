"""Installer tests use temporary homes; no live desktop or boot changes."""
import copy
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
from atlas import config, palette, state, user


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atlas-test-')
        self.home=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def tx(self,files,**kwargs):
        with state.lock(self.home): return state.transact(self.home,files,**kwargs)
    def test_dry_run_creates_no_files(self):
        state.transact(self.home,{'config/file':state.value('new')},dry=True)
        self.assertEqual(list(self.home.iterdir()),[])
    def test_original_symlink_and_mode_restored(self):
        p=self.home/'original';p.write_text('data');p.chmod(0o600)
        (self.home/'link').symlink_to('original')
        desired={'original':state.value('style'),'link':state.value('replace link'),'new':state.value('new')}
        self.tx(desired)
        self.tx(desired)
        records=state.load(self.home)['files']
        self.tx({k:v['before'] for k,v in records.items()},restoring=True)
        self.assertTrue((self.home/'link').is_symlink())
        self.assertEqual(p.read_text(),'data')
        self.assertEqual(p.stat().st_mode & 0o777,0o600)
        self.assertFalse((self.home/'new').exists())
        self.assertFalse(state.metadata(self.home,'manifest.json').exists())
    def test_later_user_edit_stops_whole_transaction(self):
        self.tx({'first':state.value('one'),'second':state.value('two')})
        (self.home/'second').write_text('user edit')
        with self.assertRaisesRegex(ValueError,'later edit'):
            self.tx({'first':state.value('changed'),'second':state.value('user edit')})
        self.assertEqual((self.home/'first').read_text(),'one')
    def test_parent_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            (self.home/'escape').symlink_to(other,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'escapes'):
                self.tx({'escape/file':state.value('no')})
            self.assertFalse((Path(other)/'file').exists())
    def test_state_symlink_is_rejected(self):
        root=self.home/'.local/state';root.mkdir(parents=True)
        (root/'atlas-bundle').symlink_to(self.home/'redirect')
        with self.assertRaisesRegex(ValueError,'symlink'): state.load(self.home)
    def test_write_failure_rolls_back_files_and_manifest(self):
        self.tx({'one':state.value('before')})
        baseline=state.metadata(self.home,'manifest.json').read_bytes()
        original=state.write
        raised=False
        def fail_once(path,item):
            nonlocal raised
            if path.name=='two' and not raised:
                raised=True;raise OSError('simulated disk failure')
            return original(path,item)
        with patch.object(state,'write',fail_once):
            with self.assertRaisesRegex(OSError,'simulated'):
                self.tx({'one':state.value('after'),'two':state.value('new')})
        self.assertEqual((self.home/'one').read_text(),'before')
        self.assertFalse((self.home/'two').exists())
        self.assertEqual(state.metadata(self.home,'manifest.json').read_bytes(),baseline)
        self.assertFalse(state.metadata(self.home,'pending.json').exists())
    def test_interrupted_transaction_recovery(self):
        with state.lock(self.home):
            pending={'changes':{'a':{'before':state.value('before'),'after':state.value('after')}},'manifest_before':{'kind':'absent'}}
            state.write(self.home/'a',state.value('after'))
            state.write(state.metadata(self.home,'pending.json'),state.value(json.dumps(pending),0o600))
            with self.assertRaisesRegex(ValueError,'Interrupted'):
                state.transact(self.home,{'a':state.value('other')})
            state.recover(self.home)
        self.assertEqual((self.home/'a').read_text(),'before')
    def test_recovery_preserves_later_edit(self):
        with state.lock(self.home):
            pending={'changes':{'a':{'before':state.value('before'),'after':state.value('after')}},'manifest_before':{'kind':'absent'}}
            state.write(self.home/'a',state.value('a later edit'))
            state.write(state.metadata(self.home,'pending.json'),state.value(json.dumps(pending),0o600))
            with self.assertRaisesRegex(ValueError,'later edit'): state.recover(self.home)


class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.colors=palette.resolve(ROOT/'colors.toml')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atlas user % ')
        self.home=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def write(self,path,text):
        p=self.home/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    def plan(self,components=user.COMPONENTS,**kwargs):
        return user.plan(ROOT,self.home,components,self.colors,**kwargs)
    def apply(self,files):
        with state.lock(self.home): state.transact(self.home,files,user.COMPONENTS)
    def test_all_components_install_idempotently_and_restore(self):
        self.write('.bashrc','# existing shell preferences\n')
        self.write('.local/bin/atlas-vpn', '# prior standalone VPN panel\n')
        desired=self.plan(cli_groups={'all'})
        user.validate(desired);self.apply(desired)
        again=self.plan(cli_groups={'all'})
        self.assertTrue(all(state.snapshot(state.target(self.home,k))==v for k,v in again.items()))
        self.assertEqual(user.plan(ROOT,self.home,user.COMPONENTS,self.colors,syncing=True),
                         {k:v for k,v in desired.items() if k in user.plan(ROOT,self.home,user.COMPONENTS,self.colors,syncing=True)})
        self.assertTrue((self.home/'.local/bin/atlas-info').is_file())
        self.assertTrue(os.access(self.home/'.local/bin/atlas-vpn', os.X_OK))
        self.assertIn('atlas-vpn', (self.home/'.config/atlas/workspace.conf').read_text())
        self.assertTrue((self.home/'.config/atlas/atlas-prompt.py').is_file())
        self.assertTrue((self.home/'.codex/themes/atlas.tmTheme').is_file())
        records=state.load(self.home)['files']
        with state.lock(self.home): state.transact(self.home,{k:v['before'] for k,v in records.items()},restoring=True)
        self.assertEqual((self.home/'.bashrc').read_text(),'# existing shell preferences\n')
        self.assertEqual((self.home/'.local/bin/atlas-vpn').read_text(), '# prior standalone VPN panel\n')
        self.assertFalse((self.home/'.config/omarchy/themes/atlas/colors.toml').exists())
    def test_cli_restore_returns_success(self):
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        for args in (['--components','theme','--offline'],['restore','--dry-run'],['restore']):
            result=subprocess.run([sys.executable,str(ROOT/'install.py'),*args,'--home',str(self.home)],capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_installed_application_commands_launch(self):
        self.apply(self.plan({'apps'}))
        stub_bin=self.home/'stub-bin'
        stub_bin.mkdir()
        for name in ('omarchy','tmux','btop'):
            stub=stub_bin/name
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "'+name+'" "$@"\n')
            stub.chmod(0o755)
        env=dict(os.environ,HOME=str(self.home),PATH=str(stub_bin)+os.pathsep+os.environ['PATH'],
                 TERM='xterm-256color',PYTHONDONTWRITEBYTECODE='1')
        env.pop('TMUX',None)
        expected={
            'atlas-files':'omarchy\nlaunch\nterminal\nyazi\n',
            'atlas-info':'ATLAS / DIRECTORY',
            'atlas-panel':'btop\n',
            'atlas-session':'tmux\nnew-session\n',
            'atlas-theme':'usage:',
        }
        for name,output in expected.items():
            with self.subTest(command=name):
                command=self.home/'.local/bin'/name
                self.assertTrue(os.access(command,os.X_OK),name+' is not executable')
                args=[str(command)]+(['--help'] if name=='atlas-theme' else [])
                result=subprocess.run(args,cwd=self.home,env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn(output,result.stdout)
    def test_existing_app_preferences_are_merged(self):
        self.write('.config/lazygit/config.yml','git:\n  autoFetch: false\n')
        self.write('.config/spotify-player/app.toml','client_id = "recipient-app-id"\n')
        self.write('.config/spotify-player/theme.toml','[[themes]]\nname = "personal"\n')
        desired=self.plan({'apps'})
        self.assertIn('autoFetch: false',state.text_value(desired['.config/lazygit/config.yml']))
        self.assertIn('recipient-app-id',state.text_value(desired['.config/spotify-player/app.toml']))
        self.assertIn('personal',state.text_value(desired['.config/spotify-player/theme.toml']))
        user.validate(desired)
    def test_cli_core_does_not_enable_optional_tools(self):
        desired=self.plan({'cli'})
        self.assertIn('.local/bin/nmap',desired)
        self.assertNotIn('.msf4/msfconsole.rc',desired)
        self.assertNotIn('.local/bin/tcpdump',desired)
    def test_existing_metasploit_startup_is_preserved(self):
        self.write('.msf4/msfconsole.rc','# recipient startup\nsetg TimestampOutput true\n')
        desired=self.plan({'cli'},cli_groups={'cli-metasploit'})
        self.assertIn('setg TimestampOutput true',state.text_value(desired['.msf4/msfconsole.rc']))
    def test_zen_profile_discovery_and_preferences(self):
        self.write('.config/zen/profiles.ini','[Profile0]\nIsRelative=1\nPath=profile 50%\n')
        self.write('.config/zen/profile 50%/user.js','user_pref("example.setting", true);\n')
        result=self.plan({'apps'})
        rel='.config/zen/profile 50%/'
        self.assertIn(rel+'chrome/atlas.css',result)
        self.assertIn('example.setting',state.text_value(result[rel+'user.js']))
    def test_external_browser_profile_is_rejected(self):
        self.write('.config/zen/profiles.ini','[Profile0]\nIsRelative=0\nPath=/outside/private-profile\n')
        with self.assertRaisesRegex(ValueError,'outside'): self.plan({'apps'})
    def test_desktop_only_does_not_require_workspace_shell(self):
        desired=self.plan({'theme','desktop'})
        self.assertNotIn('shell=',state.text_value(desired['.config/foot/foot.ini']))
        self.assertNotIn('.local/bin/atlas-session',desired)
        self.write('.config/foot/foot.ini','[main]\nshell=/bin/zsh\n')
        desired=self.plan({'theme','desktop'})
        self.assertIn('shell=/bin/zsh',state.text_value(desired['.config/foot/foot.ini']))
        with self.assertRaisesRegex(ValueError,'custom shell'): self.plan({'theme','desktop','apps'})
    def test_custom_terminal_shell_preserved(self):
        self.write('.config/foot/foot.ini','[main]\nshell=/bin/zsh\n')
        with self.assertRaisesRegex(ValueError,'custom shell'): self.plan({'apps'})
    def test_shell_merge_preserves_widgets_and_settings(self):
        original={'version':1,'idle':{'lock':123},'bar':{'position':'bottom','layout':{'left':[{'id':'custom.widget','value':42}],'right':[{'id':'atlas.monitor','size':7}]}},'disabledPlugins':['omarchy.monitor'],'plugins':['atlas.lock',{'id':'atlas.polkit'},{'id':'atlas.idle'}, {'id':'custom.service'}],'cloneSourceRestores':['atlas.lock','atlas.polkit','atlas.idle']}
        merged=user.merge_shell(self.home,copy.deepcopy(original),ROOT/'components/desktop')
        self.assertEqual(merged['idle'],original['idle'])
        self.assertEqual(merged['bar']['position'],'bottom')
        self.assertEqual(merged['bar']['layout']['left'],original['bar']['layout']['left'])
        self.assertEqual(merged['bar']['layout']['right'],[{'id':'atlas.monitor','size':7}])
        self.assertNotIn('omarchy.monitor',merged['disabledPlugins'])
        self.assertEqual(user.merge_shell(self.home,copy.deepcopy(merged),ROOT/'components/desktop'),merged)
    def test_unknown_authentication_clone_blocks_install(self):
        self.write('.config/omarchy/plugins/custom.lock/manifest.json',json.dumps({'id':'custom.lock','omarchy':{'clonedFrom':'omarchy.lock'}}))
        shell={'plugins':[{'id':'custom.lock'}]}
        with self.assertRaisesRegex(ValueError,'Another enabled'):
            user.merge_shell(self.home,shell,ROOT/'components/desktop')
    def test_palette_change_updates_apps_without_replacing_runtime(self):
        before=self.plan({'apps'})
        colors=dict(self.colors,accent='#123456',accent_strip='123456',accent_sgr='18;52;86')
        after=user.plan(ROOT,self.home,{'apps'},colors,syncing=True)
        self.assertNotEqual(before['.config/atlas/tmux.conf'],after['.config/atlas/tmux.conf'])
        self.assertFalse(any(k.startswith('.local/share/atlas') for k in after))

if __name__=='__main__': unittest.main()
