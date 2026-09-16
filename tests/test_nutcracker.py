"""Nutcracker packaging is explicit, pinned, portable, and reversible."""
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
sys.path.insert(0, str(ROOT / 'components/nutcracker'))
from atlas import nutcracker, state
from atlas_nutcracker import backend


class NutcrackerPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)

    def tearDown(self): self.temporary.cleanup()

    def test_exact_upstream_and_direct_dependencies_are_pinned(self):
        self.assertEqual(nutcracker.UPSTREAM_COMMIT, 'c0980227fabd910ce4e4597937a5b88be39527f2')
        requirements = (ROOT / 'components/nutcracker/requirements.txt').read_text().splitlines()
        declarations = [line for line in requirements if line and not line.startswith('#')]
        self.assertTrue(declarations)
        self.assertTrue(all('==' in line and not any(char in line for char in '<>~') for line in declarations))
        text_files = {'.py', '.toml', '.txt', '.tcss'}
        self.assertNotIn(str(Path.home()), '\n'.join(path.read_text() for path in
            (ROOT / 'components/nutcracker').rglob('*')
            if path.is_file() and path.suffix in text_files))

    def test_paths_honor_xdg_environment(self):
        data = self.home / 'xdg-data'; config = self.home / 'xdg-config'
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(data), 'XDG_CONFIG_HOME': str(config)}):
            with patch('pathlib.Path.home', return_value=self.home): paths = nutcracker.Paths()
        self.assertEqual(paths.base, data / 'atlas-nutcracker')
        self.assertEqual(paths.config, config / 'atlas/nutcracker.yaml')

    def test_platform_check_supports_only_packaged_linux_architectures(self):
        with patch.object(nutcracker.platform, 'system', return_value='Linux'), \
             patch.object(nutcracker.platform, 'machine', return_value='amd64'):
            self.assertEqual(nutcracker.architecture(), 'x86_64')
        with patch.object(nutcracker.platform, 'system', return_value='Darwin'):
            with self.assertRaisesRegex(ValueError, 'Linux only'): nutcracker.architecture()

    def test_generated_source_symlink_is_rejected(self):
        paths = nutcracker.Paths(self.home)
        paths.base.mkdir(parents=True)
        paths.source.symlink_to(self.home, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'must not be symlinks'):
            nutcracker._clone_source(paths)

    def test_only_exact_legacy_setuptools_artifacts_are_repeat_safe(self):
        source = self.home / 'source'
        original = source / 'nutcracker_core/module.py'; original.parent.mkdir(parents=True)
        original.write_text('value = 1\n')
        built = source / 'build/lib/nutcracker_core/module.py'; built.parent.mkdir(parents=True)
        built.write_text(original.read_text())
        egg = source / 'nutcracker.egg-info'; egg.mkdir()
        for name in ('PKG-INFO', 'SOURCES.txt', 'dependency_links.txt',
                     'entry_points.txt', 'requires.txt', 'top_level.txt'):
            (egg / name).write_text('generated\n')
        changes = ['?? build/', '?? nutcracker.egg-info/']
        self.assertTrue(nutcracker._known_source_build_artifacts(source, changes))
        (built.parent / 'unexpected.py').write_text('user data\n')
        self.assertFalse(nutcracker._known_source_build_artifacts(source, changes))

    def test_checksum_mismatch_removes_download(self):
        destination = self.home / 'asset'
        with patch.object(nutcracker, 'urlopen', return_value=io.BytesIO(b'tampered')):
            with self.assertRaisesRegex(ValueError, 'Checksum'):
                nutcracker._download({'url': 'https://example.invalid/a', 'sha256': '0' * 64}, destination)
        self.assertFalse(destination.exists())

    def test_archive_traversal_is_rejected(self):
        archive = self.home / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as bundle: bundle.writestr('../escape', 'bad')
        with self.assertRaisesRegex(ValueError, 'Unsafe JADX'):
            nutcracker._extract_zip(archive, self.home / 'output')

    def test_jadx_launchers_receive_explicit_executable_modes(self):
        root = self.home / 'jadx'
        (root / 'bin').mkdir(parents=True)
        for name in ('jadx', 'jadx-gui'):
            path = root / 'bin' / name; path.write_text('#!/bin/sh\n'); path.chmod(0o644)
        nutcracker._restore_jadx_modes(root)
        self.assertEqual((root / 'bin/jadx').stat().st_mode & 0o777, 0o755)
        self.assertEqual((root / 'bin/jadx-gui').stat().st_mode & 0o777, 0o755)

    def test_integration_round_trip_restores_wrappers_and_desktop(self):
        paths = nutcracker.Paths(self.home)
        with state.lock(self.home): nutcracker._integrate(paths)
        self.assertTrue((self.home / '.local/bin/nutcracker').stat().st_mode & 0o111)
        self.assertTrue(paths.application.is_file())
        with state.lock(self.home): nutcracker._integrate(paths, restoring=True)
        self.assertFalse((self.home / '.local/bin/nutcracker').exists())
        self.assertFalse(paths.application.exists())

    def test_setup_is_opt_in_and_process_network_are_mockable(self):
        paths = nutcracker.Paths(self.home)
        with patch.object(nutcracker, 'architecture', return_value='x86_64'), \
             patch.object(nutcracker, '_clone_source') as clone, \
             patch.object(nutcracker, '_install_python') as install, \
             patch.object(nutcracker, '_install_tools') as tools:
            nutcracker.setup(ROOT, self.home, with_tools=False)
        clone.assert_called_once(); install.assert_called_once(); tools.assert_not_called()
        marker = json.loads(paths.marker.read_text())
        self.assertEqual(marker['upstream'], nutcracker.UPSTREAM_COMMIT)
        self.assertIsNone(marker['jre'])

    def test_restore_removes_only_generated_runtime_and_keeps_user_data(self):
        paths = nutcracker.Paths(self.home)
        for path in (paths.source, paths.venv, paths.tools, paths.data / 'reports'):
            path.mkdir(parents=True); (path / 'keep').write_text('data')
        paths.marker.write_text(json.dumps({'version': 1, 'upstream': nutcracker.UPSTREAM_COMMIT}))
        with state.lock(self.home): nutcracker._integrate(paths)
        nutcracker.restore(self.home)
        self.assertFalse(paths.source.exists()); self.assertFalse(paths.venv.exists())
        self.assertFalse(paths.tools.exists()); self.assertTrue((paths.data / 'reports/keep').is_file())

    def test_restore_without_journal_record_preserves_unrelated_launcher(self):
        paths = nutcracker.Paths(self.home)
        paths.base.mkdir(parents=True)
        paths.marker.write_text(json.dumps({'version': 1, 'upstream': nutcracker.UPSTREAM_COMMIT}))
        paths.bin.mkdir(parents=True)
        unrelated = paths.bin / 'nutcracker'; unrelated.write_text('recipient command\n')
        nutcracker.restore(self.home)
        self.assertEqual(unrelated.read_text(), 'recipient command\n')

    def test_existing_frontend_configuration_is_preserved(self):
        data = self.home / 'data'; config_path = self.home / 'config/nutcracker.yaml'
        config_path.parent.mkdir(parents=True); config_path.write_text('custom: true\n')
        with patch.object(backend, 'DATA', data), patch.object(backend, 'CONFIG', config_path):
            backend.setup()
        self.assertEqual(config_path.read_text(), 'custom: true\n')

    def test_frontend_uses_xdg_defaults_and_local_timezone(self):
        source = (ROOT / 'components/nutcracker/atlas_nutcracker/backend.py').read_text()
        self.assertIn('XDG_DATA_HOME', source); self.assertIn('XDG_CONFIG_HOME', source)
        self.assertNotIn('Europe/Oslo', source); self.assertNotIn("Path.home() / 'Work", source)

    def test_apk_validation_and_static_command_do_not_touch_devices(self):
        apk = self.home / 'fixture.apk'
        with zipfile.ZipFile(apk, 'w') as bundle: bundle.writestr('AndroidManifest.xml', b'fixture')
        command = backend.analysis_command(apk)
        self.assertIn('--static-only', command); self.assertNotIn('adb', command)


if __name__ == '__main__': unittest.main()
