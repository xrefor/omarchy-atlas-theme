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
        payload = {'id': identifier, 'parent_thread_id': parent}
        if inherited is not None:
            payload['subagent_history_start_ordinal'] = inherited
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
        path = self.child(inherited=2, metadata={'forked_from_id': 'root'}, events=[
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

    def test_nonforked_child_without_boundary_waits_for_own_turn(self):
        path = self.child(inherited=None, events=[
            event('message', kind='response_item', role='assistant', phase='commentary',
                  content='Copied parent message'),
            event('task_complete', turn_id='parent'),
        ])
        reader = self.reader(path)
        row = reader.poll()
        self.assertEqual(row['status'], 'starting')
        self.assertEqual(row['activity'], 'Waiting for first update')
        self.assertIsNone(row['finished_at'])
        self.append(path, event('task_started', stamp=150, turn_id='own'),
                    event('message', stamp=160, kind='response_item', role='assistant',
                          phase='commentary', content='Child update'))
        row = reader.poll()
        self.assertEqual((row['status'], row['started_at'], row['activity']),
                         ('running', 150, 'Child update'))
        self.append(path, event('task_complete', stamp=170, turn_id='own'))
        self.assertEqual(reader.poll()['status'], 'completed')

    def test_observer_accepts_children_without_boundary_in_both_history_modes(self):
        for mode in ('legacy', 'paginated'):
            self.child(mode, inherited=None,
                       metadata={'cli_version': '0.154.0', 'history_mode': mode},
                       events=[event('task_started', turn_id=mode),
                               event('task_complete', stamp=150, turn_id=mode)])
            with self.connect() as database:
                database.execute('UPDATE threads SET history_mode=? WHERE id=?', (mode, mode))
        snapshot = backend.Observer('root', self.home).poll()
        self.assertTrue(snapshot['connected'], snapshot['error'])
        self.assertEqual(len(snapshot['agents']), 2)
        self.assertTrue(all(row['status'] == 'completed' for row in snapshot['agents']))

    def test_forked_child_without_history_boundary_is_rejected(self):
        path = self.child(inherited=None, metadata={'forked_from_id': 'root'}, events=[
            event('task_started', turn_id='parent')])
        with self.assertRaisesRegex(ValueError, 'inherited-history boundary'):
            self.reader(path)

    def test_invalid_explicit_history_boundary_is_rejected(self):
        for boundary in (-1, '0', 1.5):
            with self.subTest(boundary=boundary):
                path = self.child(str(boundary), inherited=boundary)
                with self.assertRaisesRegex(ValueError, 'inherited-history boundary'):
                    self.reader(path, str(boundary))

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

    def test_owned_task_stays_stable_through_progress_and_completion(self):
        path = self.child(inherited=2, metadata={'forked_from_id': 'root'}, events=[
            event('task_started', turn_id='parent'),
            event('message', kind='response_item', role='user', content='Inherited parent objective'),
            event('task_started', turn_id='own'),
            event('message', kind='response_item', role='user', content=[
                {'type': 'input_text', 'text': 'Unify Nym panel styling. Own the Nym renderer.'}]),
            event('message', kind='response_item', role='assistant', phase='commentary',
                  content='Editing background and footer colors'),
            event('message', kind='response_item', role='assistant', phase='final_answer',
                  content='Implemented Nym consolidation: - Shared colors and many more details'),
            event('task_complete', turn_id='own'),
        ])
        row = self.reader(path).poll()
        self.assertEqual(row['task'], 'Unify Nym panel styling')
        self.assertEqual(row['status'], 'completed')
        self.assertTrue(row['activity'].startswith('Implemented Nym consolidation'))
        self.assertNotIn('Inherited', json.dumps(row))

    def test_new_task_envelope_and_followup_respect_recipient_and_turn(self):
        def assignment(description, recipient='/root/child', **extra):
            return event('agent_message', kind='response_item', author='/root', recipient=recipient,
                         content=[{'type': 'input_text', 'text':
                                   'Message Type: NEW_TASK\nTask name: /root/child\nSender: /root\nPayload:\n' + description}], **extra)
        path = self.child(metadata={'agent_path': '/root/child'}, events=[
            event('task_started', turn_id='one'),
            assignment('Wrong recipient objective', recipient='/root/other'),
            assignment('Review panel sizing.'),
            assignment('Mid-turn message must not replace task'),
            event('task_complete', turn_id='one'),
        ])
        reader = self.reader(path)
        self.assertEqual(reader.poll()['task'], 'Review panel sizing')
        self.append(path, event('task_started', turn_id='two'),
                    assignment('Wrong turn objective', internal_chat_message_metadata_passthrough={'turn_id': 'one'}),
                    assignment('Validate narrow layouts. Preserve others edits.'))
        self.assertEqual(reader.poll()['task'], 'Validate narrow layouts')

    def test_encrypted_assignment_uses_humanized_name_without_envelope(self):
        path = self.child(identifier='nym_panel_styling', metadata={'agent_path': '/root/nym_panel_styling'}, events=[
            event('task_started', turn_id='own'),
            event('agent_message', kind='response_item', author='/root', recipient='/root/nym_panel_styling',
                  content=[{'type': 'input_text', 'text':
                            'Message Type: NEW_TASK\nTask name: /root/nym_panel_styling\nSender: /root\nPayload:\n'},
                           {'type': 'encrypted_content', 'encrypted_content': 'opaque private data'}]),
        ])
        row = self.reader(path, 'nym_panel_styling').poll()
        self.assertEqual(row['task'], 'Nym panel styling')
        self.assertNotIn('Payload', row['task'])
        self.assertNotIn('private', json.dumps(row))

    def test_legacy_user_assignment_and_encrypted_followup_replace_old_task(self):
        path = self.child(metadata={'agent_path': '/root/child'}, events=[
            event('task_started', turn_id='one'),
            event('user_message', message='Review Nym panel spacing.'),
        ])
        reader = self.reader(path)
        self.assertEqual(reader.poll()['task'], 'Review Nym panel spacing')
        self.append(path, event('task_started', turn_id='two'),
                    event('agent_message', kind='response_item', content=[
                        {'type': 'input_text', 'text': 'Message Type: MESSAGE\nPayload:\nProgress question'}]))
        self.assertEqual(reader.poll()['task'], 'Review Nym panel spacing')
        self.append(path, event('agent_message', kind='response_item', recipient='/root/child', content=[
            {'type': 'input_text', 'text': 'Message Type: NEW_TASK\nPayload:\n'},
            {'type': 'encrypted_content', 'encrypted_content': 'unavailable followup'}]))
        self.assertEqual(reader.poll()['task'], 'Child')

    def test_observer_uses_database_agent_path_to_filter_assignments(self):
        def assignment(recipient, text):
            return event('agent_message', kind='response_item', recipient=recipient,
                         content=[{'type': 'input_text', 'text':
                                   f'Message Type: NEW_TASK\nTask name: {recipient}\nPayload:\n{text}'}])
        path = self.child(events=[event('task_started', turn_id='one'),
                                  assignment('/root/other', 'Wrong agent objective')])
        observer = backend.Observer('root', self.home)
        self.assertEqual(observer.poll()['agents'][0]['task'], 'Child')
        self.append(path, assignment('/root/child', 'Review assigned panel'))
        self.assertEqual(observer.poll()['agents'][0]['task'], 'Review assigned panel')

    def test_unknown_agent_path_does_not_accept_arbitrary_task_recipient(self):
        path = self.child(events=[
            event('task_started', turn_id='one'),
            event('agent_message', kind='response_item', recipient='/root/other', content=[
                {'type': 'input_text', 'text': 'Message Type: NEW_TASK\nTask name: /root/other\nPayload:\nWrong agent objective'}]),
        ])
        self.assertEqual(self.reader(path).poll()['task'], 'Child')

    def test_database_agent_path_takes_precedence_over_session_metadata(self):
        path = self.child(metadata={'agent_path': '/root/stale'}, events=[
            event('task_started', turn_id='one'),
            event('agent_message', kind='response_item', recipient='/root/child', content=[
                {'type': 'input_text', 'text': 'Message Type: NEW_TASK\nTask name: /root/child\nPayload:\nReview current task'}]),
        ])
        self.assertEqual(backend.Observer('root', self.home).poll()['agents'][0]['task'], 'Review current task')

    def test_setup_boilerplate_and_command_output_are_not_task_descriptions(self):
        path = self.child(events=[
            event('task_started', turn_id='own'),
            event('message', kind='response_item', role='user', content='# AGENTS.md instructions\nprivate configuration'),
            event('message', kind='response_item', role='user', content='<environment_context>private environment</environment_context>'),
            event('function_call_output', kind='response_item', output='private raw command output'),
            event('message', kind='response_item', role='developer', content='private developer instructions'),
            event('message', kind='response_item', role='user', content='Objective: Check panel resizing. More scope details.'),
        ])
        row = self.reader(path).poll()
        self.assertEqual(row['task'], 'Check panel resizing')
        self.assertNotIn('private', json.dumps(row))

    def test_task_description_is_concise_and_does_not_cut_words(self):
        self.assertEqual(backend.task_description('Please review layout. Then run focused tests.'), 'review layout')
        self.assertEqual(backend.task_description('You are a worker. Private scope details.'), '')
        summary = backend.task_description('Review ' + 'narrow layouts ' * 30)
        self.assertLessEqual(len(summary), 96)
        self.assertTrue(summary.endswith(('narrow…', 'layouts…')))
        self.assertNotIn('encrypted', backend.task_description([
            {'type': 'encrypted_content', 'text': 'encrypted body'}]))

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
