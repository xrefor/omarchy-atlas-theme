"""Release construction includes only reviewed, tracked source files."""
import importlib.util
import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('atlas_build',ROOT/'tools/build.py')
build=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(build)


class BuildPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atlas-build-')
        self.root=Path(self.temp.name)
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        (self.root/'docs').mkdir()
        (self.root/'docs/reviewed.md').write_text('reviewed\n')
        subprocess.run(['git','-C',str(self.root),'add','docs/reviewed.md'],check=True)

    def tearDown(self): self.temp.cleanup()

    def test_untracked_file_under_allowed_directory_is_excluded(self):
        (self.root/'docs/.env').write_text('TOKEN=private\n')
        files=build.payload(self.root,files=(),dirs=('docs',))
        self.assertEqual(set(files),{'docs/reviewed.md'})

    def test_tracked_secret_like_file_is_rejected(self):
        path=self.root/'docs/private.pem';path.write_text('private\n')
        subprocess.run(['git','-C',str(self.root),'add',str(path)],check=True)
        with self.assertRaisesRegex(ValueError,'Private/generated'):
            build.payload(self.root,files=(),dirs=('docs',))

    def test_missing_required_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Required release file is not tracked'):
            build.payload(self.root,files=('README.md',),dirs=('docs',))

    def test_tracked_file_replaced_by_symlink_is_rejected(self):
        source=self.root/'docs/reviewed.md'
        source.unlink()
        source.symlink_to(self.root/'outside.md')
        (self.root/'outside.md').write_text('unreviewed\n')
        with self.assertRaisesRegex(ValueError,'Unsafe release entry'):
            build.payload(self.root,files=(),dirs=('docs',))

    def test_tracked_parent_replaced_by_symlink_is_rejected(self):
        (self.root/'docs').rename(self.root/'outside')
        (self.root/'outside/reviewed.md').write_text('unreviewed\n')
        (self.root/'docs').symlink_to(self.root/'outside',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Unsafe release entry'):
            build.payload(self.root,files=(),dirs=('docs',))

    def test_filenames_that_cannot_use_plain_checksum_lines_are_rejected(self):
        for name in ('line\nbreak.md','carriage\rreturn.md','back\\slash.md'):
            with self.subTest(name=name):
                path=self.root/'docs'/name
                path.write_text('reviewed\n')
                subprocess.run(['git','-C',str(self.root),'add',str(path)],check=True)
                try:
                    with self.assertRaisesRegex(ValueError,'Unsafe release filename'):
                        build.payload(self.root,files=(),dirs=('docs',))
                finally:
                    subprocess.run(['git','-C',str(self.root),'rm','-q','--cached',str(path)],check=True)
                    path.unlink()

    def test_archive_is_reproducible_with_normalized_metadata(self):
        source=self.root/'docs/reviewed.md'
        source.chmod(0o755)
        entries=build.payload(self.root,files=(),dirs=('docs',))
        first=self.root/'first.tar.gz';second=self.root/'second.tar.gz'
        build.write_archive(first,'atlas-test',entries)
        os.utime(source,(1,1))
        source.chmod(0o711)
        build.write_archive(second,'atlas-test',entries)
        self.assertEqual(first.read_bytes(),second.read_bytes())
        with tarfile.open(first) as archive:
            self.assertEqual(archive.getnames(),['atlas-test/docs/reviewed.md','atlas-test/SHA256SUMS'])
            for info in archive.getmembers():
                self.assertEqual((info.uid,info.gid,info.uname,info.gname,info.mtime),(0,0,'','',0))
            self.assertEqual(archive.getmember('atlas-test/docs/reviewed.md').mode,0o755)
            self.assertEqual(archive.getmember('atlas-test/SHA256SUMS').mode,0o644)
            data=archive.extractfile('atlas-test/docs/reviewed.md').read()
            checksums=archive.extractfile('atlas-test/SHA256SUMS').read().decode()
            self.assertEqual(checksums,hashlib.sha256(data).hexdigest()+'  docs/reviewed.md\n')

    def test_checksum_uses_same_snapshot_as_archived_content(self):
        source=self.root/'docs/reviewed.md'
        archive_path=self.root/'release.tar.gz'
        with mock.patch.object(Path,'read_bytes',side_effect=[b'first version',b'changed version']):
            build.write_archive(archive_path,'atlas-test',{'docs/reviewed.md':source})
        with tarfile.open(archive_path) as archive:
            data=archive.extractfile('atlas-test/docs/reviewed.md').read()
            checksums=archive.extractfile('atlas-test/SHA256SUMS').read().decode()
            self.assertEqual(data,b'first version')
            self.assertEqual(checksums,hashlib.sha256(data).hexdigest()+'  docs/reviewed.md\n')

    def test_failed_build_preserves_prior_archive_and_removes_partial_file(self):
        output=self.root/'dist';output.mkdir()
        archive=output/'release.tar.gz';archive.write_bytes(b'prior release')
        with self.assertRaises(FileNotFoundError):
            build.write_archive(archive,'atlas-test',{'missing.md':self.root/'missing.md'})
        self.assertEqual(archive.read_bytes(),b'prior release')
        self.assertEqual(list(output.iterdir()),[archive])


if __name__=='__main__': unittest.main()
