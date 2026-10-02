"""Create a dedicated short-lived technical login; never borrow a reviewer identity."""
import secrets,hashlib,json,sqlite3,time
from pathlib import Path
out=Path('/home/ubuntu/unreal-auditor/ancient-workspace/out/indoor-cola-v3/qa-cookie.json');assert not out.exists()
owner='qa-ancient-'+secrets.token_hex(8);cookie=secrets.token_urlsafe(32)
with sqlite3.connect('/home/ubuntu/unreal-auditor/review-service/state/review.sqlite3') as db:
 db.execute('INSERT INTO logins VALUES(?,?,?,?)',(hashlib.sha256(cookie.encode()).hexdigest(),owner,'Ancient technical QA',time.time()+7200));db.commit()
out.write_text(json.dumps(dict(cookie=cookie,owner=owner)));out.chmod(0o600)
print('Dedicated technical login created; cookie stored privately.')
