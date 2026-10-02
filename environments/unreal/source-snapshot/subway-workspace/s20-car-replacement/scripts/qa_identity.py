from pathlib import Path
import sqlite3,json,secrets,hashlib,time,sys
work=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20-car-replacement');state=Path('/home/ubuntu/unreal-auditor/review-service/state');record=work/'qa-login.json';db=sqlite3.connect(state/'review.sqlite3')
if sys.argv[1]=='create':
 assert not record.exists();cookie=secrets.token_urlsafe(32);owner='subway-s20-coupe-qa-'+secrets.token_hex(16)
 db.execute('INSERT INTO logins VALUES(?,?,?,?)',(hashlib.sha256(cookie.encode()).hexdigest(),owner,'Subway S20 QA',time.time()+3600));db.commit()
 record.write_text(json.dumps(dict(cookie=cookie,owner=owner,cookie_name=json.loads((state/'service-env.json').read_text()).get('REVIEW_COOKIE_NAME','review_session'))));record.chmod(0o600);print('QA identity created')
else:
 d=json.loads(record.read_text());assert not db.execute("SELECT 1 FROM sessions WHERE owner=? AND status NOT IN ('closed','failed')",(d['owner'],)).fetchone();assert not db.execute('SELECT 1 FROM feedback WHERE owner=?',(d['owner'],)).fetchone();db.execute('DELETE FROM logins WHERE owner=?',(d['owner'],));db.commit();record.unlink();print('QA login removed; closed technical sessions retained for audit')
db.close()
