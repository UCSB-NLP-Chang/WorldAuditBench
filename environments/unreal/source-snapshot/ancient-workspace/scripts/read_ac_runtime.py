"""Read only the runtime belonging to this task's technical login."""
import sys,json,sqlite3
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor');own=json.loads((r/'ancient-workspace/out/ac-v2/qa-cookie.json').read_text())['owner'];sid=sys.argv[1]
with sqlite3.connect('file:'+str(r/'review-service/state/review.sqlite3')+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row;row=db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone();assert row and row['owner']==own
state=r/'review-service/state';runtime=row['runtime_id'] or sid
path=Path(json.loads((state/'runtime.json').read_text())['state_dir'])/runtime/'review-ipc/response.json'
data=json.loads(path.read_text());print(json.dumps({k:data[k] for k in ('pid','generation','map','task','status','position')}))
