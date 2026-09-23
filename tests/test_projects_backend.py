"""Local-only project fact collection."""
from pathlib import Path
import subprocess
import threading
import os
import shlex
import time
import tempfile
import unittest
from unittest.mock import patch

from components.apps.atlas_projects.backend import Collector, GitError, MAX_CHANGED


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
        self.assertEqual(value['counts'], {'staged': 1, 'unstaged': 1, 'untracked': 1, 'conflicts': 0})
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
        self.assertEqual(counts, {'staged': 1, 'unstaged': 0, 'untracked': 1, 'conflicts': 0})
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

    def remote_repository(self):
        self.repository()
        remote = self.root / 'remote.git'
        self.git('init', '--bare', '-q', str(remote))
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '-qu', 'origin', 'HEAD')
        return remote

    def test_explicit_remote_check_updates_only_tracking_ref_and_reports_failure(self):
        remote = self.remote_repository()
        collector = Collector(self.root)
        first = collector.collect()
        self.assertEqual(first['remote_check']['state'], 'never')
        self.assertTrue(first['divergence_available'])
        original_head = first['head']
        clone = self.root / 'other'
        self.git('clone', '-q', str(remote), str(clone))
        self.git('config', 'user.name', 'Other', cwd=clone)
        self.git('config', 'user.email', 'other@example', cwd=clone)
        (clone / 'new').write_text('remote change')
        self.git('add', 'new', cwd=clone)
        self.git('commit', '-qm', 'Other machine', cwd=clone)
        self.git('push', '-q', cwd=clone)
        (self.root / 'tracked.txt').write_text('unfinished local work')
        hook = self.root / '.git' / 'hooks' / 'reference-transaction'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o700)
        self.assertEqual(collector.collect()['behind'], 0)
        checked = collector.check_remote()
        self.assertEqual(checked['remote_check']['state'], 'ok', checked)
        hook.unlink()
        self.assertEqual(checked['behind'], 1)
        self.assertEqual(checked['head'], original_head)
        self.assertEqual((self.root / 'tracked.txt').read_text(), 'unfinished local work')
        self.assertFalse((self.root / '.git' / 'FETCH_HEAD').exists())
        success_time = checked['remote_check']['checked_at']
        remote.rename(self.root / 'offline.git')
        failed = collector.check_remote()
        self.assertEqual(failed['remote_check']['state'], 'failed')
        self.assertEqual(failed['remote_check']['checked_at'], success_time)
        self.assertNotIn(str(remote), failed['remote_check']['error'])
        self.git('checkout', '-qb', 'different')
        self.assertEqual(collector.collect()['remote_check']['state'], 'unavailable')

    def test_fetch_overrides_configured_extra_refs_and_pruning(self):
        self.remote_repository()
        self.git('branch', 'extra')
        self.git('push', '-q', 'origin', 'extra')
        self.git('update-ref', '-d', 'refs/remotes/origin/extra')
        self.git('tag', 'local-only')
        self.git('config', 'fetch.prune', 'true')
        self.git('config', 'fetch.pruneTags', 'true')
        result = Collector(self.root).check_remote()
        self.assertEqual(result['remote_check']['state'], 'ok')
        self.assertEqual(self.git('tag', '--list', 'local-only').stdout.strip(), 'local-only')
        self.assertEqual(self.git('for-each-ref', 'refs/remotes/origin/extra').stdout, '')

    def test_unborn_detached_and_local_upstream_cannot_check_remote(self):
        self.git('init', '-q')
        collector = Collector(self.root)
        unborn = collector.check_remote()
        self.assertTrue(unborn['status_available'])
        self.assertTrue(unborn['history_available'])
        self.assertIsNone(unborn['ahead'])
        self.assertEqual(unborn['remote_check']['state'], 'unavailable')
        self.repository()
        self.git('branch', 'base')
        self.git('branch', '--set-upstream-to=base')
        local = collector.check_remote()
        self.assertEqual(local['remote_check']['state'], 'unavailable')
        self.assertTrue(local['divergence_available'])
        self.git('checkout', '-q', '--detach')
        self.assertEqual(collector.check_remote()['remote_check']['state'], 'unavailable')

    def test_failed_queries_are_not_clean_or_empty_history(self):
        self.repository()
        collector = Collector(self.root)
        original = collector._run
        for failing, flag in [('status', 'status_available'), ('log', 'history_available')]:
            def run(*args, **kwargs):
                if args[0] == failing:
                    raise GitError(failing, 128, 'broken repository')
                return original(*args, **kwargs)
            with patch.object(collector, '_run', side_effect=run):
                result = collector.collect()
            self.assertFalse(result[flag])
            self.assertTrue(result['errors'])
        with patch.object(collector, '_run', side_effect=GitError('rev-parse', 128, 'fatal: detected dubious ownership')):
            result = collector.collect()
        self.assertEqual(result['discovery_state'], 'unavailable')
        self.assertTrue(result['errors'])

    def test_deleted_upstream_is_failed_not_success_and_missing_ref_is_unknown(self):
        remote = self.remote_repository()
        collector = Collector(self.root)
        upstream = self.git('rev-parse', '--symbolic-full-name', '@{upstream}').stdout.strip()
        self.git('update-ref', '-d', upstream)
        result = collector.collect()
        self.assertFalse(result['divergence_available'])
        self.assertIsNone(result['ahead'])
        self.assertEqual(collector.check_remote()['remote_check']['state'], 'ok')
        branch = self.git('symbolic-ref', 'HEAD').stdout.strip()
        self.git('update-ref', '-d', branch, cwd=remote)
        self.assertEqual(collector.check_remote()['remote_check']['state'], 'failed')

    def test_custom_ssh_identity_is_preserved_with_batch_mode_first(self):
        self.remote_repository()
        self.git('config', 'core.sshCommand', 'ssh -i "/tmp/test identity" -oBatchMode=no')
        with patch.dict(os.environ, {}, clear=True):
            environment = Collector(self.root)._ssh_environment()
        self.assertEqual(shlex.split(environment['GIT_SSH_COMMAND']),
                         ['ssh', '-oBatchMode=yes', '-i', '/tmp/test identity', '-oBatchMode=no'])
        with patch.dict(os.environ, {'GIT_SSH_COMMAND': 'ssh -i /tmp/override'}, clear=True):
            environment = Collector(self.root)._ssh_environment()
        self.assertIn('/tmp/override', environment['GIT_SSH_COMMAND'])
        self.git('config', 'ssh.variant', 'plink')
        with self.assertRaisesRegex(ValueError, 'Unsupported SSH variant'):
            Collector(self.root)._ssh_environment()
        self.assertEqual(Collector(self.root).check_remote()['remote_check']['state'], 'ok')
        self.git('remote', 'set-url', 'origin', 'ssh://example.invalid/repo')
        # Unsupported SSH is rejected before any network operation.
        self.assertEqual(Collector(self.root).check_remote()['remote_check']['state'], 'unavailable')

    def test_transport_detection_honors_rewrites_without_network(self):
        remote = self.remote_repository()
        collector = Collector(self.root)
        self.git('config', 'ssh.variant', 'plink')
        self.git('config', 'core.sshCommand', 'env CUSTOM=value ssh')
        self.git('config', f'url.{remote}.insteadOf', 'https://example.invalid/project')
        self.git('remote', 'set-url', 'origin', 'https://example.invalid/project')
        self.assertEqual(collector.check_remote()['remote_check']['state'], 'ok')
        for url in ('ssh://host/repo', 'git+ssh://host/repo', 'user@host:repo', '[::1]:repo'):
            self.assertTrue(collector._uses_ssh(url), url)
        for url in ('https://host/repo', 'file:///tmp/repo', '/tmp/repo:name', './repo:name', 'ext::command'):
            self.assertFalse(collector._uses_ssh(url), url)

    def test_changed_effective_remote_invalidates_freshness(self):
        remote = self.remote_repository()
        self.git('config', f'url.{remote}.insteadOf', 'https://example.invalid/project')
        self.git('remote', 'set-url', 'origin', 'https://example.invalid/project')
        collector = Collector(self.root)
        checked = collector.check_remote()
        self.assertEqual(checked['remote_check']['state'], 'ok')
        self.assertIsNotNone(checked['remote_check']['checked_at'])
        self.git('config', '--unset', f'url.{remote}.insteadOf')
        self.git('config', f'url.{self.root / "different.git"}.insteadOf', 'https://example.invalid/project')
        changed = collector.collect()
        self.assertEqual(changed['remote_check']['state'], 'never')
        self.assertIsNone(changed['remote_check']['checked_at'])
        self.assertIsNone(changed['remote_check']['attempted_at'])

    def test_fetch_error_never_exposes_credentials(self):
        self.remote_repository()
        collector = Collector(self.root)
        original = collector._run
        def run(*args, **kwargs):
            if 'fetch' in args:
                raise GitError('fetch', 128, 'fatal: https://user:SECRET_TOKEN@example failed')
            return original(*args, **kwargs)
        with patch.object(collector, '_run', side_effect=run):
            result = collector.check_remote()
        self.assertEqual(result['remote_check']['state'], 'failed')
        self.assertNotIn('SECRET_TOKEN', str(result))

    def test_cancel_kills_git_and_helper_process_group(self):
        helper = self.root / 'helper-git'
        marker = self.root / 'late-marker'
        ready = self.root / 'ready'
        helper.write_text(
            '#!/usr/bin/env python3\nimport subprocess, time\nfrom pathlib import Path\n'
            + f'subprocess.Popen(["python3", "-c", {("import time; from pathlib import Path; time.sleep(0.5); Path(" + repr(str(marker)) + ").touch()")!r}])\n'
            + f'Path({str(ready)!r}).touch()\ntime.sleep(5)\n')
        helper.chmod(0o700)
        collector = Collector(self.root, git=helper)
        errors = []
        def run():
            try:
                collector._run('status')
            except (GitError, OSError):
                errors.append(True)
        worker = threading.Thread(target=run)
        worker.start()
        deadline = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(ready.exists())
        collector.cancel()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        time.sleep(.6)
        self.assertFalse(marker.exists(), 'Helper survived collector cancellation')
        self.assertTrue(errors)

    def test_conflicts_are_explicit(self):
        raw = 'u UU N... 100644 100644 100644 100644 a b c conflict.txt\0'
        _, counts, _, _ = Collector._status(raw)
        self.assertEqual(counts['conflicts'], 1)


if __name__ == '__main__':
    unittest.main()
