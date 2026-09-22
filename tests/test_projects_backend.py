"""Local-only project fact collection."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from components.apps.atlas_projects.backend import Collector, MAX_CHANGED


class ProjectsBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas projects ')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *arguments, cwd=None):
        return subprocess.run(['git', *arguments], cwd=cwd or self.root, check=True,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def repository(self):
        self.git('init', '-q')
        self.git('config', 'user.name', 'ATLAS Test')
        self.git('config', 'user.email', 'atlas@example')
        (self.root / 'tracked.txt').write_text('one\n')
        self.git('add', 'tracked.txt')
        self.git('commit', '-qm', 'Initial local commit')

    def test_collects_worktree_counts_history_and_root_from_nested_path(self):
        self.repository()
        (self.root / 'nested').mkdir()
        (self.root / 'tracked.txt').write_text('changed\n')
        (self.root / 'staged.txt').write_text('staged\n')
        (self.root / 'untracked.txt').write_text('new\n')
        self.git('add', 'staged.txt')

        value = Collector(self.root / 'nested').collect()

        self.assertTrue(value['is_git'], value['errors'])
        self.assertEqual(value['repo_root'], str(self.root))
        self.assertEqual(value['path'], str(self.root / 'nested'))
        self.assertEqual(value['counts'], {'staged': 1, 'unstaged': 1, 'untracked': 1})
        self.assertEqual(value['commits'][0]['subject'], 'Initial local commit')
        self.assertEqual(value['worktrees'][0]['path'], str(self.root))
        self.assertLessEqual(len(value['changes']), MAX_CHANGED)

    def test_detached_head_and_local_tracking_divergence(self):
        self.repository()
        initial = self.git('rev-parse', 'HEAD').stdout.strip()
        (self.root / 'tracked.txt').write_text('two\n')
        self.git('commit', '-qam', 'Second commit')
        self.git('checkout', '-q', initial)

        value = Collector(self.root).collect()

        self.assertTrue(value['detached'])
        self.assertIsNone(value['branch'])
        self.assertEqual(value['head'], initial)

    def test_status_parser_handles_rename_and_bounds_visible_files(self):
        raw = ('# branch.oid abc\0# branch.head main\0# branch.upstream refs/remotes/up\0'
               '# branch.ab +3 -2\0'
               '2 R. N... 100644 100644 100644 a b R100 new name\0old name\0'
               '? loose file\0')
        branch, counts, changes, total = Collector._status(raw)
        self.assertEqual((branch['ahead'], branch['behind']), (3, 2))
        self.assertEqual(counts, {'staged': 1, 'unstaged': 0, 'untracked': 1})
        self.assertEqual(total, 2)
        self.assertEqual(changes[0]['path'], 'new name')
        self.assertEqual(changes[0]['original_path'], 'old name')

    def test_non_git_and_missing_directories_are_honest_empty_states(self):
        plain = Collector(self.root).collect()
        self.assertFalse(plain['is_git'])
        self.assertEqual(plain['errors'], [])
        missing = Collector(self.root / 'missing').collect()
        self.assertFalse(missing['is_git'])
        self.assertIn('not an accessible directory', missing['errors'][0])

    def test_output_limit_and_timeout_are_strictly_bounded(self):
        self.repository()
        with self.assertRaisesRegex(ValueError, 'output exceeded'):
            Collector(self.root, max_output=1024)._run('show',
                f'--format={"x" * 2048}', 'HEAD')
        sleeper = self.root / 'slow-git'
        sleeper.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(2)\n')
        sleeper.chmod(0o700)
        with self.assertRaisesRegex(TimeoutError, 'exceeded'):
            Collector(self.root, git=sleeper, timeout=.1)._run('status')


if __name__ == '__main__':
    unittest.main()
