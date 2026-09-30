from pathlib import Path
import sqlite3,json,hashlib
out=Path('/home/ubuntu/unreal-auditor/indoor-h10-start-workspace/out');p=out/'qa-cookie.json';auth=json.loads(p.read_text());owner=auth['owner'];assert owner.startswith('qa-h10-start-')
with sqlite3.connect('/home/ubuntu/unreal-auditor/review-service/state/review.sqlite3') as db:
 rows=db.execute('SELECT id,status FROM sessions WHERE owner=?',(owner,)).fetchall();assert rows and all(s in ('closed','failed') for _,s in rows),rows
 counts={t:db.execute('SELECT COUNT(*) FROM '+t+' WHERE owner=?',(owner,)).fetchone()[0] for t in ['feedback','review_history','evidence']};assert not any(counts.values()),counts
 db.execute('DELETE FROM logins WHERE token_hash=? AND owner=?',(hashlib.sha256(auth['cookie'].encode()).hexdigest(),owner));db.commit()
p.unlink();(out/'cleanup.json').write_text(json.dumps(dict(result='PASS',own_sessions=rows,review_records=counts,login_removed=True),indent=2));print('Owned AC QA session closed; no review records submitted; login revoked.')
