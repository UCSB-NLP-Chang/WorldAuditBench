"""Exploration persistence: public tasks, drafts, immutable submissions, outbox."""
import json
import time
from .common import Database, canonical, digest, require, uid
from .contracts import identifier, validate_envelope
from .taxonomy import category
from .images import decode_png, validate_png
from . import allocation
from .taxonomy import TAXONOMY

SCHEMA = '''
CREATE TABLE IF NOT EXISTS task_versions(id TEXT PRIMARY KEY, public_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), task_version_id TEXT NOT NULL REFERENCES task_versions(id), status TEXT NOT NULL, draft TEXT NOT NULL, draft_version INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_sessions(id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id), created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS flags(id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id), runtime_id TEXT NOT NULL REFERENCES runtime_sessions(id), sha256 TEXT NOT NULL, size INTEGER NOT NULL, captured_at REAL NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS deleted_flags(id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id), deleted REAL NOT NULL);
CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY, attempt_id TEXT UNIQUE NOT NULL REFERENCES attempts(id), payload TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(submission_id TEXT PRIMARY KEY REFERENCES submissions(id), attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0, delivered REAL, last_error TEXT);
'''


class ExplorationStore(Database):
    def __init__(self, root):
        super().__init__(root, 'exploration.sqlite3', SCHEMA + allocation.SCHEMA)
        self.guidance = None
        with self.transaction() as db:
            if 'updated' not in {row[1] for row in db.execute('PRAGMA table_info(attempts)')}:
                db.execute('ALTER TABLE attempts ADD COLUMN updated REAL')
                db.execute('UPDATE attempts SET updated=created')
            db.execute('DROP INDEX IF EXISTS one_active_attempt')
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_task_attempt ON attempts(owner,task_version_id) WHERE status='draft'")
        self.evidence_dir = self.root / 'evidence'
        self.evidence_dir.mkdir(exist_ok=True, mode=0o700)

    def register_task(self, task):
        # Construct an allowlisted public object; never serialize a source manifest.
        public = {k: task[k] for k in ('id', 'title', 'query', 'controls')}
        identifier(public['id'])
        with self.transaction() as db:
            old = db.execute('SELECT public_json FROM task_versions WHERE id=?', (public['id'],)).fetchone()
            require(old is None or old[0] == canonical(public), 'Task versions are immutable', 409)
            db.execute('INSERT OR IGNORE INTO task_versions VALUES(?,?)', (public['id'], canonical(public)))
        self.catalog(public['id'], public['title'], task.get('case_key', public['id']))

    def owned(self, db, aid, user):
        row = db.execute('SELECT * FROM attempts WHERE id=? AND owner=?', (aid, user['id'])).fetchone()
        require(row is not None, '探索记录不存在', 404)
        self.require_access(user, row['task_version_id'], 'explorer')
        return row

    def task(self, version):
        with self.lock:
            row = self.db.execute('SELECT public_json FROM task_versions WHERE id=?', (version,)).fetchone()
            require(row is not None, '任务不存在', 404)
            result = json.loads(row[0])
            from .environments import description_for
            result['environment_description'] = description_for(version)
            if self.guidance is not None:
                codes = self.guidance.get(version, [])
                result['human_eligible'] = bool(codes)
                result['ground_truth_categories'] = [{k:c[k] for k in ('id','name','description')} for c in TAXONOMY['categories'] if c['id'] in codes]
            return result

    def snapshot(self, user, aid=None, task_id=None):
        with self.lock:
            if aid is None:
                row = self.db.execute("SELECT * FROM attempts WHERE owner=? AND (? IS NULL OR task_version_id=?) AND task_version_id IN (SELECT task_id FROM task_access WHERE user_id=? AND role='explorer') ORDER BY created DESC LIMIT 1", (user['id'], task_id, task_id, user['id'])).fetchone()
                if row is None:
                    return None
            else:
                row = self.owned(self.db, aid, user)
            flags = [dict(r) for r in self.db.execute('SELECT id,captured_at,created FROM flags WHERE attempt_id=? ORDER BY created', (row['id'],))]
            submission = self.db.execute('SELECT s.id,o.delivered FROM submissions s JOIN outbox o ON o.submission_id=s.id WHERE s.attempt_id=?', (row['id'],)).fetchone()
            return {'id': row['id'], 'status': row['status'], 'task': self.task(row['task_version_id']), 'draft': json.loads(row['draft']), 'draft_version': row['draft_version'], 'flags': flags, 'submission': dict(submission) if submission else None}

    def start_attempt(self, user, task_id):
        self.task(task_id)
        require(self.guidance is None or self.guidance.get(task_id), '该题不在当前有 bug 的探索题池中；历史记录仍可查看。', 409)
        self.require_access(user, task_id, 'explorer')
        with self.transaction() as db:
            old = db.execute("SELECT id FROM attempts WHERE owner=? AND task_version_id=? AND status='draft'", (user['id'], task_id)).fetchone()
            if old:
                aid = old[0]
            else:
                aid = uid()
                db.execute('INSERT INTO attempts(id,owner,task_version_id,status,draft,draft_version,created) VALUES(?,?,?,?,?,?,?)', (aid, user['id'], task_id, 'draft', canonical({'reports': [], 'outcome': 'reports'}), 0, time.time()))
        return self.snapshot(user, aid)

    def save_draft(self, user, aid, data):
        draft = data.get('draft')
        require(isinstance(draft, dict) and draft.get('outcome') in ('reports', 'none', 'technical'), '草稿格式错误')
        reports = draft.get('reports')
        require(isinstance(reports, list) and len(reports) <= 20, '最多 20 条报告')
        clean, seen = [], set()
        for report in reports:
            rid = identifier(report.get('id'))
            require(rid not in seen, '报告编号重复')
            seen.add(rid)
            description = report.get('description')
            evidence = report.get('evidence_ids')
            require(isinstance(description, str) and len(description) <= 10000, '描述最多 10000 字')
            require(isinstance(evidence, list) and len(evidence) <= 30 and all(isinstance(e, str) for e in evidence), '截图列表错误')
            clean.append({'id': rid, 'description': description, 'category': category(report.get('category', 'unsure')), 'evidence_ids': list(dict.fromkeys(evidence))})
        note = draft.get('technical_note', '')
        require(isinstance(note, str) and len(note) <= 10000, '技术问题描述过长')
        draft = {'reports': clean, 'outcome': draft['outcome'], 'technical_note': note}
        with self.transaction() as db:
            row = self.owned(db, aid, user)
            require(row['status'] == 'draft', '已提交的答案不能修改', 409)
            require(data.get('version') == row['draft_version'], '草稿已在其他页面更新，请刷新后重试', 409)
            allowed = {r[0] for r in db.execute('SELECT id FROM flags WHERE attempt_id=?', (aid,))}
            require(all(set(r['evidence_ids']) <= allowed for r in clean), '截图不属于当前探索')
            db.execute('UPDATE attempts SET draft=?,draft_version=draft_version+1,updated=? WHERE id=?', (canonical(draft), time.time(), aid))
        return self.snapshot(user, aid)

    def record_runtime(self, aid, user, rid):
        with self.transaction() as db:
            row = self.owned(db, aid, user)
            require(row['status'] == 'draft', '探索已经结束', 409)
            db.execute('INSERT INTO runtime_sessions VALUES(?,?,?)', (rid, aid, time.time()))

    def add_flag(self, user, aid, data):
        fid, rid = identifier(data.get('id')), identifier(data.get('runtime_id'))
        captured = data.get('captured_at')
        require(isinstance(captured, (int, float)) and abs(time.time() - captured) < 86400, '截图时间无效')
        raw = decode_png(data.get('content_base64'))
        meta = validate_png(raw)
        with self.transaction() as db:
            row = self.owned(db, aid, user)
            require(row['status'] == 'draft', '探索已经提交', 409)
            require(db.execute('SELECT 1 FROM runtime_sessions WHERE id=? AND attempt_id=?', (rid, aid)).fetchone(), '截图会话不匹配')
            require(not db.execute('SELECT 1 FROM deleted_flags WHERE id=?', (fid,)).fetchone(), '截图已删除，不能重新上传', 409)
            old = db.execute('SELECT * FROM flags WHERE id=?', (fid,)).fetchone()
            if old:
                require(old['attempt_id'] == aid and old['runtime_id'] == rid and old['sha256'] == meta['sha256'], '截图编号冲突', 409)
            else:
                require(db.execute('SELECT count(*) FROM flags WHERE attempt_id=?', (aid,)).fetchone()[0] < 30, '最多 30 张截图')
                path = self.evidence_dir / fid
                temporary = self.evidence_dir / (fid + '.tmp')
                temporary.write_bytes(raw)
                temporary.replace(path)
                db.execute('INSERT INTO flags VALUES(?,?,?,?,?,?,?)', (fid, aid, rid, meta['sha256'], len(raw), captured, time.time()))
                db.execute('UPDATE attempts SET updated=? WHERE id=?', (time.time(), aid))
        return {'id': fid}

    def delete_flag(self, user, aid, data):
        fid = identifier(data.get('id'))
        with self.transaction() as db:
            row = self.owned(db, aid, user)
            require(row['status'] == 'draft', '已提交的截图不能删除', 409)
            deleted = db.execute('SELECT attempt_id FROM deleted_flags WHERE id=?', (fid,)).fetchone()
            require(not deleted or deleted[0] == aid, '截图不存在', 404)
            if not deleted:
                require(data.get('version') == row['draft_version'], '草稿已在其他页面更新，请刷新后重试', 409)
                flag = db.execute('SELECT attempt_id FROM flags WHERE id=?', (fid,)).fetchone()
                require(not flag or flag[0] == aid, '截图不存在', 404)
                draft = json.loads(row['draft'])
                for report in draft['reports']:
                    report['evidence_ids'] = [eid for eid in report['evidence_ids'] if eid != fid]
                # Tombstone also cancels uploads whose response was lost. Retain the
                # original file for recovery; it is no longer addressable via the API.
                db.execute('INSERT INTO deleted_flags VALUES(?,?,?)', (fid, aid, time.time()))
                db.execute('DELETE FROM flags WHERE id=? AND attempt_id=?', (fid, aid))
                db.execute('UPDATE attempts SET draft=?,draft_version=draft_version+1,updated=? WHERE id=?', (canonical(draft), time.time(), aid))
        return self.snapshot(user, aid)

    def evidence(self, fid, user=None, submission_id=None):
        identifier(fid)
        with self.lock:
            row = self.db.execute('SELECT f.*,a.owner FROM flags f JOIN attempts a ON a.id=f.attempt_id WHERE f.id=?', (fid,)).fetchone()
            require(row is not None, '截图不存在', 404)
            if user:
                self.owned(self.db, row['attempt_id'], user)
                require(row['owner'] == user['id'], '截图不存在', 404)
            else:
                sub = self.db.execute('SELECT payload FROM submissions WHERE id=? AND attempt_id=?', (submission_id, row['attempt_id'])).fetchone()
                require(sub and fid in {e['id'] for e in json.loads(sub[0])['evidence']}, '截图未包含在提交中', 404)
            return (self.evidence_dir / fid).read_bytes()

    def submit(self, user, aid, data):
        with self.transaction() as db:
            row = self.owned(db, aid, user)
            old = db.execute('SELECT id FROM submissions WHERE attempt_id=?', (aid,)).fetchone()
            if old:
                return {'id': old[0]}
            require(row['status'] == 'draft', '探索已经结束', 409)
            require(data.get('version') == row['draft_version'], '请先保存最新草稿', 409)
            draft = json.loads(row['draft'])
            if self.guidance is not None and draft['outcome'] == 'none':
                db.execute("UPDATE attempts SET status='skipped',updated=? WHERE id=?", (time.time(),aid))
                allocation.finish(self,user,aid)
                return {'status':'skipped'}
            if draft['outcome'] == 'technical':
                require(draft.get('technical_note', '').strip(), '请描述技术问题')
                db.execute("UPDATE attempts SET status='technical',updated=? WHERE id=?", (time.time(), aid))
                allocation.finish(self,user,aid)
                return {'status': 'technical'}
            require(db.execute('SELECT 1 FROM runtime_sessions WHERE attempt_id=?', (aid,)).fetchone(), '请先进入环境')
            reports = draft['reports'] if draft['outcome'] == 'reports' else []
            used = {eid for r in reports for eid in r['evidence_ids']}
            evidence = [{'id': f['id'], 'sha256': f['sha256'], 'size': f['size'], 'mime': 'image/png', 'captured_at': f['captured_at']} for f in db.execute('SELECT * FROM flags WHERE attempt_id=? ORDER BY created', (aid,)) if f['id'] in used]
            sid = uid()
            payload = {'schema_version': 1, 'id': sid, 'attempt_id': aid, 'task_version_id': row['task_version_id'], 'query': self.task(row['task_version_id'])['query'], 'outcome': draft['outcome'], 'reports': reports, 'evidence': evidence, 'submitted_at': time.time(), 'test_submission': bool(user.get('is_test')), 'explorer_name': user['name']}
            if self.guidance is not None:
                payload['exploration_protocol']='category_guided_v1'
                payload['provided_categories']=self.guidance.get(row['task_version_id'],[])
            validate_envelope(payload)
            db.execute('INSERT INTO submissions VALUES(?,?,?,?)', (sid, aid, canonical(payload), time.time()))
            db.execute('INSERT INTO outbox(submission_id) VALUES(?)', (sid,))
            db.execute("UPDATE attempts SET status='submitted',updated=? WHERE id=?", (time.time(), aid))
            allocation.finish(self,user,aid)
            return {'id': sid}

    def delivery_batch(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT s.id,s.payload,o.attempts FROM submissions s JOIN outbox o ON s.id=o.submission_id WHERE o.delivered IS NULL AND o.next_try<=? LIMIT 4', (time.time(),))]

    def delivery_result(self, sid, error=None):
        with self.transaction() as db:
            if error is None:
                db.execute('UPDATE outbox SET delivered=?,last_error=NULL WHERE submission_id=?', (time.time(), sid))
            else:
                db.execute('UPDATE outbox SET attempts=attempts+1,next_try=?+min(300,5*(attempts+1)),last_error=? WHERE submission_id=?', (time.time(), str(error)[:200], sid))
