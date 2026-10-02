"""Check all42 private catalogs and seven representative live HTTP runtimes, no model calls."""
from pathlib import Path
import json,sys,subprocess,time,urllib.request,os,signal,importlib.util
from admission_guard import digest
B=Path(__file__).resolve().parent
C=B.parent/'gemini-unreal-icl-ablation-20260921/code';sys.path.insert(0,str(C))
from batch_reservation import Reservation
J=B/'private-runtime-preflight-reservation.json'

def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def main():
 s=json.loads((B/'episodes-selection.json').read_text());out={'status':'running','model_calls':0,'catalogs':[],'live':[]};chosen={}
 for t in s['tasks']:
  prod=Path(t['private_production']);tasks=json.loads((prod/'audit/tasks.json').read_text())['tasks'];assert len(tasks)==1 and tasks[0]['id']==t['task_id']
  p=list(json.loads((prod/'audit/runtime.json').read_text())['launch_profiles'].values());assert len(p)==1
  assert p[0]['binary']==t['binary_path'] and p[0]['build_sha256']==t['build_sha256']
  assert '-AuditorComposition='+str(B/t['composition_spec']) in p[0]['extra_args']
  assert digest(B/t['composition_spec'])==t['composition_sha256']
  out['catalogs'].append(t['id'])
  if t['condition']=='ABC':chosen.setdefault(t['family'],t)
 assert len(chosen)==7
 lease=Reservation(Path('/home/ec2-user/unreal-production'),J,[0]);proc=None
 try:
  lease.acquire()
  for family,t in chosen.items():
   d=B/'private-runtime-preflight'/t['id'];d.mkdir(parents=True,exist_ok=False);source=Path(t['source_remote'])/'code';py=source/'out/native-agents/venv/bin/python'
   cmd=[str(py),'-u',str(source/'remote_unreal.py'),'--production',t['private_production'],'--task',t['task_id'],'--gpu','0','--gpu-slots','2','--gpu-slot','0','--port','51910','--state-root',str(B/'preflight-native'),'--batch-reservation',str(J)]
   with (d/'server.log').open('x') as log:proc=subprocess.Popen(cmd,cwd=source,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   deadline=time.monotonic()+210;native=None
   while time.monotonic()<deadline:
    if proc.poll() is not None:raise RuntimeError('Runtime exited: '+t['id'])
    for line in (d/'server.log').read_text().splitlines():
     try:r=json.loads(line)
     except ValueError:continue
     if isinstance(r,dict) and r.get('state'):native=Path(r['state'])
    try:
     with urllib.request.urlopen('http://127.0.0.1:51910/health',timeout=2) as f:h=json.load(f)
     if native and (native/'response.json').exists():
      r=json.loads((native/'response.json').read_text());c=json.loads((native/'composition-status.json').read_text())
      if h.get('engine_alive') and r.get('paused') and r.get('frames'):
       assert h['build_sha256']==t['build_sha256'] and h['policy_sha256']==t['policy_sha256'] and h['task_id']==t['task_id']
       assert c['status']=='applied' and c['added_count']==2 and c['specification']==str(B/t['composition_spec'])
       write(d/'verification.json',{'health':h,'composition':c,'native':str(native),'model_calls':0});break
    except (OSError,ValueError):pass
    time.sleep(.25)
   else:raise TimeoutError(t['id'])
   os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=30);proc=None
   out['live'].append(t['id']);write(B/'private-runtime-preflight-status.json',out);print(t['id'],'private native HTTP verified',flush=True)
  out['status']='passed'
 except Exception as e:out.update(status='failed',error=repr(e));raise
 finally:
  if proc and proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=30)
  lease.release();write(B/'private-runtime-preflight-status.json',out)
if __name__=='__main__':main()
