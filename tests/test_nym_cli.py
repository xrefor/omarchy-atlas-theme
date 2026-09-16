"""Nym CLI downloads are opt-in, version matched and verified before publication."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'lib'))
from atlas import nym_cli, optional

VERSION = '2026.12.2'
STEM = 'nym-vpn-core-v2026.12.2_linux_x86_64'


class NymCliTests(unittest.TestCase):
    def archive(self, symlink=False):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as archive:
            member = tarfile.TarInfo(STEM+'/nym-vpnc')
            binary = b'fake CLI; never executed'
            if symlink:
                member.type = tarfile.SYMTYPE
                member.linkname = '/etc/passwd'
            else:
                member.size = len(binary)
            archive.addfile(member, io.BytesIO(binary))
        return data.getvalue()

    def responses(self, archive, checksum=None):
        digest = checksum or hashlib.sha256(archive).hexdigest()
        metadata = {'tag_name': 'nym-vpn-v'+VERSION, 'draft': False,
                    'assets': [{'name': STEM+'.tar.gz', 'digest': 'sha256:'+digest, 'size': len(archive)}]}
        return [io.BytesIO(json.dumps(metadata).encode()), io.BytesIO(archive)]

    def test_matching_version_and_architecture(self):
        for output in ('nym-vpnd\nBuild Version:      2026.12.2\n', 'nym-vpnd 2026.12.2\n'):
            with patch.object(nym_cli.subprocess, 'check_output', return_value=output), patch.object(nym_cli.platform, 'system', return_value='Linux'), patch.object(nym_cli.platform, 'machine', return_value='x86_64'):
                self.assertEqual(nym_cli.release(), (VERSION, STEM))

    def test_unknown_version_rejected(self):
        with patch.object(nym_cli.subprocess, 'check_output', return_value='unknown build'):
            with self.assertRaisesRegex(ValueError, 'version'):
                nym_cli.release()

    def test_verified_binary_installed_executable(self):
        with tempfile.TemporaryDirectory() as home:
            dest = Path(home)/'.local/bin/nym-vpnc'
            with patch.object(nym_cli, 'fetch', side_effect=self.responses(self.archive())) as fetch:
                nym_cli.install(VERSION, STEM, dest)
            self.assertEqual(dest.read_bytes(), b'fake CLI; never executed')
            self.assertEqual(dest.stat().st_mode & 0o777, 0o755)
            self.assertIn('/nym-vpn-v2026.12.2/', fetch.call_args.args[0])
            self.assertEqual(list(dest.parent.iterdir()), [dest])

    def test_bad_checksum_and_symlink_never_install(self):
        for symlink, checksum in ((False, '0'*64), (True, None)):
            with tempfile.TemporaryDirectory() as home:
                dest = Path(home)/'nym-vpnc'
                with patch.object(nym_cli, 'fetch', side_effect=self.responses(self.archive(symlink), checksum)):
                    with self.assertRaises(ValueError):
                        nym_cli.install(VERSION, STEM, dest)
                self.assertFalse(dest.exists())

    def test_existing_destination_is_preserved_without_network(self):
        with tempfile.TemporaryDirectory() as home:
            dest = Path(home)/'nym-vpnc'
            dest.write_text('existing')
            with patch.object(nym_cli, 'fetch') as fetch:
                with self.assertRaises(ValueError):
                    nym_cli.install(VERSION, STEM, dest)
            self.assertEqual(dest.read_text(), 'existing')
            fetch.assert_not_called()

    def test_missing_digest_rejected_before_download(self):
        metadata = {'tag_name': 'nym-vpn-v'+VERSION, 'draft': False,
                    'assets': [{'name': STEM+'.tar.gz', 'digest': None}]}
        with tempfile.TemporaryDirectory() as home, patch.object(nym_cli, 'fetch', return_value=io.BytesIO(json.dumps(metadata).encode())) as fetch:
            with self.assertRaisesRegex(ValueError, 'digest'):
                nym_cli.install(VERSION, STEM, Path(home)/'nym-vpnc')
            self.assertEqual(fetch.call_count, 1)

    def test_racing_destination_not_replaced(self):
        with tempfile.TemporaryDirectory() as home:
            dest = Path(home)/'nym-vpnc'
            def race(source, destination):
                dest.write_text('another installer')
                raise FileExistsError('existing destination')
            with patch.object(nym_cli, 'fetch', side_effect=self.responses(self.archive())), patch.object(nym_cli.os, 'link', side_effect=race):
                with self.assertRaises(FileExistsError):
                    nym_cli.install(VERSION, STEM, dest)
            self.assertEqual(dest.read_text(), 'another installer')
            self.assertEqual(list(dest.parent.iterdir()), [dest])

    def test_prompt_decline_and_accept(self):
        for answer in ('', 'yes'):
            with patch.object(nym_cli, 'release', return_value=(VERSION, STEM)), patch('builtins.input', return_value=answer), patch.object(nym_cli, 'install') as install:
                nym_cli.offer()
            self.assertEqual(install.call_count, int(answer == 'yes'))

    def test_missing_cli_offered_with_existing_daemon(self):
        with patch.object(optional.sys.stdin, 'isatty', return_value=True), patch.object(optional, 'available', side_effect=lambda command: command != 'nym-vpnc'), patch.object(nym_cli, 'offer') as offer:
            optional.install()
        offer.assert_called_once_with()

    def test_cli_offered_after_new_daemon_install(self):
        installed = False
        def available(command):
            return installed if command == 'nym-vpnd' else command != 'nym-vpnc'
        def install(*args, **kwargs):
            nonlocal installed
            installed = True
        with patch.object(optional.sys.stdin, 'isatty', return_value=True), patch.object(optional, 'available', side_effect=available), patch('builtins.input', return_value='yes'), patch.object(optional.subprocess, 'run', side_effect=install), patch.object(nym_cli, 'offer') as offer:
            optional.install()
        offer.assert_called_once_with()
