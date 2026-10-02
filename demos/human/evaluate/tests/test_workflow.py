import base64
import json
import pathlib
import subprocess
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zlib
from unittest.mock import patch

from bf.common import Problem, canonical, digest, uid
from bf.contracts import validate_envelope
from bf.delivery import deliver_pending
from bf.evaluation import EvaluationStore
from bf.exploration import ExplorationStore
from bf.http import make_server
from bf.images import validate_png
from bf.runtime import Runtime


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\0\xff\0\0\0\xff\0' * 2)) + chunk(b'IEND', b'')


class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.ex = ExplorationStore(self.root / 'exploration')
        self.ev = EvaluationStore(self.root / 'evaluation')
        self.task = {'id': uid(), 'title': 'Explore', 'query': 'Find unexpected behavior.', 'controls': 'WASD, F', 'rubric': 'SECRET_SENTINEL'}
        self.ex.register_task(self.task)
        self.ev.register_reference({'id': self.task['id'], 'query': self.task['query'], 'rubric': 'SECRET_SENTINEL'})
        self.ex.add_user('explorer', 'test-explorer-password')
        self.ex.add_user('other', 'test-other-password')
        self.ev.add_user('judge', 'test-judge-password')
        self.ev.add_user('judge2', 'test-judge2-password')
        self.user = self.ex.authenticate(self.ex.login('explorer', 'test-explorer-password'))
        self.other = self.ex.authenticate(self.ex.login('other', 'test-other-password'))
        self.judge = self.ev.authenticate(self.ev.login('judge', 'test-judge-password'))
        self.judge2 = self.ev.authenticate(self.ev.login('judge2', 'test-judge2-password'))
        for name in ('explorer', 'other'): self.ex.grant_task(name, self.task['id'], 'explorer')
        for name in ('judge', 'judge2'): self.ev.grant_task(name, self.task['id'], 'reviewer')
        self.a = self.ex.start_attempt(self.user, self.task['id'])
        self.rid = uid()
        self.ex.record_runtime(self.a['id'], self.user, self.rid)
        self.flag = {'id': uid(), 'runtime_id': self.rid, 'captured_at': time.time(), 'content_base64': base64.b64encode(png()).decode()}
        self.ex.add_flag(self.user, self.a['id'], self.flag)

    def tearDown(self):
        self.ex.db.close()
        self.ev.db.close()
        self.tmp.cleanup()

    def submit(self):
        snapshot = self.ex.save_draft(self.user, self.a['id'], {'version': 0, 'draft': {'outcome': 'reports', 'reports': [{'id': uid(), 'description': 'An object is unsupported.', 'evidence_ids': [self.flag['id']]}]}})
        result = self.ex.submit(self.user, self.a['id'], {'version': snapshot['draft_version']})
        payload = json.loads(self.ex.delivery_batch()[0]['payload'])
        return result, payload

    def import_answer(self):
        result, payload = self.submit()
        self.ev.import_submission(payload, lambda sid, fid: self.ex.evidence(fid, submission_id=sid))
        return result, payload

    def test_public_projection_has_no_ground_truth(self):
        self.assertNotIn('SECRET_SENTINEL', canonical(self.ex.snapshot(self.user)))
        self.assertNotIn('rubric', self.ex.task(self.task['id']))
        self.assertNotIn(b'SECRET_SENTINEL', (self.root / 'exploration' / 'exploration.sqlite3-wal').read_bytes())

    def test_delete_flag_unlinks_and_blocks_retry(self):
        saved = self.ex.save_draft(self.user, self.a['id'], {'version': 0, 'draft': {'outcome': 'reports', 'reports': [{'id': uid(), 'description': 'Keep this text', 'category': 'V4', 'evidence_ids': [self.flag['id']]}]}})
        request = {'id': self.flag['id'], 'version': saved['draft_version']}
        result = self.ex.delete_flag(self.user, self.a['id'], request)
        self.assertEqual(result['flags'], [])
        self.assertEqual(result['draft']['reports'][0]['evidence_ids'], [])
        self.assertEqual(result['draft']['reports'][0]['description'], 'Keep this text')
        self.assertEqual(self.ex.delete_flag(self.user, self.a['id'], request)['draft_version'], result['draft_version'])
        with self.assertRaises(Problem):
            self.ex.add_flag(self.user, self.a['id'], self.flag)
        with self.assertRaises(Problem):
            self.ex.evidence(self.flag['id'], user=self.user)
        with self.assertRaises(Problem):
            self.ex.submit(self.user, self.a['id'], {'version': result['draft_version']})

    def test_delete_flag_ownership_version_and_finality(self):
        with self.assertRaises(Problem):
            self.ex.delete_flag(self.other, self.a['id'], {'id': self.flag['id'], 'version': 0})
        with self.assertRaises(Problem):
            self.ex.delete_flag(self.user, self.a['id'], {'id': self.flag['id'], 'version': 99})
        result, payload = self.submit()
        with self.assertRaises(Problem):
            self.ex.delete_flag(self.user, self.a['id'], {'id': self.flag['id'], 'version': 1})
        self.assertEqual(self.ex.evidence(self.flag['id'], submission_id=payload['id']), png())

    def test_cancel_pending_flag_prevents_late_upload(self):
        result = self.ex.delete_flag(self.user, self.a['id'], {'id': uid(), 'version': 0})
        fid = self.ex.db.execute('SELECT id FROM deleted_flags').fetchone()[0]
        with self.assertRaises(Problem):
            self.ex.add_flag(self.user, self.a['id'], {**self.flag, 'id': fid})
        self.assertEqual(len(result['flags']), 1)

    def test_category_roundtrip_and_validation(self):
        report = {'id': uid(), 'description': 'Material mismatch', 'category': 'V4', 'evidence_ids': [self.flag['id']]}
        saved = self.ex.save_draft(self.user, self.a['id'], {'version': 0, 'draft': {'outcome': 'reports', 'reports': [report]}})
        with self.assertRaises(Problem):
            self.ex.save_draft(self.user, self.a['id'], {'version': 1, 'draft': {'outcome': 'reports', 'reports': [{**report, 'category': 'invalid'}]}})
        self.ex.submit(self.user, self.a['id'], {'version': saved['draft_version']})
        payload = json.loads(self.ex.delivery_batch()[0]['payload'])
        validate_envelope(payload)
        self.ev.import_submission(payload, lambda sid, fid: self.ex.evidence(fid, submission_id=sid))
        self.assertEqual(self.ev.claim(self.judge, payload['id'])['submission']['reports'][0]['category'], 'V4')

    def test_prompt_category_roundtrip(self):
        report = {'id': uid(), 'description': 'Observed inconsistent behavior', 'category': 'state', 'evidence_ids': [self.flag['id']]}
        saved = self.ex.save_draft(self.user, self.a['id'], {'version': 0, 'draft': {'outcome': 'reports', 'reports': [report]}})
        self.ex.submit(self.user, self.a['id'], {'version': saved['draft_version']})
        payload = json.loads(self.ex.delivery_batch()[0]['payload'])
        self.ev.import_submission(payload, lambda sid, fid: self.ex.evidence(fid, submission_id=sid))
        self.assertEqual(self.ev.claim(self.judge, payload['id'])['submission']['reports'][0]['category'], 'state')

    def test_bilingual_instructions_cover_public_taxonomy(self):
        from bf.instructions import INSTRUCTIONS, markdown
        from bf.taxonomy import TAXONOMY
        for lang in ('zh', 'en'):
            text = markdown(lang)
            self.assertEqual(len(INSTRUCTIONS[lang]['sections']), 5)
            self.assertIn(INSTRUCTIONS[lang]['template'], text)
            for group in TAXONOMY['categories']:
                self.assertTrue(group['description'][lang])
                self.assertIn(group['name'][lang] + ': ' + group['description'][lang], text)
            self.assertNotIn('SECRET_SENTINEL', text)
        from bf.taxonomy import taxonomy_text
        expected = pathlib.Path(__file__).with_name('prompt-taxonomy.txt').read_text().rstrip('\n')
        self.assertEqual(taxonomy_text('en'), expected)
        self.assertIn(expected, markdown('en'))
        self.assertEqual(len(TAXONOMY['categories']), 5)

    def test_unassigned_user_cannot_enter_or_read_task(self):
        self.ex.add_user('unassigned', 'password')
        user = self.ex.authenticate(self.ex.login('unassigned', 'password'))
        with self.assertRaises(Problem): self.ex.start_attempt(user, self.task['id'])
        with self.assertRaises(Problem): self.ex.snapshot(user, self.a['id'])
        with self.assertRaises(Problem): self.ex.evidence(self.flag['id'], user=user)
        self.assertEqual(self.ex.accessible_tasks(user, 'explorer'), [])

    def test_case_roles_cannot_cross_between_task_versions(self):
        new_id = uid()
        self.ex.catalog(new_id, 'New version', self.task['id'])
        with self.assertRaises(Problem): self.ex.grant_task('explorer', new_id, 'reviewer')
        self.ex.grant_task('explorer', new_id, 'explorer')

    def test_multiple_case_drafts_do_not_return_wrong_case(self):
        second = {**self.task, 'id': uid()}
        self.ex.register_task(second)
        self.ex.grant_task('explorer', second['id'], 'explorer')
        draft = self.ex.start_attempt(self.user, second['id'])
        self.assertNotEqual(draft['id'], self.a['id'])
        self.assertEqual(self.ex.snapshot(self.user, task_id=self.task['id'])['id'], self.a['id'])
        self.assertEqual(self.ex.start_attempt(self.user, second['id'])['id'], draft['id'])

    def test_progress_counts_cases_not_attempts_and_denies_admin_scope(self):
        from bf.progress import progress
        self.submit()
        next_attempt = self.ex.start_attempt(self.user, self.task['id'])
        own = progress(self.ex, 'exploration', self.user)
        self.assertEqual(own['summary']['total'], 1)
        self.assertEqual(own['summary']['completed'], 1)
        self.assertEqual(own['rows'][0]['attempt_count'], 2)
        self.assertEqual(own['rows'][0]['attempt_id'], next_attempt['id'])
        self.assertNotIn('rubric', json.dumps(own))
        with self.assertRaises(Problem): progress(self.ex, 'exploration', self.user, 'all')
        with self.assertRaises(Problem): progress(self.ex, 'exploration', self.user, cohort=1)
        admin = {**self.user, 'is_admin': 1}
        all_rows = progress(self.ex, 'exploration', admin, 'all')
        self.assertEqual(all_rows['summary']['total'], 2)
        self.assertEqual(len(all_rows['people']), 2)

    def test_reviewer_access_and_self_review_are_enforced(self):
        result, payload = self.import_answer()
        self.ev.add_user('outsider', 'password')
        outsider = self.ev.authenticate(self.ev.login('outsider', 'password'))
        self.assertEqual(self.ev.queue(outsider), [])
        with self.assertRaises(Problem): self.ev.claim(outsider, result['id'])
        with self.assertRaises(Problem): self.ev.evidence(outsider, payload['evidence'][0]['id'])
        self.ev.add_user('explorer', 'password')
        self.ev.grant_task('explorer', self.task['id'], 'reviewer')
        same = self.ev.authenticate(self.ev.login('explorer', 'password'))
        self.assertEqual(self.ev.queue(same), [])
        with self.assertRaises(Problem): self.ev.claim(same, result['id'])

    def test_evaluation_progress_uses_latest_judgment_and_lease_state(self):
        from bf.progress import progress
        result, payload = self.import_answer()
        self.assertEqual(progress(self.ev, 'evaluation', self.judge)['summary']['states'], {'pending': 1})
        self.assertEqual(progress(self.ev, 'evaluation', self.judge, 'mine')['summary']['total'], 0)
        self.ev.claim(self.judge, result['id'])
        self.assertEqual(progress(self.ev, 'evaluation', self.judge)['summary']['states'], {'in_progress': 1})
        answer = {'report_id': payload['reports'][0]['id'], 'verdict': 'correct', 'reference_item': 'primary', 'reason': 'supported'}
        self.ev.save_judgment(self.judge, result['id'], {'revision': 0, 'answers': [answer]})
        answer.update(verdict='insufficient', reference_item='', reason='need more evidence')
        self.ev.save_judgment(self.judge, result['id'], {'revision': 1, 'answers': [answer]})
        result = progress(self.ev, 'evaluation', self.judge, 'mine')
        self.assertEqual(result['summary']['completed'], 1)
        self.assertEqual(result['distribution']['bugs'], {'insufficient': 1})
        self.assertNotIn('need more evidence', json.dumps(result))
        self.assertNotIn('SECRET_SENTINEL', json.dumps(result))

    def test_case_access_checked_again_after_claim(self):
        result, payload = self.import_answer()
        self.ev.claim(self.judge, result['id'])
        with self.ev.transaction() as db: db.execute('DELETE FROM task_access WHERE user_id=?', (self.judge['id'],))
        with self.assertRaises(Problem): self.ev.detail(self.judge, result['id'])
        with self.assertRaises(Problem): self.ev.evidence(self.judge, payload['evidence'][0]['id'])

    def test_test_cohort_metadata_preserves_immutable_payload(self):
        from bf.progress import progress
        result, payload = self.import_answer()
        before = self.ev.db.execute('SELECT payload FROM submissions').fetchone()[0]
        with self.ev.transaction() as db: db.execute('UPDATE submission_authors SET is_test=1')
        self.assertEqual(progress(self.ev, 'evaluation', self.judge)['summary']['total'], 0)
        qa = {**self.judge, 'is_test': 1}
        self.assertEqual(progress(self.ev, 'evaluation', qa)['summary']['total'], 1)
        self.assertEqual(self.ev.db.execute('SELECT payload FROM submissions').fetchone()[0], before)

    def test_assignment_retries_return_same_active_attempt(self):
        self.assertEqual(self.a['id'], self.ex.start_attempt(self.user, self.task['id'])['id'])

    def test_flag_retry_is_idempotent(self):
        self.ex.add_flag(self.user, self.a['id'], self.flag)
        self.assertEqual(len(self.ex.snapshot(self.user)['flags']), 1)

    def test_evidence_cannot_cross_users_or_attempts(self):
        with self.assertRaises(Problem):
            self.ex.evidence(self.flag['id'], user=self.other)
        other = self.ex.start_attempt(self.other, self.task['id'])
        with self.assertRaises(Problem):
            self.ex.save_draft(self.other, other['id'], {'version': 0, 'draft': {'outcome': 'reports', 'reports': [{'id': uid(), 'description': '', 'evidence_ids': [self.flag['id']]}]}})

    def test_png_corruption_rejected(self):
        with self.assertRaises(Problem):
            validate_png(png()[:-1])
        with self.assertRaises(Problem):
            validate_png(b'\x89PNG\r\n\x1a\n' + b'bad')

    def test_draft_conflict_preserves_latest(self):
        self.ex.save_draft(self.user, self.a['id'], {'version': 0, 'draft': {'outcome': 'none', 'reports': []}})
        with self.assertRaises(Problem):
            self.ex.save_draft(self.user, self.a['id'], {'version': 0, 'draft': {'outcome': 'reports', 'reports': []}})
        self.assertEqual(self.ex.snapshot(self.user)['draft']['outcome'], 'none')

    def test_final_submit_retry_and_immutability(self):
        result, _ = self.submit()
        self.assertEqual(result, self.ex.submit(self.user, self.a['id'], {'version': 1}))
        with self.assertRaises(Problem):
            self.ex.save_draft(self.user, self.a['id'], {'version': 1, 'draft': {'outcome': 'none', 'reports': []}})
        self.assertEqual(len(self.ex.delivery_batch()), 1)

    def test_invalid_submission_is_atomic(self):
        with self.assertRaises(Problem):
            self.ex.submit(self.user, self.a['id'], {'version': 0})
        self.assertEqual(self.ex.snapshot(self.user)['status'], 'draft')
        self.assertFalse(self.ex.delivery_batch())

    def test_import_retry_copies_evidence_and_deduplicates(self):
        result, payload = self.import_answer()
        self.ev.import_submission(payload, lambda *_: self.fail('Already imported'))
        self.assertEqual(len(self.ev.queue(self.judge)), 1)
        (self.ex.evidence_dir / self.flag['id']).unlink()
        self.ev.claim(self.judge, result['id'])
        self.assertEqual(self.ev.evidence(self.judge, self.flag['id']), png())

    def test_failed_import_never_enters_queue_then_recovers(self):
        result, payload = self.submit()
        with self.assertRaises(Problem):
            self.ev.import_submission(payload, lambda *_: b'broken')
        self.assertFalse(self.ev.queue(self.judge))
        self.ev.import_submission(payload, lambda *_: png())
        self.assertEqual(len(self.ev.queue(self.judge)), 1)

    def test_import_conflict_rejected(self):
        _, payload = self.import_answer()
        payload['reports'][0]['description'] = 'Different content'
        with self.assertRaises(Problem):
            self.ev.import_submission(payload, lambda *_: png())

    def test_outage_keeps_outbox_and_recovers(self):
        result, payload = self.submit()
        c = {'evaluation_internal': 'http://127.0.0.1:1', 'transfer_secret': 'test'}
        deliver_pending(self.ex, c)
        with self.ex.transaction() as db:
            row = db.execute('SELECT * FROM outbox').fetchone()
            self.assertIsNone(row['delivered'])
            self.assertEqual(row['attempts'], 1)
            db.execute('UPDATE outbox SET next_try=0')
        with patch('bf.delivery.request_json', return_value={'id': result['id'], 'status': 'complete'}):
            deliver_pending(self.ex, c)
        self.assertFalse(self.ex.delivery_batch())

    def test_lease_excludes_other_judge_and_expired_owner(self):
        result, _ = self.import_answer()
        self.ev.claim(self.judge, result['id'])
        with self.assertRaises(Problem):
            self.ev.claim(self.judge2, result['id'])
        with self.ev.transaction() as db:
            db.execute('UPDATE review_assignments SET lease_until=0')
        self.ev.claim(self.judge2, result['id'])
        with self.assertRaises(Problem):
            self.ev.detail(self.judge, result['id'])

    def test_category_judgment_is_separate_and_preserves_submission(self):
        result, payload = self.import_answer()
        self.ev.claim(self.judge, result['id'])
        answer = {'report_id': payload['reports'][0]['id'], 'verdict': 'correct', 'reference_item': 'primary', 'reason': 'Bug supported, category should be geometry.', 'category_verdict': 'incorrect', 'corrected_category': 'geometry'}
        saved = self.ev.save_judgment(self.judge, result['id'], {'revision': 0, 'answers': [answer]})
        self.assertEqual(saved['judgment']['answers'][0]['verdict'], 'correct')
        self.assertEqual(saved['judgment']['answers'][0]['corrected_category'], 'geometry')
        self.assertEqual(saved['submission'], payload)
        answer.update(category_verdict='correct', corrected_category='')
        saved = self.ev.save_judgment(self.judge, result['id'], {'revision': 1, 'answers': [answer]})
        self.assertEqual(len(saved['history']), 2)
        self.assertEqual(saved['judgment']['answers'][0]['category_verdict'], 'correct')

    def test_category_judgment_rejects_invalid_corrections(self):
        result, payload = self.import_answer()
        self.ev.claim(self.judge, result['id'])
        answer = {'report_id': payload['reports'][0]['id'], 'verdict': 'insufficient', 'reason': 'Need additional evidence.'}
        for status, correction in [('incorrect', ''), ('incorrect', 'V4'), ('incorrect', 'invalid'), ('correct', 'geometry'), ('invalid', '')]:
            with self.assertRaises(Problem):
                self.ev.save_judgment(self.judge, result['id'], {'revision': 0, 'answers': [{**answer, 'category_verdict': status, 'corrected_category': correction}]})
        self.assertEqual(self.ev.detail(self.judge, result['id'])['revision'], 0)

    def test_judgment_history_and_revision_conflict(self):
        result, payload = self.import_answer()
        self.ev.claim(self.judge, result['id'])
        data = {'revision': 0, 'answers': [{'report_id': payload['reports'][0]['id'], 'verdict': 'correct', 'reason': 'Screenshot supports the description.', 'reference_item': 'primary'}]}
        saved = self.ev.save_judgment(self.judge, result['id'], data)
        self.assertEqual(saved['revision'], 1)
        with self.assertRaises(Problem):
            self.ev.save_judgment(self.judge, result['id'], data)
        data['revision'] = 1
        saved = self.ev.save_judgment(self.judge, result['id'], data)
        self.assertEqual(len(saved['history']), 2)

    def test_technical_issue_not_delivered(self):
        self.ex.save_draft(self.user, self.a['id'], {'version': 0, 'draft': {'outcome': 'technical', 'technical_note': 'No video', 'reports': []}})
        self.ex.submit(self.user, self.a['id'], {'version': 1})
        self.assertFalse(self.ex.delivery_batch())
        self.assertEqual(self.ex.snapshot(self.user)['status'], 'technical')

    def test_none_submission_can_be_evaluated(self):
        self.ex.save_draft(self.user, self.a['id'], {'version': 0, 'draft': {'outcome': 'none', 'reports': []}})
        result = self.ex.submit(self.user, self.a['id'], {'version': 1})
        payload = json.loads(self.ex.delivery_batch()[0]['payload'])
        self.ev.import_submission(payload, lambda *_: self.fail('No evidence expected'))
        self.ev.claim(self.judge, result['id'])
        self.ev.save_judgment(self.judge, result['id'], {'revision': 0, 'answers': [{'report_id': 'none', 'verdict': 'missed', 'reason': 'Known defect is present.'}]})

    def test_reference_versions_cannot_be_rewritten(self):
        with self.assertRaises(Problem):
            self.ev.register_reference({'id': self.task['id'], 'query': self.task['query'], 'rubric': 'Changed'})

    def test_qa_answers_are_in_a_separate_cohort(self):
        self.user['is_test'] = 1
        result, _ = self.import_answer()
        self.assertFalse(self.ev.queue(self.judge))
        with self.assertRaises(Problem):
            self.ev.claim(self.judge, result['id'])
        self.judge['is_test'] = 1
        self.assertEqual(len(self.ev.queue(self.judge)), 1)
        self.ev.claim(self.judge, result['id'])

    def test_supervisor_module_entry_starts_and_stops(self):
        manifest = self.root / 'manifest.json'
        manifest.write_text('{"tasks":[]}')
        config = self.root / 'runtime.json'
        config.write_text(json.dumps({'capacity': 1, 'streamer_port': 19111, 'player_port': 19112, 'sfu_port': 19113, 'supervisor_port': 0, 'manifest': str(manifest), 'state_dir': str(self.root / 'runtime')}))
        process = subprocess.Popen([sys.executable, '-m', 'bf.runtime_supervisor', str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            import select
            readable, _, _ = select.select([process.stdout], [], [], 5)
            self.assertTrue(readable)
            self.assertIn('supervisor ready', process.stdout.readline())
        finally:
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stderr)

    def test_legacy_busy_prevents_launch(self):
        runtime = Runtime(self.ex, {'legacy_player_ports': [1], 'gpu_guard': False})
        with patch('bf.runtime.listening', return_value=True), patch.object(runtime, 'call') as call:
            with self.assertRaises(Problem):
                runtime.start(self.user, self.a['id'])
            call.assert_not_called()

    def test_runtime_yields_to_legacy_without_touching_legacy(self):
        runtime = Runtime(self.ex, {'legacy_player_ports': [1]})
        runtime.current = {'id': uid(), 'attempt_id': self.a['id'], 'owner': self.user['id'], 'status': 'ready'}
        with patch('bf.runtime.listening', return_value=True), patch.object(runtime, 'call', return_value={'stopped': True}) as call:
            runtime.tick()
            self.assertIsNone(runtime.current)
            self.assertEqual(call.call_args.args[0], 'stop')

    def test_stream_disconnect_grace_and_reconnect(self):
        runtime = Runtime(self.ex, {'legacy_player_ports': []})
        sid = uid()
        runtime.current = {'id': sid, 'attempt_id': self.a['id'], 'owner': self.user['id'],
                           'status': 'ready', 'created': 100, 'heartbeat': 100}
        with patch('bf.runtime.time.time', return_value=100), patch.object(runtime, 'call', return_value={'ready': True, 'stopped': True}) as call:
            runtime.stream_connected(sid)
            runtime.stream_connected(sid)
            runtime.stream_disconnected(sid)
            self.assertNotIn('disconnect_deadline', runtime.current)
            runtime.stream_disconnected(sid)
            self.assertEqual(runtime.current['disconnect_deadline'], 110)
            runtime.stream_connected(sid)
            self.assertNotIn('disconnect_deadline', runtime.current)
            runtime.stream_disconnected('stale-session')
            self.assertEqual(runtime.current['connections'], 1)
            runtime.tick()
            self.assertIsNotNone(runtime.current)
            runtime.stream_disconnected(sid)
            with patch('bf.runtime.time.time', return_value=111):
                # Polling heartbeat must not keep a disconnected game alive.
                runtime.current['heartbeat'] = 111
                runtime.tick()
            self.assertIsNone(runtime.current)
            self.assertEqual(call.call_args.args[0], 'stop')

    def test_http_role_and_origin_boundaries(self):
        config = {'port': 0, 'origin': 'http://explore.test', 'task_id': self.task['id'], 'transfer_secret': 'internal-test-secret'}
        server = make_server('exploration', self.ex, config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            users = json.load(urllib.request.urlopen(base + '/api/login-users'))
            self.assertEqual(set(users), {'users'})
            self.assertEqual(users['users'], [r['name'] for r in self.ex.db.execute('SELECT name FROM users ORDER BY name COLLATE NOCASE')])
            self.assertTrue(all(isinstance(name, str) for name in users['users']))
            token = self.ex.login('explorer', 'test-explorer-password')
            for route in ('/api/queue', '/api/tasks', '/static/evaluation/app.js'):
                req = urllib.request.Request(base + route, headers={'Cookie': 'bf_explore_session=' + token})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req)
                self.assertEqual(caught.exception.code, 404)
            req = urllib.request.Request(base + '/api/attempts', data=b'{}', headers={'Content-Type': 'application/json', 'Origin': 'http://evil.test', 'Cookie': 'bf_explore_session=' + token})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code, 403)
            req = urllib.request.Request(base + '/api/workspace', headers={'Cookie': 'bf_explore_session=' + token})
            self.assertNotIn(b'SECRET_SENTINEL', urllib.request.urlopen(req).read())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
