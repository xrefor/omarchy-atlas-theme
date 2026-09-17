"""Observe local Codex JSONL sessions without loading or resuming a thread.

The local adapter is intentionally small and version-sensitive. Unknown schemas
fail visibly; it never treats database recency or an open spawn edge as liveness.
Only public assistant messages, plans and execution lifecycle labels reach the UI.
"""
import contextlib
import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

MAX_AGENTS = 64
READ_BUDGET = 512 * 1024
MAX_LINE = 1024 * 1024


def codex_home():
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser().resolve()


def timestamp(value, fallback=0):
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return fallback


def short_text(value, limit=240):
    # The UI also strips terminal escapes. Bound data before it enters the cache.
    if not isinstance(value, str):
        return ''
    return ' '.join(value.split())[:limit]


def message_text(content):
    if isinstance(content, str):
        return short_text(content)
    if isinstance(content, list):
        return short_text(' '.join(x.get('text', '') for x in content
                                  if isinstance(x, dict) and isinstance(x.get('text'), str)))
    return ''


def safe_rollout(home, path):
    path = Path(path)
    resolved = path.resolve()
    relative = resolved.relative_to(home.resolve())
    if not relative.parts or relative.parts[0] not in ('sessions', 'archived_sessions'):
        raise ValueError('Codex session file is outside its session directory')
    if path.is_symlink() or resolved.suffix != '.jsonl':
        raise ValueError('Unsupported Codex session file')
    return resolved


def open_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        os.close(fd)
        raise ValueError('Codex session must be a regular file owned by this user')
    return os.fdopen(fd, 'rb')


def session_metadata(path):
    with open_regular(path) as source:
        line = source.readline(MAX_LINE + 1)
    if len(line) > MAX_LINE or not line.endswith(b'\n'):
        raise ValueError('Codex session metadata is unavailable')
    data = json.loads(line)
    if data.get('type') != 'session_meta' or not isinstance(data.get('payload'), dict):
        raise ValueError('Unsupported Codex session metadata')
    return data['payload'], len(line)


def process_start(pid):
    try:
        # The command name may itself contain spaces and parentheses.
        fields = (Path('/proc') / str(int(pid)) / 'stat').read_text().rsplit(') ', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, ValueError, IndexError):
        return None


def process_root(pid, home):
    """Select the CLI's one open root session, never a same-directory guess."""
    candidates = set()
    try:
        descriptors = list((Path('/proc') / str(int(pid)) / 'fd').iterdir())
    except (OSError, ValueError):
        return None
    for fd in descriptors:
        try:
            path = safe_rollout(home, os.readlink(fd))
            meta, _ = session_metadata(path)
            if meta.get('source') == 'cli' and not meta.get('parent_thread_id'):
                candidates.add(meta['id'])
        except (OSError, ValueError, KeyError):
            continue
    if len(candidates) > 1:
        raise ValueError('Multiple open Codex conversations; use atlas-agents attach --thread ID')
    return next(iter(candidates), None)


class Rollout:
    def __init__(self, path, record):
        self.path = path
        meta, self.offset = session_metadata(path)
        if meta.get('id') != record['id']:
            raise ValueError('Codex session identity does not match its metadata')
        self.skip = meta.get('subagent_history_start_ordinal', 0)
        if not isinstance(self.skip, int) or self.skip < 0:
            raise ValueError('Unsupported Codex inherited-history boundary')
        if meta.get('parent_thread_id') and 'subagent_history_start_ordinal' not in meta:
            raise ValueError('Codex child session lacks an inherited-history boundary')
        info = path.stat()
        self.identity = (info.st_dev, info.st_ino)
        self.ordinal = 0
        self.buffer = b''
        self.dropping = False
        self.turn_id = None
        self.record = dict(record, status='starting', activity='Waiting for first update',
                           task='', plan=[], started_at=record['created_at'],
                           updated_at=record['created_at'], finished_at=None)

    def plan(self, value):
        if not isinstance(value, list):
            return
        self.record['plan'] = [{'step': short_text(x.get('step')), 'status': x['status']}
                               for x in value[:30] if isinstance(x, dict)
                               and x.get('status') in ('pending', 'inProgress', 'in_progress', 'completed')]
        for step in self.record['plan']:
            if step['status'] == 'in_progress':
                step['status'] = 'inProgress'

    def feed(self, event):
        payload = event.get('payload', {})
        if not isinstance(payload, dict):
            return
        kind, detail = event.get('type'), payload.get('type')
        stamp = timestamp(event.get('timestamp'), time.time())
        row = self.record
        if kind == 'event_msg' and detail == 'task_started':
            self.turn_id = payload.get('turn_id')
            row.update(status='running', activity='Working', plan=[], finished_at=None,
                       started_at=timestamp(payload.get('started_at'), stamp), updated_at=stamp)
            return
        # Ignore copied conversation history and events for another turn.
        if self.turn_id is None or (payload.get('turn_id') and payload['turn_id'] != self.turn_id):
            return
        if kind == 'event_msg':
            if detail == 'task_complete':
                row.update(status='completed', finished_at=timestamp(payload.get('completed_at'), stamp), updated_at=stamp)
                if row['activity'] in ('Working', 'Running tools', 'Running command'):
                    row['activity'] = 'Completed'
            elif detail in ('turn_aborted', 'task_aborted'):
                row.update(status='interrupted', activity='Interrupted', finished_at=stamp, updated_at=stamp)
            elif detail in ('error', 'task_failed'):
                row.update(status='error', activity='Agent reported an error', finished_at=stamp, updated_at=stamp)
            elif detail in ('plan_update', 'plan_updated'):
                self.plan(payload.get('plan'))
            elif detail == 'item_completed':
                item = payload.get('item', {})
                if not isinstance(item, dict):
                    return
                item_type = item.get('type')
                if item_type == 'AgentMessage' and item.get('phase') in ('commentary', 'final_answer'):
                    text = message_text(item.get('content'))
                    if text: row.update(activity=text, updated_at=stamp)
                elif item_type == 'CommandExecution':
                    row.update(activity='Command failed' if item.get('exit_code') not in (None, 0) else 'Command completed', updated_at=stamp)
                elif item_type in ('Plan', 'PlanUpdate'):
                    self.plan(item.get('plan'))
        elif kind == 'response_item':
            if detail == 'message' and payload.get('role') == 'assistant' and payload.get('phase') in ('commentary', 'final_answer'):
                text = message_text(payload.get('content'))
                if text: row.update(activity=text, updated_at=stamp)
            elif detail in ('function_call', 'custom_tool_call'):
                name = str(payload.get('name', '')).rsplit('.', 1)[-1]
                if name == 'update_plan':
                    try: self.plan(json.loads(payload.get('arguments', '{}')).get('plan'))
                    except (ValueError, TypeError, AttributeError): pass
                elif name in ('request_user_input', 'request_user_input_async'):
                    row.update(status='waiting', activity='Waiting for input', updated_at=stamp)
                else:
                    row.update(activity='Running command' if name in ('exec_command', 'write_stdin') else 'Running tools', updated_at=stamp)
            elif detail in ('function_call_output', 'custom_tool_call_output') and row['status'] == 'waiting':
                row.update(status='running', activity='Working', updated_at=stamp)

    def poll(self):
        with open_regular(self.path) as source:
            info = os.fstat(source.fileno())
            if (info.st_dev, info.st_ino) != self.identity or info.st_size < self.offset:
                raise ValueError('Codex session file changed identity; reconnect the panel')
            source.seek(self.offset)
            data = source.read(READ_BUDGET)
        self.offset += len(data)
        chunks = data.split(b'\n')
        for i, chunk in enumerate(chunks):
            complete = i < len(chunks) - 1
            if len(self.buffer) + len(chunk) > MAX_LINE:
                self.buffer = b''; self.dropping = True
            if not self.dropping:
                self.buffer += chunk
            if not complete:
                continue
            self.ordinal += 1
            if not self.dropping and self.ordinal > self.skip:
                try:
                    event = json.loads(self.buffer)
                    if isinstance(event, dict): self.feed(event)
                except (ValueError, UnicodeError):
                    pass  # Incomplete writes/unsupported records never imply completion.
            self.buffer = b''; self.dropping = False
        result = dict(self.record)
        if self.offset < info.st_size:
            result.update(status='unknown', activity='Loading session activity')
        return result


class Observer:
    def __init__(self, root_id, home=None):
        self.home = Path(home or codex_home()).resolve()
        self.root_id = root_id
        self.readers = {}
        self.last = {'root_id': root_id, 'connected': False, 'error': '', 'updated_at': 0, 'agents': []}

    def database(self):
        files = [p for p in self.home.glob('state_*.sqlite') if re.fullmatch(r'state_\d+\.sqlite', p.name)]
        if not files:
            raise ValueError('Local Codex session metadata is unavailable')
        path = max(files, key=lambda p: int(p.stem.split('_')[1]))
        if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
            raise ValueError('Unsafe Codex metadata file')
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        return connection

    def poll(self):
        try:
            with contextlib.closing(self.database()) as database:
                root = database.execute('SELECT id FROM threads WHERE id=?', (self.root_id,)).fetchone()
                if not root: raise ValueError('The selected Codex conversation is unavailable')
                rows = database.execute('''WITH RECURSIVE descendants(id) AS (
                        SELECT child_thread_id FROM thread_spawn_edges WHERE parent_thread_id=?
                        UNION SELECT edge.child_thread_id FROM thread_spawn_edges edge
                        JOIN descendants parent ON edge.parent_thread_id=parent.id)
                        SELECT t.id,t.rollout_path,t.agent_path,t.agent_nickname,t.agent_role,
                               t.created_at,t.history_mode FROM threads t
                        JOIN descendants d ON t.id=d.id WHERE t.id != ?
                        ORDER BY t.created_at,t.id LIMIT ?''', (self.root_id, self.root_id, MAX_AGENTS + 1)).fetchall()
            if len(rows) > MAX_AGENTS:
                raise ValueError('This conversation exceeds the panel limit of 64 agents')
            agents = []
            for row in rows:
                data = dict(row)
                if data['history_mode'] not in (None, 'jsonl', 'legacy', 'paginated'):
                    raise ValueError('This Codex history format is not supported by the local observer')
                name = short_text((data['agent_path'] or '').rsplit('/', 1)[-1] or data['agent_nickname'] or data['id'][:8], 80)
                record = {'id': data['id'], 'name': name, 'role': short_text(data['agent_role'], 40),
                          'created_at': data['created_at']}
                reader = self.readers.get(data['id'])
                path = safe_rollout(self.home, data['rollout_path'])
                if reader is None or reader.path != path:
                    reader = self.readers[data['id']] = Rollout(path, record)
                agents.append(reader.poll())
            self.last = {'root_id': self.root_id, 'connected': True, 'error': '',
                         'updated_at': time.time(), 'agents': agents}
        except (OSError, ValueError, sqlite3.Error, KeyError) as error:
            # Keep last observations, prominently marked stale/disconnected.
            self.last = dict(self.last, connected=False, error=short_text(str(error)))
        return self.last
