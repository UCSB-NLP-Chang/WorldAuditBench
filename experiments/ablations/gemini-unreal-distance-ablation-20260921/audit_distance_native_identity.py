"""Bind QA launches to pinned binaries, fresh processes and unchanged task entries."""
from pathlib import Path
import json,hashlib,time,sys,math,re
B=Path(__file__).resolve().parent;sys.path.insert(0,str(B));from prepare_routes import profile
S=json.loads((B/'selection.json').read_text());hashes={};rows=[]
def read(p):return json.loads(p.read_text())
def sha(p):
 p=str(p)
 if p not in hashes:hashes[p]=hashlib.sha256(Path(p).read_bytes()).hexdigest()
 return hashes[p]
for t in S['tasks']:
 tid=t['id'];row={'id':tid,'passed':False,'arms':{}}
 try:
  p=profile(t);binary=p['binary'];assert sha(binary)==t['build_sha256'],(tid,'binary hash mismatch')
  orig=read(Path(t['source_remote'])/'pinned-production/policies'/t['policy_sha256'])['tasks'][tid];geom=read(B/'route-preparation'/tid/'result.json');pids=[];userdirs=[]
  for arm in ['far','near','medium']:
   d=B/'rendered-route-qa'/tid/arm;cmd=read(d/'launch-command.json');state=read(d/'initial-state.json');proc=read(d/'process.json')
   assert cmd[0]==binary and cmd[1]==t['map'] and '-AuditorRemoteTask='+tid in cmd and '-AuditorExplorationTask='+tid in cmd
   policies=[Path(x.split('=',1)[1]) for x in cmd if x.startswith('-AuditorExplorationPolicy=')];assert len(policies)==1
   actual=read(policies[0])['tasks'][tid];expected=orig if arm=='far' else geom['arms'][arm]['policy'];assert actual==expected
   changed=[k for k in set(orig)|set(actual) if orig.get(k)!=actual.get(k)];assert set(changed)<={'spawn','route_to_old_spawn'}
   assert state['simulation_time']==0 and state['task_id']==tid
   assert math.dist(state['position_cm'],actual['spawn'])<10 and abs((state['yaw_degree']-actual['yaw']+180)%360-180)<.2
   userdir=next(x.split('=',1)[1] for x in cmd if x.startswith('-UserDir='));assert userdir==str(d/'user') and '-NoSaveConfig' in cmd
   markers=read(d/'initial-trigger-evidence.json')['native_log_markers'];ready=[x for x in markers if ('READY' in x and ('id='+tid) in x)]
   if not ready and t['family']=='urban':
    assert state['result']=='ready' and state['paused']
    ready=[x for x in (d/'native.log').read_text(errors='replace').splitlines() if 'AUDITOR_REMOTE_READY id='+tid+' ' in x]
   assert ready,(tid,arm,'no affirmative native-ready marker')
   pids.append(proc['pid']);userdirs.append(userdir)
   row['arms'][arm]={'process_pid':proc['pid'],'user_dir':userdir,'simulation_time':0,'ready_markers':ready,'initial_image_sha256':sha(d/'initial.png'),'launch_command_sha256':sha(d/'launch-command.json'),'initial_state_sha256':sha(d/'initial-state.json'),'policy_sha256':sha(policies[0]),'changed_keys':changed}
  assert len(set(pids))==3 and len(set(userdirs))==3
  row.update(passed=True,build_sha256=sha(binary),binary=binary,task_map=t['map'],verification_basis='Same pinned executable/map/task and fresh per-arm process/user directory; only spawn/route policy changes; affirmative task-ready evidence at simulation_time=0. Visual/temporal behavior is a separate empirical check; no claim of internal-memory equality or unbound source audit.')
 except Exception as exc:row['error']=repr(exc)
 rows.append(row)
result={'updated_at':time.time(),'tasks':rows,'checked':len(rows),'passed_count':sum(r['passed'] for r in rows),'passed':all(r['passed'] for r in rows),'approved_for_model':False}
(B/'native-initialization-identity-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='tasks'}));print('errors',[(r['id'],r.get('error')) for r in rows if not r['passed']])
