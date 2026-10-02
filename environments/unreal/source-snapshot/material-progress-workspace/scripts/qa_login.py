"""Create or revoke one dedicated, read-only browser QA login. No review sessions."""
from pathlib import Path
import hashlib,json,secrets,sqlite3,sys,time
work=Path('/home/ubuntu/unreal-auditor/material-progress-workspace');path=work/'qa-cookie.json';db=sqlite3.connect(work.parent/'review-service/state/review.sqlite3')
if sys.argv[1]=='mint':
 assert not path.exists()
 owner='qa-material-progress-'+secrets.token_hex(12);cookie=secrets.token_urlsafe(32)
 db.execute('INSERT INTO logins VALUES(?,?,?,?)',(hashlib.sha256(cookie.encode()).hexdigest(),owner,'Material progress technical QA',time.time()+3600));db.commit()
 path.touch(mode=0o600);path.write_text(json.dumps({'cookie':cookie,'owner':owner}));print('Dedicated QA login created')
else:
 data=json.loads(path.read_text());assert data['owner'].startswith('qa-material-progress-')
 assert not db.execute('SELECT 1 FROM sessions WHERE owner=?',(data['owner'],)).fetchone()
 assert not db.execute('SELECT 1 FROM feedback WHERE owner=?',(data['owner'],)).fetchone()
 db.execute('DELETE FROM logins WHERE owner=?',(data['owner'],));db.commit();path.unlink();print('QA login revoked; no sessions or feedback created')
db.close()
