"""Bounded local Git facts and an explicit tracking-ref refresh."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import selectors
import signal
import shlex
import threading
import subprocess
import time


MAX_OUTPUT = 4 * 1024 * 1024
MAX_CHANGED = 200
MAX_COMMITS = 12
MAX_WORKTREES = 50
MAX_VALUE = 4096


class GitError(RuntimeError):
    """A bounded Git query failed."""

    def __init__(self, command, returncode, output):
        self.command = command
        self.returncode = returncode
        self.output = output
        detail = output.strip().splitlines()[-1] if output.strip() else f'exit {returncode}'
        super().__init__(detail[:240])


def _text(value):
    """Bound a value while retaining filenames literally for the UI to sanitize."""
    return str(value)[:MAX_VALUE]


class Collector:
    """Collect locally; contact the configured upstream only through check_remote()."""

    def __init__(self, path, *, git='git', timeout=2.0, max_output=MAX_OUTPUT):
        self.path = os.path.abspath(os.path.expanduser(os.fspath(path)))
        self.git = os.fspath(git)
        self.timeout = max(0.1, min(float(timeout), 10.0))
        self.max_output = max(1024, min(int(max_output), MAX_OUTPUT))
        self._identity = None
        self._remote_check = self._empty_check()
        self._process = None
        self._process_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._cancelled = threading.Event()

    @staticmethod
    def _empty_check(state='never'):
        return dict(state=state, checked_at=None, attempted_at=None, error=None)

    @staticmethod
    def _kill(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()

    def cancel(self):
        """Permanently stop this collector, including active Git helper processes."""
        self._cancelled.set()
        with self._process_lock:
            if self._process is not None:
                self._kill(self._process)


    def _run(self, *arguments, limit=None, timeout=None, environment_updates=None):
        with self._run_lock:
            return self._execute(*arguments, limit=limit, timeout=timeout,
                                 environment_updates=environment_updates)

    def _execute(self, *arguments, limit=None, timeout=None, environment_updates=None):
        """Run Git with a wall-clock deadline and a hard captured-output bound."""
        limit = self.max_output if limit is None else min(int(limit), self.max_output)
        environment = os.environ.copy()
        environment.update({
            'GIT_OPTIONAL_LOCKS': '0',
            'GIT_PAGER': 'cat',
            'GIT_NO_LAZY_FETCH': '1',
            'LC_ALL': 'C',
            'PAGER': 'cat',
            'GIT_TERMINAL_PROMPT': '0',
            'GIT_ASKPASS': '/bin/false',
            'SSH_ASKPASS': '/bin/false',
        })
        environment.update(environment_updates or {})
        command = [self.git, '--no-pager', '-c', 'color.ui=false',
                   '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
                   '-c', 'credential.interactive=false',
                   '-C', self.path, *arguments]
        with self._process_lock:
            if self._cancelled.is_set():
                raise OSError('Collector closed')
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=environment, close_fds=True,
                                       start_new_session=True)
            self._process = process
        output = bytearray()
        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        duration = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + duration
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._kill(process)
                    raise TimeoutError(f'Git query exceeded {duration:g}s')
                events = selector.select(remaining)
                if not events:
                    self._kill(process)
                    raise TimeoutError(f'Git query exceeded {duration:g}s')
                for key, _ in events:
                    chunk = os.read(key.fd, min(65536, limit + 1 - len(output)))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    if len(output) > limit:
                        self._kill(process)
                        raise ValueError(f'Git output exceeded {limit} bytes')
            try:
                returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(f'Git query exceeded {duration:g}s') from error
        finally:
            selector.close()
            # Kill the entire group even if Git exited before a helper did.
            self._kill(process)
            with self._process_lock:
                if self._process is process:
                    self._process = None
            process.stdout.close()
        text = output.decode('utf-8', errors='replace')
        if returncode:
            raise GitError(arguments[0] if arguments else 'git', returncode, text)
        return text

    @staticmethod
    def _status(raw):
        branch = {'name': None, 'detached': False, 'head': None,
                  'upstream': None, 'ahead': None, 'behind': None}
        counts = {'staged': 0, 'unstaged': 0, 'untracked': 0, 'conflicts': 0}
        changes = []
        records = raw.split('\0')
        index = 0
        total = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            if record.startswith('# branch.oid '):
                value = record[13:]
                branch['head'] = None if value == '(initial)' else _text(value)
                continue
            if record.startswith('# branch.head '):
                value = record[14:]
                branch['detached'] = value == '(detached)'
                branch['name'] = None if branch['detached'] else _text(value)
                continue
            if record.startswith('# branch.upstream '):
                branch['upstream'] = _text(record[18:])
                continue
            if record.startswith('# branch.ab '):
                values = record[12:].split()
                try:
                    branch['ahead'] = int(values[0].lstrip('+'))
                    branch['behind'] = abs(int(values[1]))
                except (IndexError, ValueError):
                    pass
                continue
            kind = record[:1]
            path = None
            xy = '..'
            original = None
            if kind == '1':
                fields = record.split(' ', 8)
                if len(fields) == 9:
                    xy, path = fields[1], fields[8]
            elif kind == '2':
                fields = record.split(' ', 9)
                if len(fields) == 10:
                    xy, path = fields[1], fields[9]
                    if index < len(records):
                        original = records[index]
                        index += 1
            elif kind == 'u':
                fields = record.split(' ', 10)
                if len(fields) == 11:
                    xy, path = fields[1], fields[10]
            elif kind == '?':
                xy, path = '??', record[2:]
            if path is None:
                continue
            staged = kind not in ('?', '!') and xy[:1] not in ('.', ' ')
            unstaged = kind not in ('?', '!') and xy[1:2] not in ('.', ' ')
            untracked = kind == '?'
            counts['conflicts'] += int(kind == 'u')
            counts['staged'] += int(staged)
            counts['unstaged'] += int(unstaged)
            counts['untracked'] += int(untracked)
            total += 1
            if len(changes) < MAX_CHANGED:
                item = {'path': _text(path), 'status': xy, 'staged': staged,
                        'unstaged': unstaged, 'untracked': untracked}
                if original:
                    item['original_path'] = _text(original)
                changes.append(item)
        return branch, counts, changes, total

    @staticmethod
    def _commits(raw):
        lines = raw.splitlines()
        result = []
        for offset in range(0, len(lines) - 3, 4):
            full, short, timestamp, subject = lines[offset:offset + 4]
            try:
                timestamp = int(timestamp)
            except ValueError:
                continue
            result.append({'hash': _text(full), 'short_hash': _text(short),
                           'timestamp': timestamp, 'subject': _text(subject)})
            if len(result) >= MAX_COMMITS:
                break
        return result

    @staticmethod
    def _worktrees(raw):
        result = []
        for block in raw.split('\0\0'):
            item = {}
            for field in block.strip('\0').split('\0'):
                key, _, value = field.partition(' ')
                if key == 'worktree':
                    item['path'] = _text(value)
                elif key == 'HEAD':
                    item['head'] = _text(value)
                elif key == 'branch':
                    item['branch'] = _text(value.removeprefix('refs/heads/'))
                elif key in ('bare', 'detached', 'locked', 'prunable'):
                    item[key] = True if not value else _text(value)
            if item.get('path'):
                result.append(item)
            if len(result) >= MAX_WORKTREES:
                break
        return result

    def collect(self):
        snapshot = {
            'path': self.path,
            'is_git': False,
            'repo_root': None,
            'repo_name': Path(self.path).name or self.path,
            'branch': None,
            'detached': False,
            'head': None,
            'upstream': None,
            'ahead': None,
            'behind': None,
            'discovery_state': 'unavailable',
            'status_available': False,
            'history_available': False,
            'divergence_available': False,
            'remote_check': self._empty_check('unavailable'),
            'counts': {'staged': 0, 'unstaged': 0, 'untracked': 0, 'conflicts': 0},
            'changes': [],
            'changes_total': 0,
            'changes_omitted': 0,
            'commits': [],
            'worktrees': [],
            'errors': [],
        }
        if not Path(self.path).is_dir():
            self._identity = None
            self._remote_check = self._empty_check()
            snapshot['errors'].append('Project path is not an accessible directory.')
            return snapshot
        try:
            root = self._run('rev-parse', '--path-format=absolute', '--show-toplevel',
                             limit=64 * 1024).removesuffix('\n')
        except GitError as error:
            # A normal directory outside Git is an empty state, not a fault.
            if error.returncode == 128 and error.output.startswith('fatal: not a git repository'):
                snapshot['discovery_state'] = 'not_repo'
            else:
                snapshot['errors'].append('Git discovery unavailable.')
            self._identity = None
            self._remote_check = self._empty_check()
            return snapshot
        except (OSError, TimeoutError, ValueError) as error:
            self._identity = None
            self._remote_check = self._empty_check()
            snapshot['errors'].append(f'Git discovery unavailable: {error}')
            return snapshot
        if not root:
            return snapshot
        snapshot.update(is_git=True, discovery_state='ok', repo_root=_text(root),
                        repo_name=_text(Path(root).name or root))
        try:
            raw = self._run('status', '--porcelain=v2', '--branch', '-z',
                            '--untracked-files=all')
            branch, counts, changes, total = self._status(raw)
            snapshot.update(status_available=True, branch=branch['name'], detached=branch['detached'],
                            head=branch['head'], upstream=branch['upstream'],
                            ahead=branch['ahead'], behind=branch['behind'],
                            counts=counts, changes=changes, changes_total=total,
                            changes_omitted=max(0, total - len(changes)),
                            divergence_available=branch['ahead'] is not None and branch['behind'] is not None)
            if not branch['head']:
                snapshot['history_available'] = True
        except (OSError, GitError, TimeoutError, ValueError) as error:
            snapshot['errors'].append(f'Working tree unavailable: {error}')
        if snapshot['head']:
            try:
                raw = self._run('log', f'--max-count={MAX_COMMITS}',
                                '--format=%H%n%h%n%ct%n%s')
                snapshot['commits'] = self._commits(raw)
                snapshot['history_available'] = True
            except (OSError, GitError, TimeoutError, ValueError) as error:
                snapshot['errors'].append(f'Commit history unavailable: {error}')
        try:
            snapshot['worktrees'] = self._worktrees(
                self._run('worktree', 'list', '--porcelain', '-z'))
        except (OSError, GitError, TimeoutError, ValueError) as error:
            snapshot['errors'].append(f'Worktrees unavailable: {error}')
        self._sync_identity(snapshot)
        return snapshot

    def _tracking_identity(self, snapshot):
        if not snapshot['status_available']:
            self._tracking_error = 'Working tree status is unavailable.'
            return None
        if snapshot['detached']:
            self._tracking_error = 'Detached HEAD has no branch to check.'
            return None
        if not snapshot['head']:
            self._tracking_error = 'Create the first commit before checking an upstream.'
            return None
        if not snapshot['branch']:
            return None
        ref = 'refs/heads/' + snapshot['branch']
        raw = self._run('for-each-ref',
                        '--format=%(refname)%00%(upstream)%00%(upstream:remotename)%00%(upstream:remoteref)',
                        '--', ref, limit=64 * 1024)
        rows = [row.split('\0') for row in raw.splitlines()]
        fields = next((row for row in rows if len(row) == 4 and row[0] == ref), None)
        if not fields:
            return None
        _, upstream, remote, source = fields
        if remote == '.':
            self._tracking_error = 'Tracking a local branch; no remote to check.'
        # Never fetch a URL or a local branch. Use only configured remote names
        # and remote-tracking destinations to avoid touching a checked-out branch.
        if (not remote or remote == '.' or remote.startswith('-') or
                not upstream.startswith('refs/remotes/') or
                not source.startswith('refs/heads/')):
            return None
        self._run('check-ref-format', upstream)
        self._run('check-ref-format', source)
        remotes = self._run('remote').splitlines()
        if remote not in remotes:
            return None
        # Include remote configuration so changing its URL invalidates freshness.
        remote_config = self._run('config', '--get-all', f'remote.{remote}.url')
        effective_url = self._run('remote', 'get-url', '--', remote)
        config_digest = hashlib.sha256((remote_config + '\0' + effective_url).encode()).hexdigest()
        return snapshot['repo_root'], ref, upstream, remote, source, config_digest

    def _sync_identity(self, snapshot):
        self._tracking_error = 'No supported remote upstream is configured.'
        try:
            identity = self._tracking_identity(snapshot)
        except (OSError, GitError, TimeoutError, ValueError):
            self._tracking_error = 'Upstream configuration is unavailable.'
            identity = None
        if identity != self._identity:
            self._identity = identity
            self._remote_check = self._empty_check()
        if identity is None:
            snapshot['remote_check'] = self._empty_check('unavailable')
            snapshot['remote_check']['error'] = self._tracking_error
        else:
            snapshot['remote_check'] = dict(self._remote_check)

    def _config_optional(self, key):
        try:
            return self._run('config', '--get', key).strip()
        except GitError as error:
            if error.returncode == 1:
                return ''
            raise

    @staticmethod
    def _uses_ssh(url):
        """Recognize Git SSH URLs and scp-style addresses without exposing them."""
        if '://' in url:
            return url.split('://', 1)[0].lower() in ('ssh', 'git+ssh', 'ssh+git')
        if re.match(r'^[A-Za-z0-9][A-Za-z0-9+.-]*::', url):
            return False  # Explicit remote-helper transport.
        host, separator, _ = url.partition(':')
        return bool(separator and host and '/' not in host)

    def _transport_environment(self, remote):
        # get-url expands insteadOf locally; a nominal file/HTTPS URL can resolve
        # to SSH (and vice versa). Inspect only the effective fetch transport.
        url = self._run('remote', 'get-url', '--', remote).strip()
        return self._ssh_environment() if self._uses_ssh(url) else {}

    def _ssh_environment(self):
        variant = os.environ.get('GIT_SSH_VARIANT') or self._config_optional('ssh.variant')
        if variant and variant != 'ssh':
            raise ValueError('Unsupported SSH variant')
        command = (os.environ.get('GIT_SSH_COMMAND') or self._config_optional('core.sshCommand')
                   or (shlex.quote(os.environ['GIT_SSH']) if os.environ.get('GIT_SSH') else 'ssh'))
        # OpenSSH honors the first value. Custom commands must be an executable
        # plus arguments; arbitrary shell pipelines cannot safely receive flags.
        words = shlex.split(command)
        if not words:
            raise ValueError('Empty SSH command')
        if any(word in (';', '&&', '||', '|') for word in words) or '=' in words[0]:
            raise ValueError('Unsupported SSH command')
        words[1:1] = ['-oBatchMode=yes']
        return {'GIT_SSH_COMMAND': shlex.join(words), 'GIT_SSH_VARIANT': 'ssh'}

    def check_remote(self):
        """Explicitly refresh just this branch's tracking ref, never the worktree."""
        snapshot = self.collect()
        identity = self._identity
        if identity is None:
            return snapshot
        _, _, upstream, remote, source, _ = identity
        try:
            ssh_environment = self._transport_environment(remote)
        except (OSError, GitError, TimeoutError, ValueError):
            self._remote_check.update(state='unavailable', error='Remote check unavailable: unsupported SSH configuration.')
            return self.collect()
        self._remote_check.update(state='checking', attempted_at=time.time(), error=None)
        try:
            self._run('-c', 'maintenance.auto=false', '-c', 'gc.auto=0',
                      '-c', 'core.hooksPath=/dev/null',
                      '-c', 'fetch.parallel=1', 'fetch', '--no-tags',
                      '--no-recurse-submodules', '--no-auto-maintenance',
                      '--no-write-fetch-head', '--no-prune', '--no-prune-tags',
                      '--no-write-commit-graph', '--refmap=',
                      '--', remote, f'+{source}:{upstream}', timeout=20.0,
                      environment_updates=ssh_environment)
        except (OSError, GitError, TimeoutError, ValueError):
            self._remote_check.update(state='failed', error='Remote check failed. Check connectivity and remote access.')
        else:
            self._remote_check.update(state='ok', checked_at=time.time(), error=None)
        return self.collect()
