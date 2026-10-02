"""Isolated synthetic browser fixture. Never reads or writes production review data."""
import json,sys,tempfile,time
from pathlib import Path
work=Path('/home/ubuntu/unreal-auditor/material-progress-workspace');stage=work/'material-progress-20260913-v1'
sys.path.insert(0,str(stage))
from server import Store,make_server
from participants import Participants
tmp=tempfile.TemporaryDirectory(prefix='material-progress-fixture-')
s=Store(Path(tmp.name)/'review.sqlite3',json.loads((stage/'tasks.json').read_text()),tokens={'fixture-login':{'id':'fixture-a','reviewer':'Alice'}})
p=Participants(s,{'mode':'token'})
for owner,name in [('fixture-a','Alice'),('fixture-b','Bob'),('fixture-none','No reviews')]:
 s.db.execute('INSERT INTO participants VALUES(?,?,?,?)',(owner,name.casefold(),name,time.time()))
for i,(owner,name,tid,quality,stale) in enumerate([
 ('fixture-a','Alice','S01','pass',False),('fixture-a','Alice','S01','fail',False),
 ('fixture-a','Alice','JS_SP09','uncertain',False),('fixture-a','Alice','H03','pass',False),
 ('fixture-b','Bob','H03','pass',False),('fixture-b','Bob','JS_SP09','pass',False),
 ('fixture-a','Alice','S02','pass',True)]):
 task=s.tasks[tid];v={k:task[k] for k in ['revision','sha256','build_sha256']}
 v.update(task_id=tid,reviewer=name,quality=quality,mode='mock')
 if stale:v['sha256']='0'*64
 payload=json.dumps(v);s.db.execute('INSERT INTO feedback VALUES(?,?,?,?,?)',(str(i),str(i),owner,time.time()+i,payload))
 s.append_review_history(str(i),str(i),owner,time.time()+i,v)
s.db.commit();http=make_server(s,port=18098);http.participants=p
print('Fixture ready on 18098',flush=True)
try:http.serve_forever()
finally:http.server_close();s.db.close();tmp.cleanup()
