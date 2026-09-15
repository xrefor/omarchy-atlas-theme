"""Release construction includes only reviewed, tracked source files."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


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


if __name__=='__main__': unittest.main()
