from pathlib import Path
import json,sqlite3,sys,re
sid=sys.argv[1];assert re.fullmatch('[0-9a-f]{32}',sid)
r=Path('/home/ubuntu/unreal-auditor/review-service/state');db=sqlite3.connect('file:'+str(r/'review.sqlite3')+'?mode=ro',uri=True)
row=db.execute('SELECT runtime_id FROM sessions WHERE id=?',(sid,)).fetchone();assert row
runtime=row[0] or sid
path=Path(json.loads((r/'runtime.json').read_text())['state_dir'])/runtime/'review-ipc/response.json'
s=json.loads(path.read_text());print(json.dumps({k:s[k] for k in ('pid','generation','map','task','status','position')}));db.close()
