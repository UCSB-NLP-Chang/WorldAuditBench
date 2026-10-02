from pathlib import Path
import json,sqlite3,hashlib,secrets,time,sys
root=Path('/home/ubuntu/unreal-auditor/review-service');db=sqlite3.connect(root/'state/review.sqlite3')
record=root/'staging/ancient-core18-20260912/canary-identities.json'
if sys.argv[1]=='create':
 assert not record.exists()
 entries=[]
 for letter in ('A','B'):
  cookie=secrets.token_urlsafe(32);owner='ancient-qa-'+secrets.token_hex(16)
  db.execute('INSERT INTO logins VALUES(?,?,?,?)',(hashlib.sha256(cookie.encode()).hexdigest(),owner,'Ancient QA '+letter,time.time()+1800))
  entries.append(dict(cookie=cookie,owner=owner))
 db.commit();record.write_text(json.dumps(entries));record.chmod(0o600)
 print(json.dumps(entries))
elif sys.argv[1]=='cleanup':
 entries=json.loads(record.read_text())
 for entry in entries:
  assert not db.execute("SELECT 1 FROM sessions WHERE owner=? AND status IN ('queued','starting','ready','resetting','switching','closing')",(entry['owner'],)).fetchone()
  assert not db.execute('SELECT 1 FROM feedback WHERE owner=?',(entry['owner'],)).fetchone()
  db.execute('DELETE FROM logins WHERE owner=?',(entry['owner'],))
 db.commit();record.unlink();print('Temporary canary logins removed; no feedback submitted.')
db.close()

