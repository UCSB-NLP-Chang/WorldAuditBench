"""Render representative frozen starts with one temporary idle Review GPU lease."""
import ast,atexit,hashlib,json,os,pathlib,signal,sqlite3,subprocess,sys,time,uuid
from pathlib import Path
root=Path(sys.argv[1]);policy=root/'policy.json'
while not (root/'validation.json').exists():time.sleep(1)
qa=json.loads((root/'validation.json').read_text());assert qa['status']=='PASS'
source=ast.parse((root/'remote_unreal.py').read_text());node=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='IdleReviewGPU');exec(compile(ast.Module(body=[node],type_ignores=[]),'native-gpu-reservation','exec'))
rt=json.loads(Path('/home/ec2-user/unreal-production/audit/runtime.json').read_text());sc=json.loads(Path(rt['scheduler_config']).read_text());lease=IdleReviewGPU(sc['database'],rt['slot_gpus'],3,root/'render-gpu-reservation.json');lease.acquire()
rows={r['id']:r for r in json.loads((root/'inventory.json').read_text())};p=json.loads(policy.read_text());proc=None

def cleanup(*args):
 global proc
 if proc is not None and proc.poll() is None:
  os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=7)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
 lease.release()
 if args:raise SystemExit(2)
signal.signal(signal.SIGTERM,cleanup);signal.signal(signal.SIGHUP,cleanup);signal.signal(signal.SIGINT,cleanup)
results=[]
try:
 for tid in ['S01','S03','H09','A09','I05','R13','MV18']:
  row=rows[tid];e=p['tasks'][tid];d=root/'renders'/tid;d.mkdir(parents=True,exist_ok=True)
  cmd=[row['profile']['binary'],e['map']+'?Task='+tid,'-RenderOffscreen','-windowed','-ResX=960','-ResY=540','-nosound','-unattended','-AuditorServe','-AuditorIPC='+str(d),'-AuditorExplorationPolicy='+str(policy),'-AuditorExplorationTask='+tid,'-AuditorExplorationReport='+str(d/'native.json'),'-abslog='+str(d/'native.log'),'-UserDir='+str(d/'userdata'),'-NoSaveConfig','-graphicsadapter=3',*row['profile']['game_args']]
  with (d/'stdout.log').open('w') as log:
   proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);start=time.monotonic()
   try:
    while not (d/'observation.png').exists():
     assert lease.owned(),'GPU reservation lost';assert proc.poll() is None,'Native process exited';assert time.monotonic()-start<100,'Render timeout'
     m=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_gpu_memory','--format=csv,noheader,nounits'],text=True)
     for line in m.splitlines():
      fields=[x.strip() for x in line.split(',')]
      if len(fields)==2 and fields[0]==str(proc.pid):assert int(fields[1])<6000,'Private renderer exceeds 6000 MiB'
     time.sleep(.5)
    r=json.loads((d/'native.json').read_text());assert r['status']=='validated' and r['id']==tid
    out={'id':tid,'status':'PASS','image':str(d/'observation.png'),'spawn':r['spawn']}
   except Exception as exc:out={'id':tid,'status':'FAIL','error':str(exc)}
   finally:
    if proc.poll() is None:
     os.killpg(proc.pid,signal.SIGTERM)
     try:proc.wait(timeout=7)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
  results.append(out);print(json.dumps(out),flush=True)
finally:cleanup()
(root/'render-validation.json').write_text(json.dumps({'status':'PASS' if all(r['status']=='PASS' for r in results) else 'FAIL','policy_sha256':hashlib.sha256(policy.read_bytes()).hexdigest(),'tasks':results,'urban_note':'Urban validated with native collision/frozen-spawn checks; no AuditorServe image capture available.'},indent=2))
