"""Bounded, read-only collection of local Git project facts."""
from __future__ import annotations

import os
from pathlib import Path
import selectors
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
    """Collect facts from one path without changing the repository or contacting remotes."""

    def __init__(self, path, *, git='git', timeout=2.0, max_output=MAX_OUTPUT):
        self.path = os.path.abspath(os.path.expanduser(os.fspath(path)))
        self.git = os.fspath(git)
        self.timeout = max(0.1, min(float(timeout), 10.0))
        self.max_output = max(1024, min(int(max_output), MAX_OUTPUT))

    def _run(self, *arguments, limit=None):
        """Run Git with a wall-clock deadline and a hard captured-output bound."""
        limit = self.max_output if limit is None else min(int(limit), self.max_output)
        environment = os.environ.copy()
        environment.update({
            'GIT_OPTIONAL_LOCKS': '0',
            'GIT_PAGER': 'cat',
            'GIT_NO_LAZY_FETCH': '1',
            'LC_ALL': 'C',
            'PAGER': 'cat',
        })
        command = [self.git, '--no-pager', '-c', 'color.ui=false',
                   '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
                   '-C', self.path, *arguments]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=environment, close_fds=True)
        output = bytearray()
        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + self.timeout
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.kill()
                    process.wait()
                    raise TimeoutError(f'Git query exceeded {self.timeout:g}s')
                events = selector.select(remaining)
                if not events:
                    process.kill()
                    process.wait()
                    raise TimeoutError(f'Git query exceeded {self.timeout:g}s')
                for key, _ in events:
                    chunk = os.read(key.fd, min(65536, limit + 1 - len(output)))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    if len(output) > limit:
                        process.kill()
                        process.wait()
                        raise ValueError(f'Git output exceeded {limit} bytes')
            returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
        text = output.decode('utf-8', errors='replace')
        if returncode:
            raise GitError(arguments[0] if arguments else 'git', returncode, text)
        return text

    @staticmethod
    def _status(raw):
        branch = {'name': None, 'detached': False, 'head': None,
                  'upstream': None, 'ahead': 0, 'behind': 0}
        counts = {'staged': 0, 'unstaged': 0, 'untracked': 0}
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
            'ahead': 0,
            'behind': 0,
            'counts': {'staged': 0, 'unstaged': 0, 'untracked': 0},
            'changes': [],
            'changes_total': 0,
            'changes_omitted': 0,
            'commits': [],
            'worktrees': [],
            'errors': [],
        }
        if not Path(self.path).is_dir():
            snapshot['errors'].append('Project path is not an accessible directory.')
            return snapshot
        try:
            root = self._run('rev-parse', '--path-format=absolute', '--show-toplevel',
                             limit=64 * 1024).removesuffix('\n')
        except GitError as error:
            # A normal directory outside Git is an empty state, not a fault.
            if error.returncode != 128:
                snapshot['errors'].append(f'Git discovery unavailable: {error}')
            return snapshot
        except (OSError, TimeoutError, ValueError) as error:
            snapshot['errors'].append(f'Git discovery unavailable: {error}')
            return snapshot
        if not root:
            return snapshot
        snapshot.update(is_git=True, repo_root=_text(root),
                        repo_name=_text(Path(root).name or root))
        try:
            raw = self._run('status', '--porcelain=v2', '--branch', '-z',
                            '--untracked-files=all')
            branch, counts, changes, total = self._status(raw)
            snapshot.update(branch=branch['name'], detached=branch['detached'],
                            head=branch['head'], upstream=branch['upstream'],
                            ahead=branch['ahead'], behind=branch['behind'],
                            counts=counts, changes=changes, changes_total=total,
                            changes_omitted=max(0, total - len(changes)))
        except (OSError, GitError, TimeoutError, ValueError) as error:
            snapshot['errors'].append(f'Working tree unavailable: {error}')
        if snapshot['head']:
            try:
                raw = self._run('log', f'--max-count={MAX_COMMITS}',
                                '--format=%H%n%h%n%ct%n%s')
                snapshot['commits'] = self._commits(raw)
            except (OSError, GitError, TimeoutError, ValueError) as error:
                snapshot['errors'].append(f'Commit history unavailable: {error}')
        try:
            snapshot['worktrees'] = self._worktrees(
                self._run('worktree', 'list', '--porcelain', '-z'))
        except (OSError, GitError, TimeoutError, ValueError) as error:
            snapshot['errors'].append(f'Worktrees unavailable: {error}')
        return snapshot
