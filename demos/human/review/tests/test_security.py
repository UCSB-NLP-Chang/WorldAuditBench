"""Security/integrity contracts; isolated SQLite and local HTTP, never Unreal."""
import base64
import importlib.util
import json
import pathlib
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bug_review_security_server', ROOT / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def manifest():
    return {'tasks': [{'id': 'U011', 'revision': 1,
                       'map': '/Game/Auditor/Tasks/U011/R01/TaskMap',
                       'sha256': 'a' * 64, 'target': 'SECRET_TARGET',
                       'title': 'SECRET_ANSWER', 'taxonomy': {'kind': 'SECRET_KIND'}}]}


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = server.Store(pathlib.Path(self.tmp.name) / 'review.sqlite3', manifest(),
                                  capacity=1, tokens={'token-a': {'id': 'A', 'reviewer': 'Alice'},
                                                      'token-b': {'id': 'B', 'reviewer': 'Bob'}},
                                  admin_token='admin-secret', build_sha='b' * 64)
        self.cookie_a, _ = self.store.login('token-a', 'forged reviewer')
        self.cookie_b, _ = self.store.login('token-b', 'forged reviewer')
        self.a = self.store.auth(self.cookie_a)
        self.b = self.store.auth(self.cookie_b)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def ready(self, user):
        s = self.store.create(user)
        self.store.tick()
        self.store.tick()
        self.assertEqual(self.store.current(user)['status'], 'ready')
        return s['id']

    def row(self, sid):
        return dict(self.store.db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone())

    def image(self, sid, user):
        return self.store.evidence(sid, user, {'mime_type': 'image/png',
            'content_base64': base64.b64encode(b'\x89PNG\r\n\x1a\nsecurity-test').decode()})

    def feedback_data(self):
        return {'verdict': 'uncertain', 'confidence': 2, 'description': '<script>report</script>',
                'location': 'near doorway', 'steps': 'walked normally', 'prior_exposure': False}

    def assert_problem(self, code, fn, *args):
        with self.assertRaises(server.Problem) as caught:
            fn(*args)
        self.assertEqual(caught.exception.status, code)

    def test_identity_is_token_bound_and_mock_login_is_not_existing_identity(self):
        self.assertEqual((self.a['owner'], self.a['reviewer']), ('A', 'Alice'))
        # Once individual credentials exist, the shared demo credential is disabled.
        self.assert_problem(401, self.store.login, 'local-demo', 'Alice')
        self.assert_problem(401, self.store.auth, 'unknown-cookie')

    def test_cross_owner_session_operations_fail_without_mutation(self):
        sid = self.ready(self.a)
        before = self.row(sid)
        for op in ['heartbeat', 'reset', 'close']:
            self.assert_problem(404, self.store.change, sid, self.b, op)
        self.assert_problem(404, self.store.feedback, sid, self.b, self.feedback_data())
        self.assert_problem(404, self.store.evidence, sid, self.b, {})
        self.assertEqual(self.row(sid), before)
        self.assertIsNone(self.store.current(self.b))

    def test_feedback_cannot_attach_other_session_or_owner_evidence(self):
        sid_a = self.ready(self.a)
        eid = self.image(sid_a, self.a)
        self.store.change(sid_a, self.a, 'close')
        self.store.tick()
        sid_b = self.ready(self.b)
        data = self.feedback_data() | {'evidence_ids': [eid]}
        self.assert_problem(400, self.store.feedback, sid_b, self.b, data)
        self.store.change(sid_b, self.b, 'close')
        self.store.tick()
        sid_a2 = self.ready(self.a)
        self.assert_problem(400, self.store.feedback, sid_a2, self.a, data)

    def test_feedback_pins_server_snapshot_not_client_metadata_or_latest(self):
        sid = self.ready(self.a)
        self.store.tasks['U011'].update(revision=2, sha256='c' * 64,
                                      map='/Game/Auditor/Tasks/U011/R02/TaskMap')
        forged = self.feedback_data() | {'owner': 'B', 'reviewer': 'Bob', 'revision': 99,
                  'sha256': 'd' * 64, 'build_sha256': 'e' * 64, 'status': 'accepted',
                  'accepted': True, 'mode': 'external'}
        fid = self.store.feedback(sid, self.a, forged)
        row = self.store.db.execute('SELECT * FROM feedback WHERE id=?', (fid,)).fetchone()
        p = json.loads(row['payload'])
        self.assertEqual(row['owner'], 'A')
        self.assertEqual((p['revision'], p['sha256'], p['build_sha256']), (1, 'a' * 64, 'b' * 64))
        self.assertEqual((p['reviewer'], p['mode'], p['status']), ('Alice', 'mock', 'observation_submitted'))
        self.assertNotIn('accepted', p)

    def test_concurrent_duplicate_feedback_is_single_immutable_submission(self):
        sid = self.ready(self.a)
        data = self.feedback_data()
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: self.store.feedback(sid, self.a, data), range(20)))
        self.assertEqual(len(set(ids)), 1)
        self.store.feedback(sid, self.a, data | {'description': 'overwrite attempt'})
        rows = self.store.db.execute('SELECT payload FROM feedback').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])['description'], data['description'])

    def test_failed_cleanup_keeps_slot_quarantined_and_other_user_queued(self):
        sid = self.ready(self.a)
        second = self.store.create(self.b)['id']
        self.store.change(sid, self.a, 'close')
        original = self.store.call_runner
        def broken(op, session):
            if op == 'stop':
                raise RuntimeError('cleanup failed')
            return original(op, session)
        self.store.call_runner = broken
        for _ in range(3):
            self.store.tick()
        self.assertEqual((self.row(sid)['status'], self.row(sid)['slot']), ('closing', 0))
        self.assertEqual((self.row(second)['status'], self.row(second)['slot']), ('queued', None))
        self.store.call_runner = original
        self.store.tick()
        self.assertEqual((self.row(sid)['status'], self.row(sid)['slot']), ('closed', None))
        self.assertEqual(self.row(second)['slot'], 0)

    def test_negative_cleanup_confirmation_cannot_release_slot(self):
        sid = self.ready(self.a)
        second = self.store.create(self.b)['id']
        self.store.change(sid, self.a, 'close')
        self.store.call_runner = lambda op, row: {'stopped': False, 'ready': False}
        self.store.tick()
        self.assertEqual(self.row(sid)['slot'], 0)
        self.assertEqual((self.row(second)['status'], self.row(second)['slot']), ('queued', None))

    def test_reset_does_not_replace_other_session_or_feedback_snapshot(self):
        sid = self.ready(self.a)
        second = self.store.create(self.b)['id']
        self.store.change(sid, self.a, 'reset')
        self.store.tick()
        self.assertEqual(self.row(sid)['owner'], 'A')
        self.assertEqual(self.row(second)['owner'], 'B')
        self.assertEqual(self.row(sid)['revision'], 1)
        slots = [r[0] for r in self.store.db.execute('SELECT slot FROM sessions WHERE slot IS NOT NULL')]
        self.assertEqual(len(slots), len(set(slots)))

    def test_mock_database_cannot_be_reopened_as_external(self):
        self.ready(self.a)
        with self.assertRaisesRegex(ValueError, 'separate databases'):
            server.Store(self.store.path, manifest(), mode='external', capacity=1,
                         tokens={'private-token': {'id': 'A', 'reviewer': 'Alice'}},
                         runner=['unused-runner'], build_sha='b' * 64)
        self.assertEqual(self.store.current(self.a)['mode'], 'mock')

    def test_closed_session_validates_evidence_and_rejects_legacy_found(self):
        sid = self.ready(self.a)
        self.store.change(sid, self.a, 'close')
        self.store.tick()
        self.assert_problem(400, self.store.evidence, sid, self.a, {})
        self.assert_problem(409, self.store.feedback, sid, self.a,
                            self.feedback_data() | {'verdict': 'found'})
        self.store.feedback(sid, self.a, self.feedback_data() | {'verdict': 'technical_issue'})


class HTTPSecurityTests(SecurityTests):
    # HTTP cases add transport coverage; inherited Store contracts also run in isolation.
    def setUp(self):
        super().setUp()
        self.http = server.make_server(self.store, port=0, origin='https://review.test')
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
        super().tearDown()

    def request(self, method, path, cookie=None, data=None, **headers):
        if cookie:
            headers['Cookie'] = 'review_session=' + cookie
        body = json.dumps(data).encode() if data is not None else None
        if data is not None:
            headers.setdefault('Content-Type', 'application/json')
        conn = HTTPConnection('127.0.0.1', self.http.server_port, timeout=3)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_http_cross_owner_evidence_and_stream_authorization(self):
        sid = self.ready(self.a)
        eid = self.image(sid, self.a)
        self.assertEqual(self.request('GET', '/api/evidence/' + eid, self.cookie_a)[0], 200)
        self.assertEqual(self.request('GET', '/api/evidence/' + eid, self.cookie_b)[0], 404)
        self.assertEqual(self.request('GET', '/api/stream-authorize?session_id=' + sid, self.cookie_b)[0], 404)
        self.assertEqual(self.request('GET', '/api/stream-authorize?session_id=' + sid, self.cookie_a)[0], 403)
        self.assertIsNone(self.store.current(self.a)['stream_url'])

    def test_http_csrf_origin_and_cookie_flags(self):
        status, headers, _ = self.request('POST', '/api/login', data={'token': 'token-a'}, Origin='https://review.test')
        self.assertEqual(status, 200)
        for flag in ['HttpOnly', 'SameSite=Strict', 'Secure']:
            self.assertIn(flag, headers['Set-Cookie'])
        status, _, _ = self.request('POST', '/api/sessions', self.cookie_a, {}, Origin='https://evil.test')
        self.assertEqual(status, 403)
        self.assertIsNone(self.store.current(self.a))
        self.assertEqual(self.request('POST', '/api/sessions', self.cookie_a, {})[0], 403)
        self.assertEqual(self.request('POST', '/api/sessions', self.cookie_a, {}, Origin='null')[0], 403)
        self.assertEqual(self.request('POST', '/api/sessions', self.cookie_a, {}, Origin='https://review.test')[0], 200)

    def test_http_public_task_projection_and_admin_separation(self):
        code, _, body = self.request('GET', '/api/tasks', self.cookie_a)
        self.assertEqual(code, 200)
        self.assertNotIn(b'SECRET', body)
        self.assertEqual(set(json.loads(body)['tasks'][0]), {'id', 'revision', 'sha256', 'environment', 'case_id', 'rubrics', 'case_path', 'case_type'})
        self.assertEqual(self.request('GET', '/api/admin/export', self.cookie_a)[0], 403)
        self.assertEqual(self.request('GET', '/api/admin/export', Authorization='Bearer token-a')[0], 403)
        self.assertEqual(self.request('GET', '/api/admin/export', Authorization='Bearer admin-secret')[0], 200)
        self.assertEqual(self.request('GET', '/api/tasks')[0], 401)

    def test_http_path_escape_logout_and_non_json_post(self):
        self.assertEqual(self.request('GET', '/../../server.py', self.cookie_a)[0], 404)
        self.assertEqual(self.request('POST', '/api/sessions', self.cookie_a, {},
                         Origin='https://review.test', **{'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/logout', self.cookie_a, {}, Origin='https://review.test')[0], 200)
        self.assertEqual(self.request('GET', '/api/me', self.cookie_a)[0], 401)


if __name__ == '__main__':
    unittest.main()
