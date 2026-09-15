"""The one-command installer safely orchestrates the existing installer."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[1]


class EasyInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atlas-easy-install-')
        self.root=Path(self.temp.name)
        self.bin=self.root/'bin';self.bin.mkdir()
        self.trace=self.root/'trace'
        for command in ('python3','omarchy'):
            path=self.bin/command
            path.write_text('#!/bin/sh\nprintf "%s" "'+command+'" >> "$ATLAS_TEST_TRACE"\nprintf " %s" "$@" >> "$ATLAS_TEST_TRACE"\nprintf "\\n" >> "$ATLAS_TEST_TRACE"\n')
            path.chmod(0o755)
        self.env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],ATLAS_TEST_TRACE=str(self.trace))

    def tearDown(self): self.temp.cleanup()

    def run_installer(self,*args):
        return subprocess.run([str(ROOT/'install.sh'),*args],env=self.env,text=True,capture_output=True)

    def test_default_checks_installs_and_activates(self):
        result=self.run_installer()
        self.assertEqual(result.returncode,0,result.stderr)
        lines=self.trace.read_text().splitlines()
        self.assertEqual(lines[-1],'omarchy theme set atlas')
        self.assertIn(' doctor --all',lines[0])
        self.assertTrue(lines[1].endswith('install.py --all'))

    def test_dry_run_never_activates(self):
        result=self.run_installer('--dry-run')
        self.assertEqual(result.returncode,0,result.stderr)
        lines=self.trace.read_text().splitlines()
        self.assertEqual(len(lines),2)
        self.assertTrue(all(line.startswith('python3 ') for line in lines))
        self.assertTrue(all(line.endswith('--dry-run') for line in lines))

    def test_staged_home_never_activates(self):
        result=self.run_installer('--home',str(self.root/'home'),'--offline')
        self.assertEqual(result.returncode,0,result.stderr)
        lines=self.trace.read_text().splitlines()
        self.assertEqual(len(lines),2)
        self.assertTrue(all(line.startswith('python3 ') for line in lines))

    def test_empty_home_is_rejected_before_python(self):
        result=self.run_installer('--home=')
        self.assertEqual(result.returncode,2)
        self.assertIn('--home requires a path',result.stderr)
        self.assertFalse(self.trace.exists())


if __name__=='__main__': unittest.main()
