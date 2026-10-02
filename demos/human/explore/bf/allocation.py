"""Persistent, cohort-isolated claims for category-guided human exploration."""
import time
from .common import require, uid, canonical

SCHEMA = '''CREATE TABLE IF NOT EXISTS exploration_claims(
 owner TEXT PRIMARY KEY REFERENCES users(id), task_id TEXT NOT NULL REFERENCES task_versions(id),
 case_key TEXT NOT NULL, cohort INTEGER NOT NULL, attempt_id TEXT NOT NULL REFERENCES attempts(id),
 expires REAL NOT NULL, created REAL NOT NULL, UNIQUE(cohort,case_key));'''
TTL = 180
MAX_AGE = 3600


def claim(store, user, task_id=None, exclude_task_id=None):
    require(store.guidance is not None, '自动分配尚未启用', 409)
    if task_id is not None:
        require(bool(store.guidance.get(task_id)), '该题不在当前探索题池中；历史记录仍可查看。', 409)
    now = time.time(); cohort = int(user.get('is_test', 0))
    with store.lock:
        with store.transaction() as db:
            db.execute('DELETE FROM exploration_claims WHERE expires<=? OR created<=?', (now,now-MAX_AGE))
            existing = db.execute('SELECT * FROM exploration_claims WHERE owner=?', (user['id'],)).fetchone()
            if existing and not store.guidance.get(existing['task_id']):
                db.execute('DELETE FROM exploration_claims WHERE owner=?', (user['id'],))
                existing = None
            if existing:
                require(task_id is None or existing['task_id']==task_id, '请先提交或放弃当前领取的题目，再领取下一题。', 409)
                store.require_access(user,existing['task_id'],'explorer')
                return store.snapshot(user,existing['attempt_id'])
            tasks=store.accessible_tasks(user,'explorer')
            eligible=[t for t in tasks if t['id'] != exclude_task_id and store.guidance.get(t['id']) and (task_id is None or t['id']==task_id)]
            busy={r[0] for r in db.execute('SELECT case_key FROM exploration_claims WHERE cohort=?',(cohort,))}
            done={r[0] for r in db.execute("SELECT t.case_key FROM attempts a JOIN task_catalog t ON t.id=a.task_version_id WHERE a.owner=? AND a.status IN ('submitted','skipped','technical')",(user['id'],))}
            stats={r[0]:(r[1],r[2]) for r in db.execute("""SELECT t.case_key,sum(a.status IN ('submitted','skipped','technical')),max(a.created)
                FROM attempts a JOIN task_catalog t ON t.id=a.task_version_id JOIN users u ON u.id=a.owner WHERE u.is_test=? GROUP BY t.case_key""",(cohort,))}
            available=[t for t in eligible if t['case_key'] not in busy and t['case_key'] not in done]
            if not available:
                if task_id:require(False,'该题已由你完成／放弃、被其他人领取，或不在当前 bug 题池中。',409)
                return {'unavailable':True,'message':'暂时没有可领取的题目：你已处理全部可用题目，或剩余题目正在被其他人探索。请稍后重试。'}
            chosen=min(available,key=lambda t:(*stats.get(t['case_key'],(0,0)),t['id']))
            old=db.execute("SELECT id FROM attempts WHERE owner=? AND task_version_id=? AND status='draft'",(user['id'],chosen['id'])).fetchone()
            aid=old[0] if old else uid()
            if not old:
                db.execute('INSERT INTO attempts(id,owner,task_version_id,status,draft,draft_version,created) VALUES(?,?,?,?,?,?,?)',(aid,user['id'],chosen['id'],'draft',canonical({'reports':[],'outcome':'reports'}),0,now))
            attempt={'id':aid}
            db.execute('INSERT INTO exploration_claims VALUES(?,?,?,?,?,?,?)',(user['id'],chosen['id'],chosen['case_key'],cohort,attempt['id'],now+TTL,now))
        return store.snapshot(user,attempt['id'])


def heartbeat(store,user,aid):
    with store.transaction() as db:
        db.execute('UPDATE exploration_claims SET expires=? WHERE owner=? AND attempt_id=? AND expires>? AND created>?',(time.time()+TTL,user['id'],aid,time.time(),time.time()-MAX_AGE))


def finish(store, user, aid):
    store.db.execute('DELETE FROM exploration_claims WHERE owner=? AND attempt_id=?',(user['id'],aid))
