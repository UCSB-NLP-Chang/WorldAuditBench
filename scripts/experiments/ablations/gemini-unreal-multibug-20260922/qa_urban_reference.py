"""Compare original and isolated A-only runtime, with no model or judge calls."""
from pathlib import Path
import hashlib,json,math,os,shutil,signal,subprocess,sys,time,uuid
B=Path('/mnt/auditor-build/experiment-runs/gemini-unreal-multibug-20260922')
sys.path.insert(0,str(B.parent/'gemini-unreal-icl-ablation-20260921/code'))
from batch_reservation import Reservation,verify
STOP=False
ACTIVE=None
GPU=0
JOURNAL=B/'reference-qa-reservation.json'

def write(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(d,indent=2));tmp.replace(p)
def terminate(p):
 if p and p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
def stop(*_):
 global STOP
 STOP=True

def stage(ref,binary):
 old=Path(ref['profile']['binary']);root=old.parents[3];dest=B/'packages'/(ref['family']+'-'+ref['id']);assert not dest.exists()
 dest.parent.mkdir(parents=True,exist_ok=True)
 relative=old.relative_to(root)
 def mirror(source,target):
  target.mkdir()
  for p in source.iterdir():
   q=target/p.name
   if p==old:shutil.copy2(binary,q)
   elif old.is_relative_to(p):mirror(p,q)
   else:q.symlink_to(p,target_is_directory=p.is_dir())
 mirror(root,dest)
 return dest/relative

def run(ref,kind,binary):
 global ACTIVE
 tid=ref['id'];d=B/'qa-reference'/tid/kind;d.mkdir(parents=True,exist_ok=False)
 p=ref['profile'];args=[x for x in p.get('game_args',[])+p.get('extra_args',[]) if not x.lower().startswith(('-pixelstreaming','-graphicsadapter','-auditoripc','-abslog','-auditorremote','-resx','-resy'))]
 cmd=[str(binary),p['runtime_map'],'-RenderOffscreen','-windowed','-ResX=960','-ResY=540','-nosound','-unattended','-AuditorServe','-AuditorRemoteTask='+tid,'-AuditorIPC='+str(d),'-abslog='+str(d/'native.log'),'-graphicsadapter='+str(GPU),'-UserDir='+str(d/'user'),'-NoSaveConfig',*args]
 if kind=='candidate':cmd.append('-AuditorCompositionInventory')
 write(d/'launch-command.json',cmd);verify(JOURNAL,GPU)
 with (d/'stdout.log').open('w') as log:
  ACTIVE=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  write(d/'process.json',{'pid':ACTIVE.pid,'time':time.time()})
  def wait(req):
   end=time.monotonic()+180
   while time.monotonic()<end:
    if STOP:raise RuntimeError('QA interrupted')
    if ACTIVE.poll() is not None:raise RuntimeError('Native exited '+str(ACTIVE.returncode))
    verify(JOURNAL,GPU)
    try:s=json.loads((d/'response.json').read_text())
    except (FileNotFoundError,json.JSONDecodeError):s={}
    if s.get('request_id')==req and s.get('paused') and s.get('frames'):
     assert s['result'] in ['ok','ready','blocked'],s['result'];return s
    time.sleep(.1)
   raise TimeoutError('Native response timeout')
  def capture(label,s):
   write(d/(label+'.json'),s);shutil.copy2(d/s['frames'][-1]['file'],d/(label+'.png'))
  def action(kind,value):
   req=uuid.uuid4().hex;write(d/'command.json',dict(request_id=req,action=kind,value=value));return wait(req)
  try:
   s=wait('');assert math.dist(s['position_cm'],ref['policy']['spawn'])<10
   capture('initial',s);states={'initial':s}
   for k in range(4):
    s=action('turn',90);capture('panorama-'+str(k),s);states['panorama-'+str(k)]=s
   write(d/'result.json',{'status':'captured','states':states,'models_started':0})
   return states
  finally:terminate(ACTIVE);ACTIVE=None

def main():
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,stop)
 result={'status':'waiting_for_build','models_started':0,'pid':os.getpid(),'tasks':{}};write(B/'reference-qa-status.json',result)
 while not (B/'builds/urban/build.json').exists():
  if STOP:return
  time.sleep(10)
 build=json.loads((B/'builds/urban/build.json').read_text())
 assert build['status']=='compiled',build['status']
 refs=[t for t in json.loads((B/'reference-provenance.json').read_text())['tasks'] if t['family']=='urban']
 reservation=Reservation('/home/ec2-user/unreal-production',B/'reference-qa-reservation.json',[0])
 try:
  reservation.acquire();result['status']='native_reference_qa_running';write(B/'reference-qa-status.json',result)
  for ref in refs:
   candidate=stage(ref,Path(build['binary']))
   old=run(ref,'original',ref['profile']['binary']);new=run(ref,'candidate',candidate)
   fields=['actor_state_digest','position_cm','camera_position_cm','yaw_degree','look_degree','map','task_id','simulation_time']
   diffs={label:{key:[old[label].get(key),new[label].get(key)] for key in fields if old[label].get(key)!=new[label].get(key)} for label in old}
   result['tasks'][ref['id']]={'status':'pending_visual_review','state_differences':{k:v for k,v in diffs.items() if v},'candidate_binary':str(candidate)};write(B/'reference-qa-status.json',result)
  result['status']='native_captures_complete_pending_visual_review'
 except Exception as e:result.update(status='needs_attention',error=repr(e));raise
 finally:
  terminate(ACTIVE);reservation.release();result['time']=time.time();write(B/'reference-qa-status.json',result)
if __name__=='__main__':main()
