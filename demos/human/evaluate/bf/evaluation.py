"""Independent materialized answers and human judgments. No exploration DB access."""
import json
import time
from .common import Database, canonical, digest, require
from .contracts import identifier, validate_envelope
from .images import validate_png
from .judgment_options import reason_options

SCHEMA = '''
CREATE TABLE IF NOT EXISTS self_review_permissions(user_id TEXT PRIMARY KEY REFERENCES users(id), granted_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reference_versions(id TEXT PRIMARY KEY, reference TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, status TEXT NOT NULL, error TEXT);
CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY, payload TEXT NOT NULL, task_version_id TEXT NOT NULL REFERENCES reference_versions(id), created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES submissions(id), sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_assignments(submission_id TEXT PRIMARY KEY REFERENCES submissions(id), owner TEXT REFERENCES users(id), lease_until REAL NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS submission_authors(submission_id TEXT PRIMARY KEY REFERENCES submissions(id), name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS judgments(submission_id TEXT PRIMARY KEY REFERENCES submissions(id), payload TEXT NOT NULL, revision INTEGER NOT NULL, owner TEXT NOT NULL REFERENCES users(id), updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS judgment_history(id INTEGER PRIMARY KEY, submission_id TEXT NOT NULL, payload TEXT NOT NULL, revision INTEGER NOT NULL, owner TEXT NOT NULL, created REAL NOT NULL);
'''


class EvaluationStore(Database):
    def __init__(self, root):
        super().__init__(root, 'evaluation.sqlite3', SCHEMA)
        with self.transaction() as db:
            if 'is_test' not in {row[1] for row in db.execute('PRAGMA table_info(submission_authors)')}:
                db.execute('ALTER TABLE submission_authors ADD COLUMN is_test INTEGER')
        self.evidence_dir = self.root / 'evidence'
        self.evidence_dir.mkdir(exist_ok=True, mode=0o700)

    def register_reference(self, reference):
        identifier(reference.get('id'))
        with self.transaction() as db:
            old = db.execute('SELECT reference FROM reference_versions WHERE id=?', (reference['id'],)).fetchone()
            require(old is None or old[0] == canonical(reference), 'Reference versions are immutable', 409)
            db.execute('INSERT OR IGNORE INTO reference_versions VALUES(?,?)', (reference['id'], canonical(reference)))
        self.catalog(reference['id'], reference.get('title', reference.get('case_id', '任务 ' + reference['id'][:8])), reference.get('case_id', reference['id']))

    def import_submission(self, payload, fetch_evidence):
        validate_envelope(payload)
        sid, checksum = payload['id'], digest(canonical(payload).encode())
        with self.transaction() as db:
            old = db.execute('SELECT * FROM inbox WHERE id=?', (sid,)).fetchone()
            require(old is None or old['content_hash'] == checksum, 'Submission ID content conflict', 409)
            if old and old['status'] == 'complete':
                return {'id': sid, 'status': 'complete'}
            reference = db.execute('SELECT reference FROM reference_versions WHERE id=?', (payload['task_version_id'],)).fetchone()
            require(reference is not None, 'Reference version missing', 409)
            require(json.loads(reference[0])['query'] == payload['query'], 'Query/reference mismatch', 409)
            for item in payload['evidence']:
                existing = db.execute('SELECT submission_id,sha256 FROM evidence WHERE id=?', (item['id'],)).fetchone()
                require(existing is None or (existing['submission_id'] == sid and existing['sha256'] == item['sha256']), 'Evidence ID conflict', 409)
            db.execute("INSERT OR IGNORE INTO inbox VALUES(?,?,'importing',NULL)", (sid, checksum))
        try:
            # Network I/O is outside the DB transaction; only complete material enters queue.
            for item in payload['evidence']:
                raw = fetch_evidence(sid, item['id'])
                meta = validate_png(raw)
                require(meta['sha256'] == item['sha256'] and meta['size'] == item['size'], 'Evidence hash mismatch', 409)
                temporary = self.evidence_dir / (item['id'] + '.' + checksum[:12] + '.tmp')
                temporary.write_bytes(raw)
                temporary.replace(self.evidence_dir / item['id'])
            with self.transaction() as db:
                db.execute('INSERT OR IGNORE INTO submissions VALUES(?,?,?,?)', (sid, canonical(payload), payload['task_version_id'], time.time()))
                db.execute('INSERT OR IGNORE INTO submission_authors(submission_id,name,is_test) VALUES(?,?,?)', (sid, payload.get('explorer_name', '历史账号'), int(payload.get('test_submission', False))))
                for item in payload['evidence']:
                    db.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)', (item['id'], sid, item['sha256']))
                db.execute('INSERT OR IGNORE INTO review_assignments(submission_id) VALUES(?)', (sid,))
                db.execute("UPDATE inbox SET status='complete',error=NULL WHERE id=?", (sid,))
        except Exception as exc:
            with self.transaction() as db:
                db.execute("UPDATE inbox SET status='error',error=? WHERE id=?", (str(exc)[:200], sid))
            raise
        return {'id': sid, 'status': 'complete'}

    def can_self_review(self, user):
        with self.lock:
            return self.db.execute('SELECT 1 FROM self_review_permissions WHERE user_id=?', (user['id'],)).fetchone() is not None

    def queue(self, user):
        with self.lock:
            rows = self.db.execute("""SELECT a.submission_id AS id,a.state,s.created,a.owner,a.lease_until,
                CASE WHEN a.owner=? THEN 1 ELSE 0 END AS mine,
                CASE WHEN a.state='pending' AND (a.owner IS NULL OR a.lease_until<? OR a.owner=?) THEN 1 ELSE 0 END AS available
                FROM review_assignments a JOIN submissions s ON s.id=a.submission_id
                LEFT JOIN submission_authors author ON author.submission_id=s.id
                WHERE COALESCE(author.is_test,json_extract(s.payload,'$.test_submission'),0)=?
                AND s.task_version_id IN (SELECT task_id FROM task_access WHERE user_id=? AND role='reviewer')
                AND (? OR lower(COALESCE(author.name,''))<>lower(?)) ORDER BY s.created""",
                (user['id'], time.time(), user['id'], int(user.get('is_test', 0)), user['id'], self.can_self_review(user), user['name']))
            return [dict(row) for row in rows]

    def next_submission(self, user, exclude_sid=None):
        """Atomically release unfinished work and claim an unreviewed report."""
        with self.transaction() as db:
            choices = [row for row in self.queue(user)
                       if row['state'] == 'pending' and row['available'] and row['id'] != exclude_sid]
            choices.sort(key=lambda row: (row['created'], row['id']))
            if not choices:
                return {'unavailable': True, 'message': '暂无可领取的未评报告；当前草稿保留。'}
            sid = choices[0]['id']
            db.execute("UPDATE review_assignments SET owner=NULL,lease_until=0 WHERE owner=? AND state='pending' AND submission_id<>?", (user['id'], sid))
            return self.claim(user, sid)

    def claim(self, user, sid=None):
        with self.transaction() as db:
            now = time.time()
            available = self.queue(user)
            if sid is None:
                choices = [row for row in available if row['available']]
                choices.sort(key=lambda row: not row['mine'])
                require(choices, '暂无可领取的答案', 404)
                sid = choices[0]['id']
            require(any(row['id'] == sid for row in available), '答案不存在或未分配给当前复核组', 403)
            row = db.execute('SELECT * FROM review_assignments WHERE submission_id=?', (sid,)).fetchone()
            require(row['owner'] == user['id'] or (row['state'] == 'pending' and (not row['owner'] or row['lease_until'] < now)), '答案已由其他评测员领取', 409)
            db.execute('UPDATE review_assignments SET owner=?,lease_until=? WHERE submission_id=?', (user['id'], now + 300, sid))
        return self.detail(user, sid)

    def detail(self, user, sid):
        with self.lock:
            row = self.db.execute('SELECT * FROM review_assignments WHERE submission_id=?', (sid,)).fetchone()
            require(row and row['owner'] == user['id'], '请先领取这份答案', 403)
            require(row['state'] == 'complete' or row['lease_until'] > time.time(), '领取已过期，请重新领取', 409)
            sub = self.db.execute('SELECT * FROM submissions WHERE id=?', (sid,)).fetchone()
            self.require_access(user, sub['task_version_id'], 'reviewer')
            author = self.db.execute('SELECT name FROM submission_authors WHERE submission_id=?', (sid,)).fetchone()
            require(self.can_self_review(user) or not author or author[0].casefold() != user['name'].casefold(), '不能复核自己的答案', 403)
            cohort = self.db.execute('SELECT is_test FROM submission_authors WHERE submission_id=?', (sid,)).fetchone()
            is_test = cohort[0] if cohort and cohort[0] is not None else json.loads(sub['payload']).get('test_submission', False)
            require(bool(is_test) == bool(user.get('is_test')), '答案不存在', 404)
            reference = self.db.execute('SELECT reference FROM reference_versions WHERE id=?', (sub['task_version_id'],)).fetchone()
            judgment = self.db.execute('SELECT * FROM judgments WHERE submission_id=?', (sid,)).fetchone()
            history = [dict(r) for r in self.db.execute('SELECT revision,created FROM judgment_history WHERE submission_id=? ORDER BY revision', (sid,))]
            return {'submission': json.loads(sub['payload']), 'reference': json.loads(reference[0]), 'state': row['state'], 'lease_until': row['lease_until'], 'judgment': json.loads(judgment['payload']) if judgment else None, 'revision': judgment['revision'] if judgment else 0, 'history': history, 'judgment_options': reason_options(json.loads(sub['payload'])['outcome'])}

    def save_judgment(self, user, sid, data):
        with self.transaction() as db:
            detail = self.detail(user, sid)
            require(data.get('revision') == detail['revision'], '评测已更新，请重新打开', 409)
            require(data.get('judgment_version') == 2, '评测表单已更新，请刷新页面后重新提交；原草稿仍保留在浏览器中。', 409)
            answers = data.get('answers')
            require(isinstance(answers, list), '评测格式错误')
            sub = detail['submission']
            expected = {r['id'] for r in sub['reports']} if sub['outcome'] == 'reports' else {'none'}
            require(len(answers) == len(expected) and {a.get('report_id') for a in answers} == expected, '请逐条完成评测')
            cleaned = []
            options = reason_options(sub['outcome'])
            for answer in answers:
                verdict = answer.get('verdict')
                require(verdict in ('correct', 'incorrect'), '请选择正确或不正确')
                code = answer.get('reason_code', '')
                require(isinstance(code, str), '原因选项无效')
                require((verdict == 'correct' and code == '') or code in options[verdict], '不正确时请选择一个原因；原因须与当前判定相符')
                cleaned.append({'report_id': answer['report_id'], 'verdict': verdict,
                                'reason_code': code, 'reason': options[verdict].get(code, '')})
            payload = canonical({'judgment_version': 2, 'answers': cleaned})
            revision, now = detail['revision'] + 1, time.time()
            db.execute('INSERT INTO judgments VALUES(?,?,?,?,?) ON CONFLICT(submission_id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,owner=excluded.owner,updated=excluded.updated', (sid, payload, revision, user['id'], now))
            db.execute('INSERT INTO judgment_history(submission_id,payload,revision,owner,created) VALUES(?,?,?,?,?)', (sid, payload, revision, user['id'], now))
            db.execute("UPDATE review_assignments SET state='complete' WHERE submission_id=?", (sid,))
        return self.detail(user, sid)

    def evidence(self, user, fid):
        identifier(fid)
        with self.lock:
            row = self.db.execute('SELECT submission_id FROM evidence WHERE id=?', (fid,)).fetchone()
            require(row is not None, '截图不存在', 404)
            self.detail(user, row[0])
            return (self.evidence_dir / fid).read_bytes()
