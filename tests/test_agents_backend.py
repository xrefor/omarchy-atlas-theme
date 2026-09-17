"""Read-only agent observation against temporary Codex metadata and rollouts."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agents_backend', ROOT / 'components/apps/atlas_agents/backend.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


def event(detail, stamp=110, kind='event_msg', **payload):
    return {'type': kind, 'timestamp': stamp, 'payload': dict(type=detail, **payload)}


def encoded(value):
    return json.dumps(value).encode() + b'\n'


class AgentsBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / 'custom codex home #1?'
        (self.home / 'sessions').mkdir(parents=True)
        self.database = self.home / 'state_5.sqlite'
        with self.connect() as database:
            database.executescript('''
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY, rollout_path TEXT, agent_path TEXT,
                    agent_nickname TEXT, agent_role TEXT, created_at INTEGER,
                    history_mode TEXT);
                CREATE TABLE thread_spawn_edges (
                    parent_thread_id TEXT, child_thread_id TEXT, status TEXT);
                INSERT INTO threads VALUES ('root', '', '', '', '', 100, 'jsonl');
            ''')

    def connect(self):
        database = sqlite3.connect(self.database)
        self.addCleanup(database.close)
        return database

    def child(self, identifier='child', parent='root', events=(), inherited=0, metadata=None):
        path = self.home / 'sessions' / f'{identifier}.jsonl'
        payload = {'id': identifier, 'parent_thread_id': parent,
                   'subagent_history_start_ordinal': inherited}
        if metadata:
            payload.update(metadata)
        path.write_bytes(encoded({'type': 'session_meta', 'payload': payload}) +
                         b''.join(encoded(item) for item in events))
        with self.connect() as database:
            database.execute('INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?)',
                             (identifier, str(path), f'/{parent}/{identifier}',
                              'nickname', 'worker', 100, 'jsonl'))
            database.execute('INSERT INTO thread_spawn_edges VALUES (?, ?, ?)',
                             (parent, identifier, 'open'))
        return path

    def append(self, path, *events):
        with path.open('ab') as source:
            source.write(b''.join(encoded(item) for item in events))

    def reader(self, path, identifier='child'):
        return backend.Rollout(path, {'id': identifier, 'name': identifier,
                                      'role': 'worker', 'created_at': 100})

    def test_recursive_descendants_exclude_unrelated_threads_and_root(self):
        self.child('child')
        self.child('grandchild', 'child')
        self.child('unrelated', 'other-root')
        snapshot = backend.Observer('root', self.home).poll()
        self.assertTrue(snapshot['connected'], snapshot['error'])
        self.assertEqual({row['id'] for row in snapshot['agents']}, {'child', 'grandchild'})

    def test_open_spawn_edge_does_not_establish_liveness(self):
        self.child()
        snapshot = backend.Observer('root', self.home).poll()
        self.assertEqual(snapshot['agents'][0]['status'], 'starting')
        self.assertIsNone(snapshot['agents'][0]['finished_at'])

    def test_metadata_boundary_counts_records_after_metadata(self):
        path = self.child(inherited=2, events=[
            event('task_started', turn_id='inherited'),
            event('task_complete', turn_id='inherited'),
            event('message', kind='response_item', role='assistant', phase='commentary',
                  content='Unowned message before our turn'),
            event('task_started', stamp=150, turn_id='own'),
            event('message', stamp=160, kind='response_item', role='assistant',
                  phase='commentary', content='Checking child work'),
        ])
        row = self.reader(path).poll()
        self.assertEqual(row['status'], 'running')
        self.assertEqual(row['started_at'], 150)
        self.assertEqual(row['activity'], 'Checking child work')
        self.assertIsNone(row['finished_at'])

    def test_child_without_history_boundary_is_rejected(self):
        path = self.child()
        path.write_bytes(encoded({'type': 'session_meta',
                                 'payload': {'id': 'child', 'parent_thread_id': 'root'}}))
        with self.assertRaisesRegex(ValueError, 'inherited-history boundary'):
            self.reader(path)

    def test_completion_resume_interruption_and_error_lifecycle(self):
        path = self.child(events=[event('task_started', turn_id='one')])
        reader = self.reader(path)
        self.assertEqual(reader.poll()['status'], 'running')
        self.append(path, event('task_complete', 130, turn_id='one', completed_at=128))
        completed = reader.poll()
        self.assertEqual((completed['status'], completed['finished_at']), ('completed', 128))
        self.assertEqual(reader.poll(), completed)
        self.append(path, event('task_started', 200, turn_id='two', started_at=199),
                    event('task_complete', 210, turn_id='one'))
        resumed = reader.poll()
        self.assertEqual((resumed['status'], resumed['started_at']), ('running', 199))
        self.assertIsNone(resumed['finished_at'])
        self.append(path, event('turn_aborted', 220, turn_id='two'))
        self.assertEqual(reader.poll()['status'], 'interrupted')
        self.append(path, event('task_started', 230, turn_id='three'),
                    event('error', 240, turn_id='three', message='private error body'))
        failed = reader.poll()
        self.assertEqual((failed['status'], failed['finished_at']), ('error', 240))
        self.assertNotIn('private error body', json.dumps(failed))

    def test_partial_record_waits_for_newline_and_never_implies_completion(self):
        path = self.child(events=[event('task_started', turn_id='one')])
        reader = self.reader(path)
        self.assertEqual(reader.poll()['status'], 'running')
        completed = encoded(event('task_complete', 130, turn_id='one'))
        with path.open('ab') as source:
            source.write(completed[:-1])
        self.assertEqual(reader.poll()['status'], 'running')
        self.assertEqual(reader.poll()['status'], 'running')
        with path.open('ab') as source:
            source.write(b'\n')
        self.assertEqual(reader.poll()['status'], 'completed')

    def test_oversized_and_malformed_records_are_dropped_without_losing_next_event(self):
        path = self.child(events=[event('task_started', turn_id='one')])
        reader = self.reader(path)
        reader.poll()
        with path.open('ab') as source:
            source.write(b'not json\n')
            source.write(encoded(event('task_complete', turn_id='one', oversized='x' * 1000)))
        with patch.object(backend, 'MAX_LINE', 256), patch.object(backend, 'READ_BUDGET', 128):
            for _ in range(20):
                row = reader.poll()
            self.assertEqual(row['status'], 'running')
            self.assertEqual(reader.buffer, b'')
            self.append(path, event('task_complete', 200, turn_id='one'))
            self.assertEqual(reader.poll()['status'], 'completed')

    def test_backlog_is_unknown_until_observed_records_catch_up(self):
        path = self.child(events=[event('task_started', turn_id='one'),
                                  event('task_complete', 200, turn_id='one')])
        reader = self.reader(path)
        with patch.object(backend, 'READ_BUDGET', 30):
            first = reader.poll()
            self.assertEqual(first['status'], 'unknown')
            self.assertIn('Loading', first['activity'])
            for _ in range(20):
                row = reader.poll()
        self.assertEqual(row['status'], 'completed')

    def test_only_public_agent_messages_and_tool_labels_are_displayed(self):
        path = self.child(events=[event('task_started', turn_id='one')])
        reader = self.reader(path)
        reader.poll()
        self.append(path,
                    event('reasoning', kind='response_item', text='hidden reasoning'),
                    event('message', kind='response_item', role='assistant', phase='analysis',
                          content='private analysis'),
                    event('message', kind='response_item', role='user', phase='commentary',
                          content='private user content'),
                    event('item_completed', item={'type': 'Reasoning', 'text': 'private thought'}),
                    event('function_call_output', kind='response_item', output='private output'),
                    event('item_completed', item={'type': 'CommandExecution', 'exit_code': 0,
                                                  'aggregated_output': 'private command output'}))
        row = reader.poll()
        self.assertEqual(row['activity'], 'Command completed')
        self.assertNotIn('private', json.dumps(row))
        self.assertNotIn('hidden', json.dumps(row))
        self.append(path, event('message', 180, kind='response_item', role='assistant',
                                phase='commentary', content=[{'type': 'output_text', 'text': 'Public update'}]))
        self.assertEqual(reader.poll()['activity'], 'Public update')
        self.append(path, event('item_completed', 190, item={
            'type': 'AgentMessage', 'phase': 'final_answer', 'content': 'Public result'}))
        self.assertEqual(reader.poll()['activity'], 'Public result')

    def test_waiting_for_input_resumes_without_exposing_input(self):
        path = self.child(events=[event('task_started', turn_id='one'),
                                  event('function_call', kind='response_item',
                                        name='functions.request_user_input', arguments='private question')])
        reader = self.reader(path)
        self.assertEqual(reader.poll()['status'], 'waiting')
        self.append(path, event('function_call_output', kind='response_item', output='private answer'))
        row = reader.poll()
        self.assertEqual(row['status'], 'running')
        self.assertNotIn('private', json.dumps(row))

    def test_explicit_plans_are_preserved_without_estimated_progress(self):
        path = self.child(events=[event('task_started', turn_id='one'),
                                  event('function_call', kind='response_item', name='functions.update_plan',
                                        arguments=json.dumps({'plan': [
                                            {'step': 'Inspect', 'status': 'completed'},
                                            {'step': 'Validate', 'status': 'in_progress'}]}))])
        row = self.reader(path).poll()
        self.assertEqual(row['plan'], [{'step': 'Inspect', 'status': 'completed'},
                                       {'step': 'Validate', 'status': 'inProgress'}])
        self.assertNotIn('progress', row)
        self.assertNotIn('percentage', row)

    def test_database_error_keeps_last_snapshot_marked_disconnected(self):
        self.child(events=[event('task_started', turn_id='one')])
        observer = backend.Observer('root', self.home)
        previous = observer.poll()
        with patch.object(observer, 'database', side_effect=sqlite3.OperationalError('database unavailable')):
            stale = observer.poll()
        self.assertFalse(stale['connected'])
        self.assertEqual(stale['agents'], previous['agents'])
        self.assertEqual(stale['updated_at'], previous['updated_at'])
        self.assertIn('database unavailable', stale['error'])

    def test_database_connection_rejects_writes(self):
        observer = backend.Observer('root', self.home)
        database = observer.database()
        self.addCleanup(database.close)
        with self.assertRaises(sqlite3.OperationalError):
            database.execute('DELETE FROM threads')
        self.assertEqual(database.execute('SELECT count(*) FROM threads').fetchone()[0], 1)

    def test_outside_path_and_direct_symlink_are_rejected(self):
        path = self.child()
        outside = Path(self.temporary.name) / 'outside.jsonl'
        outside.write_bytes(path.read_bytes())
        with self.assertRaises(ValueError):
            backend.safe_rollout(self.home, outside)
        link = self.home / 'sessions' / 'linked.jsonl'
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            backend.safe_rollout(self.home, link)
        with self.assertRaises(OSError):
            backend.open_regular(link)

    def test_metadata_and_replaced_file_identity_are_rejected(self):
        path = self.child(metadata={'id': 'someone-else'})
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.reader(path)
        path.write_bytes(encoded({'type': 'session_meta', 'payload': {'id': 'child'}}))
        reader = self.reader(path)
        replacement = path.with_suffix('.new')
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
        with self.assertRaisesRegex(ValueError, 'identity'):
            reader.poll()

    def test_custom_codex_home_with_spaces_and_uri_characters(self):
        self.child(events=[event('task_started', turn_id='one')])
        with patch.dict(os.environ, {'CODEX_HOME': str(self.home)}):
            observer = backend.Observer('root')
            self.assertEqual(backend.codex_home(), self.home)
            snapshot = observer.poll()
        self.assertTrue(snapshot['connected'], snapshot['error'])
        self.assertEqual(snapshot['agents'][0]['status'], 'running')


if __name__ == '__main__':
    unittest.main()
