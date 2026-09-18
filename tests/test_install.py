"""Installer tests use temporary homes; no live desktop or boot changes."""
import copy
import configparser
import json
import os
import shlex
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
    def test_unchanged_transaction_does_not_write_or_snapshot_manifest(self):
        desired={'config/file':state.value('installed')}
        self.tx(desired,components={'theme'})
        manifest=state.metadata(self.home,'manifest.json')
        before=manifest.stat()
        original_snapshot=state.snapshot
        def snapshot(path):
            self.assertNotEqual(path,manifest,'Unchanged transaction copied the full manifest')
            return original_snapshot(path)
        with patch.object(state,'snapshot',side_effect=snapshot), \
             patch.object(state,'write',side_effect=AssertionError('Unchanged transaction wrote a file')):
            self.assertEqual(self.tx(desired,components={'theme'}),0)
        after=manifest.stat()
        self.assertEqual((after.st_ino,after.st_mtime_ns),(before.st_ino,before.st_mtime_ns))
        self.assertFalse(state.metadata(self.home,'pending.json').exists())
    def test_dry_run_does_not_snapshot_existing_manifest(self):
        self.tx({'config/file':state.value('installed')})
        manifest=state.metadata(self.home,'manifest.json')
        original_snapshot=state.snapshot
        def snapshot(path):
            self.assertNotEqual(path,manifest,'Dry run copied the full manifest')
            return original_snapshot(path)
        with patch.object(state,'snapshot',side_effect=snapshot), \
             patch.object(state,'write',side_effect=AssertionError('Dry run wrote a file')):
            self.assertEqual(state.transact(self.home,{'config/file':state.value('changed')},dry=True),1)
        self.assertEqual((self.home/'config/file').read_text(),'installed')
    def test_matching_unmanaged_file_is_registered_and_restore_removes_metadata(self):
        path=self.home/'existing';path.write_text('matching');path.chmod(0o640)
        original=state.snapshot(path)
        self.assertEqual(self.tx({'existing':original},components={'apps'}),0)
        manifest=state.load(self.home)
        self.assertEqual(manifest['files']['existing'],{'before':original,'installed':original})
        self.assertEqual(manifest['components'],['apps'])
        self.assertEqual(self.tx({'existing':original},restoring=True),0)
        self.assertEqual(state.snapshot(path),original)
        self.assertFalse(state.metadata(self.home,'manifest.json').exists())
    def test_component_only_update_preserves_original_snapshots(self):
        path=self.home/'config';path.write_text('original')
        desired={'config':state.value('installed')}
        self.tx(desired,components={'theme'})
        before=state.load(self.home)['files']
        self.assertEqual(self.tx(desired,components={'apps','theme'}),0)
        manifest=state.load(self.home)
        self.assertEqual(manifest['components'],['apps','theme'])
        self.assertEqual(manifest['files'],before)
    def test_unchanged_transaction_persists_legacy_directory_migration(self):
        desired={'.local/share/atlas/lib/code.py':state.value('code')}
        self.tx(desired,components={'theme'})
        path=state.metadata(self.home,'manifest.json')
        legacy=json.loads(path.read_text());del legacy['directories']
        path.write_text(json.dumps(legacy))
        self.assertEqual(self.tx(desired,components={'theme'}),0)
        self.assertEqual(json.loads(path.read_text())['directories'],
                         ['.local/share/atlas','.local/share/atlas/lib'])
    def test_unchanged_transaction_repairs_manifest_permissions(self):
        desired={'config':state.value('installed')}
        self.tx(desired)
        path=state.metadata(self.home,'manifest.json');before=path.read_bytes()
        path.chmod(0o644)
        self.assertEqual(self.tx(desired),0)
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertEqual(path.read_bytes(),before)
    def test_unchanged_transaction_persists_metadata_normalization(self):
        desired={'.config/atlas/config':state.value('installed')}
        self.tx(desired,components={'theme','apps'})
        path=state.metadata(self.home,'manifest.json')
        original=json.loads(path.read_text())
        unsorted=copy.deepcopy(original)
        unsorted['directories']=list(reversed(original['directories']))+original['directories']
        unsorted['components']=['theme','apps','theme']
        path.write_text(json.dumps(unsorted))
        self.assertEqual(self.tx(desired,components={'theme','apps'}),0)
        self.assertEqual(json.loads(path.read_text()),original)
        del original['components']
        path.write_text(json.dumps(original))
        self.assertEqual(self.tx(desired),0)
        self.assertEqual(json.loads(path.read_text())['components'],[])
    def test_nonregular_manifest_is_rejected_before_reading(self):
        path=self.home/state.STATE/'manifest.json';path.parent.mkdir(parents=True)
        for kind in ('fifo','directory','symlink'):
            with self.subTest(kind=kind):
                if kind=='fifo': os.mkfifo(path)
                elif kind=='directory': path.mkdir()
                else: path.symlink_to(self.home/'other')
                try:
                    with patch.object(Path,'read_text',side_effect=AssertionError('Unsafe manifest was read')):
                        with self.assertRaisesRegex(ValueError,'regular manifest|symlinks'):
                            self.tx({})
                finally:
                    if kind=='directory': path.rmdir()
                    else: path.unlink()
    def test_concurrent_manifest_edit_prevents_unchanged_fast_return(self):
        desired={'config':state.value('installed')}
        self.tx(desired)
        path=state.metadata(self.home,'manifest.json')
        edited=path.read_text()+'\n'
        original_snapshot=state.snapshot
        def snapshot(target):
            result=original_snapshot(target)
            if target==self.home/'config': path.write_text(edited)
            return result
        with patch.object(state,'snapshot',side_effect=snapshot), \
             patch.object(state,'write',side_effect=AssertionError('Concurrent manifest was overwritten')):
            with self.assertRaisesRegex(ValueError,'manifest changed during installation'):
                self.tx(desired)
        self.assertEqual(path.read_text(),edited)
    def test_matching_file_changed_during_adoption_is_preserved(self):
        path=self.home/'existing';path.write_text('matching')
        desired={'existing':state.snapshot(path)}
        pending=state.metadata(self.home,'pending.json')
        original_write=state.write
        def edit_after_journal(target,item):
            original_write(target,item)
            if target==pending: path.write_text('concurrent local edit')
        with patch.object(state,'write',side_effect=edit_after_journal):
            with self.assertRaisesRegex(ValueError,'File changed during installation'):
                self.tx(desired)
        self.assertEqual(path.read_text(),'concurrent local edit')
        self.assertFalse(state.metadata(self.home,'manifest.json').exists())
        self.assertFalse(pending.exists())
    def test_matching_desired_state_does_not_bypass_drift_checks(self):
        path=self.home/'config'
        self.tx({'config':state.value('installed')})
        for drift in ('content','mode','symlink'):
            with self.subTest(drift=drift):
                path.unlink();state.write(path,state.value('installed'))
                if drift=='content': path.write_text('local edit')
                elif drift=='mode': path.chmod(0o600)
                else:
                    path.unlink();path.symlink_to('local-file')
                current=state.snapshot(path)
                with patch.object(state,'write',side_effect=AssertionError('Drift check wrote a file')):
                    with self.assertRaisesRegex(ValueError,'later edit'):
                        self.tx({'config':current})
                self.assertEqual(state.snapshot(path),current)
    def test_metadata_only_failure_rolls_back_original_manifest(self):
        desired={'config':state.value('installed')}
        self.tx(desired,components={'theme'})
        path=state.metadata(self.home,'manifest.json');before=state.snapshot(path)
        original_write=state.write
        failed=False
        def fail_once(target,item):
            nonlocal failed
            if target==path and not failed:
                failed=True;raise OSError('metadata write failure')
            return original_write(target,item)
        with patch.object(state,'write',side_effect=fail_once):
            with self.assertRaisesRegex(OSError,'metadata write failure'):
                self.tx(desired,components={'apps'})
        self.assertEqual(state.snapshot(path),before)
        self.assertFalse(state.metadata(self.home,'pending.json').exists())
    def test_pending_metadata_only_transaction_blocks_noop_and_recovers(self):
        desired={'config':state.value('installed')}
        self.tx(desired,components={'theme'})
        path=state.metadata(self.home,'manifest.json');before=state.snapshot(path)
        pending=state.metadata(self.home,'pending.json')
        state.write(pending,state.value(json.dumps({'changes':{},'manifest_before':before}),0o600))
        updated=state.load(self.home);updated['components'].append('apps')
        state.write(path,state.value(json.dumps(updated),0o600))
        with patch.object(state,'write',side_effect=AssertionError('Pending transaction was ignored')):
            with self.assertRaisesRegex(ValueError,'Interrupted'):
                self.tx(desired,components={'theme','apps'})
        with state.lock(self.home): state.recover(self.home)
        self.assertEqual(state.snapshot(path),before)
        self.assertFalse(pending.exists())
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
    def test_directory_manifest_must_be_derived_from_managed_files(self):
        path=state.metadata(self.home,'manifest.json')
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'version':1,'files':{},'components':[],'directories':['.ssh']}))
        with self.assertRaisesRegex(ValueError,'Unsafe ATLAS installation directory'):
            state.load(self.home)
        path.write_text(json.dumps({'version':1,'files':{'/tmp/victim':{}},'components':[]}))
        with self.assertRaisesRegex(ValueError,'Unsafe relative path'):
            state.load(self.home)
    def test_legacy_manifest_migrates_only_atlas_owned_directories(self):
        path=state.metadata(self.home,'manifest.json')
        path.parent.mkdir(parents=True)
        files={'.local/share/atlas/lib/code.py':{},'.config/yazi/theme.toml':{}}
        path.write_text(json.dumps({'version':1,'files':files,'components':[]}))
        directories=state.load(self.home)['directories']
        self.assertIn('.local/share/atlas',directories)
        self.assertIn('.local/share/atlas/lib',directories)
        self.assertNotIn('.config/yazi',directories)
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
    def test_recovery_preserves_edit_made_after_preflight(self):
        pending={'changes':{
            'a':{'before':state.value('a before'),'after':state.value('a after')},
            'b':{'before':state.value('b before'),'after':state.value('b after')},
        },'manifest_before':{'kind':'absent'}}
        state.write(self.home/'a',state.value('a after'))
        state.write(self.home/'b',state.value('b after'))
        journal=state.metadata(self.home,'pending.json')
        state.write(journal,state.value(json.dumps(pending),0o600))
        original_write=state.write
        def edit_between_recovery_writes(path,item):
            original_write(path,item)
            if path == self.home/'b':
                (self.home/'a').write_text('concurrent local edit')
        with state.lock(self.home), patch.object(state,'write',side_effect=edit_between_recovery_writes):
            with self.assertRaisesRegex(ValueError,'changed during recovery'):
                state.recover(self.home)
        self.assertEqual((self.home/'a').read_text(),'concurrent local edit')
        self.assertEqual((self.home/'b').read_text(),'b before')
        self.assertTrue(journal.exists())


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
        foot_original='font=monospace:size=10\n[colors-dark]\nalpha=0.9\n'
        self.write('.config/foot/foot.ini',foot_original)
        self.write('.local/bin/atlas-vpn', '# prior standalone VPN panel\n')
        self.write('.local/bin/atlas-codex', '# prior Codex launcher\n')
        codex_config = '[tui]\ntheme = "atlas-readable"\n'
        self.write('.codex/config.toml', codex_config)
        desired=self.plan(cli_groups={'all'})
        user.validate(desired);self.apply(desired)
        again=self.plan(cli_groups={'all'})
        self.assertTrue(all(state.snapshot(state.target(self.home,k))==v for k,v in again.items()))
        synced=user.plan(ROOT,self.home,user.COMPONENTS,self.colors,syncing=True)
        self.assertEqual(synced,{k:v for k,v in desired.items() if k in synced})
        with patch.object(state,'write',side_effect=AssertionError('Unchanged bundle wrote a file')):
            self.apply(again)
            self.apply(synced)
        self.assertTrue((self.home/'.local/bin/atlas-info').is_file())
        self.assertTrue(os.access(self.home/'.local/bin/atlas-vpn', os.X_OK))
        self.assertTrue(os.access(self.home/'.local/bin/atlas-agents', os.X_OK))
        self.assertTrue(os.access(self.home/'.local/bin/atlas-codex', os.X_OK))
        self.assertTrue((self.home/'.local/share/atlas/components/apps/atlas_codex/__main__.py').is_file())
        self.assertTrue((self.home/'.local/share/atlas/components/apps/atlas_panel.py').is_file())
        self.assertEqual(json.loads((self.home/'.config/atlas/agents-palette.json').read_text())['accent'], self.colors['accent'])
        self.assertEqual((self.home/'.config/atlas/vpn-palette.json').read_text(),
                         (self.home/'.config/atlas/agents-palette.json').read_text())
        self.assertIn('atlas-vpn', (self.home/'.config/atlas/workspace.conf').read_text())
        self.assertTrue((self.home/'.config/atlas/atlas-prompt.py').is_file())
        self.assertTrue((self.home/'.codex/themes/atlas.tmTheme').is_file())
        self.assertTrue((self.home/'.codex/themes/atlas-readable.tmTheme').is_file())
        self.assertEqual((self.home/'.codex/config.toml').read_text(), codex_config)
        cache=self.home/'.local/lib/atlas-cli/atlas_cli/__pycache__'
        cache.mkdir()
        (cache/'runner.cpython-test.pyc').write_bytes(b'generated')
        records=state.load(self.home)['files']
        with state.lock(self.home): state.transact(self.home,{k:v['before'] for k,v in records.items()},restoring=True)
        self.assertEqual((self.home/'.bashrc').read_text(),'# existing shell preferences\n')
        self.assertEqual((self.home/'.config/foot/foot.ini').read_text(),foot_original)
        self.assertEqual((self.home/'.local/bin/atlas-vpn').read_text(), '# prior standalone VPN panel\n')
        self.assertEqual((self.home/'.local/bin/atlas-codex').read_text(), '# prior Codex launcher\n')
        self.assertEqual((self.home/'.codex/config.toml').read_text(), codex_config)
        self.assertFalse((self.home/'.codex/themes/atlas-readable.tmTheme').exists())
        self.assertFalse((self.home/'.config/omarchy/themes/atlas/colors.toml').exists())
        self.assertFalse((self.home/'.config/omarchy/themes/atlas').exists())
        self.assertFalse((self.home/'.local/share/atlas').exists())
        self.assertFalse((self.home/'.local/lib/atlas-cli').exists())
        self.assertFalse((self.home/'.config/atlas').exists())

    def test_restore_preserves_preexisting_and_nonempty_directories(self):
        preexisting=self.home/'.config/yazi'
        preexisting.mkdir(parents=True)
        desired=self.plan({'theme','apps'})
        self.apply(desired)
        extra=self.home/'.local/share/atlas/recipient-note.txt'
        extra.write_text('keep me')
        manifest=state.load(self.home)
        with state.lock(self.home):
            state.transact(self.home,{k:v['before'] for k,v in manifest['files'].items()},restoring=True)
        self.assertTrue(preexisting.is_dir())
        self.assertEqual(extra.read_text(),'keep me')
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
            'atlas-agents':'usage:',
            'atlas-codex':'usage:',
        }
        for name,output in expected.items():
            with self.subTest(command=name):
                command=self.home/'.local/bin'/name
                self.assertTrue(os.access(command,os.X_OK),name+' is not executable')
                args=[str(command)]+(['--help'] if name in ('atlas-theme','atlas-agents','atlas-codex') else [])
                result=subprocess.run(args,cwd=self.home,env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn(output,result.stdout)
        # Loading the installed VPN command must find its sibling runtime module,
        # without entering curses or contacting the service.
        probe='import runpy,sys; runpy.run_path(sys.argv[1]); import atlas_panel; print(atlas_panel.__file__)'
        result=subprocess.run([sys.executable,'-c',probe,str(self.home/'.local/bin/atlas-vpn')],
                              cwd=self.home,env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),str(self.home/'.local/share/atlas/components/apps/atlas_panel.py'))
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
    def test_foot_main_section_layouts(self):
        layouts=(
            'font=monospace:size=10\n[colors-dark]\nalpha=1.0\n',
            '[main]\nfont=monospace:size=10\n[colors-dark]\nalpha=1.0\n',
            '[colors-dark]\nalpha=1.0\n',
            'font=monospace:size=10\n[colors-dark]\nalpha=1.0\n[main]\npad=4x4\n',
        )
        rel='.config/foot/foot.ini'
        for original in layouts:
            for components in ({'desktop'},{'apps'},user.COMPONENTS):
                with self.subTest(original=original,components=sorted(components)):
                    self.write(rel,original)
                    desired=self.plan(components)
                    installed=state.text_value(desired[rel])
                    ini=configparser.ConfigParser(interpolation=None,strict=False)
                    ini.read_string('[main]\n'+installed)
                    if 'apps' in components:
                        self.assertEqual(shlex.split(ini.get('main','shell')),
                                         [str(self.home/'.local/bin/atlas-session')])
                    else:
                        self.assertFalse(ini.has_option('main','shell'))
                    if components=={'apps'}:
                        self.assertTrue(installed.endswith(original))
                    self.write(rel,installed)
                    self.assertEqual(self.plan(components)[rel],desired[rel])
    def test_foot_custom_shell_in_unnamed_or_reopened_main_is_preserved(self):
        for original in (
            'shell=/bin/zsh -l\n[colors-dark]\nalpha=1.0\n',
            'font=monospace:size=10\n[colors-dark]\nalpha=1.0\n[main]\nshell=/bin/zsh -l\n',
            '[main]\nshell=/bin/bash\n[colors-dark]\nalpha=1.0\n[main]\nshell=/bin/zsh -l\n',
        ):
            with self.subTest(original=original):
                self.write('.config/foot/foot.ini',original)
                desired=self.plan({'desktop'})
                ini=configparser.ConfigParser(interpolation=None,strict=False)
                ini.read_string('[main]\n'+state.text_value(desired['.config/foot/foot.ini']))
                self.assertEqual(ini.get('main','shell'),'/bin/zsh -l')
                for components in ({'apps'},user.COMPONENTS):
                    with self.assertRaisesRegex(ValueError,'custom shell'):
                        self.plan(components)
                self.assertEqual((self.home/'.config/foot/foot.ini').read_text(),original)
    def test_existing_foot_workspace_preserves_other_section_shell_keys(self):
        rel='.config/foot/foot.ini'
        original=('font=monospace:size=10\n[text-bindings]\nshell=Control+Shift+s\n'
                  '[main]\n  shell = '+shlex.quote(str(self.home/'.local/bin/atlas-session'))+'\n')
        self.write(rel,original)
        self.assertEqual(state.text_value(self.plan({'apps'})[rel]),original)
    def test_empty_foot_main_shell_is_replaced(self):
        rel='.config/foot/foot.ini'
        for original in (
            'shell=\n[text-bindings]\nshell=Control+Shift+s\n',
            '[main]\nshell=\n[text-bindings]\nshell=Control+Shift+s\n',
            '[main]\nshell=\n[text-bindings]\nshell=Control+Shift+s\n[main]\n  shell =\n',
        ):
            with self.subTest(original=original):
                self.write(rel,original)
                desired=self.plan({'apps'})
                installed=state.text_value(desired[rel])
                ini=configparser.ConfigParser(interpolation=None,strict=False)
                ini.read_string('[main]\n'+installed)
                self.assertEqual(shlex.split(ini.get('main','shell')),
                                 [str(self.home/'.local/bin/atlas-session')])
                self.assertEqual(ini.get('text-bindings','shell'),'Control+Shift+s')
                self.assertNotIn('shell=\n',installed)
                self.write(rel,installed)
                self.assertEqual(self.plan({'apps'})[rel],desired[rel])
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
    def test_doctor_lists_all_clone_conflicts_before_writing(self):
        names=['custom.lock','custom.polkit','custom.monitor']
        for name in names:
            source='omarchy.'+name.split('.')[1]
            self.write(f'.config/omarchy/plugins/{name}/manifest.json',json.dumps({'id':name,'omarchy':{'clonedFrom':source}}))
        shell={'plugins':names[:2], 'bar':{'layout':{'right':[names[2]]}}}
        self.write('.config/omarchy/shell.json',json.dumps(shell))
        result=subprocess.run([sys.executable,str(ROOT/'install.py'),'doctor','--all','--home',str(self.home),'--offline'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        for name in names:
            self.assertIn('omarchy plugin disable '+name,result.stderr)
        self.assertEqual(json.loads((self.home/'.config/omarchy/shell.json').read_text()),shell)
        self.assertFalse(state.metadata(self.home,'manifest.json').exists())
        shell['disabledPlugins']=names
        merged=user.merge_shell(self.home,copy.deepcopy(shell),ROOT/'components/desktop')
        self.assertTrue(set(names).issubset(merged['disabledPlugins']))
    def test_palette_change_updates_apps_without_replacing_runtime(self):
        before=self.plan({'apps'})
        colors=dict(self.colors,accent='#123456',accent_strip='123456',accent_sgr='18;52;86')
        after=user.plan(ROOT,self.home,{'apps'},colors,syncing=True)
        self.assertNotEqual(before['.config/atlas/tmux.conf'],after['.config/atlas/tmux.conf'])
        self.assertFalse(any(k.startswith('.local/share/atlas') for k in after))
        self.apply(before)
        writes=[]
        original_write=state.write
        def record_write(path,item):
            writes.append(str(path.relative_to(self.home)))
            return original_write(path,item)
        with patch.object(state,'write',side_effect=record_write):
            self.apply(after)
        self.assertEqual(state.snapshot(self.home/'.config/atlas/tmux.conf'),after['.config/atlas/tmux.conf'])
        self.assertFalse(any(rel.startswith('.local/share/atlas') for rel in writes))
        self.assertIn(state.STATE+'/pending.json',writes)
        with patch.object(state,'write',side_effect=AssertionError('Repeated new palette wrote a file')):
            self.apply(after)

if __name__=='__main__': unittest.main()
