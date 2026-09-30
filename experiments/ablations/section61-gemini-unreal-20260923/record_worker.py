from pathlib import Path
import os,sys,json,time,signal,hashlib
B=Path(__file__).resolve().parent;C=B/'code';P=B/sys.argv[1];gpu=int(sys.argv[2]);sys.path.insert(0,str(C))
os.environ.update(P2P_ROOT='/home/ec2-user/tools/open-p2p',P2P_PY='/home/ec2-user/tools/open-p2p/.venv/bin/python',GA_ICLR=str(C),HF_HOME='/home/ec2-user/.cache/huggingface',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',VLA_UE_STRICT_START='1',VLA_UE_MAXFPS='20')
from harness import vla_ue as v
from batch_reservation import verify
plan=json.loads((P/'recording-plan.json').read_text());tasks,profiles=v.load_catalog(P/'profiles.json');ids=sorted(tasks)[gpu::4]
original=v.TaskBackend.__init__
def init(self,binary,map_name,task,arguments,root,**kw):return original(self,binary,map_name,task,list(arguments)+['-graphicsadapter='+str(gpu)],root,**kw)
v.TaskBackend.__init__=init
state=P/'ue-state'/str(gpu);state.mkdir(parents=True,exist_ok=True)
def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2)+'\n');tmp.replace(p)
def stopped():return (B/'STOP.json').exists() or (P/'STOP.json').exists()
def sig(*_):raise KeyboardInterrupt()
for s in [signal.SIGTERM,signal.SIGINT]:signal.signal(s,sig)
p2p=None
try:
 verify(P/'reservation.json',gpu)
 checked=set()
 for profile in profiles.values():
  binary=Path(profile['binary'])
  if str(binary) in checked:continue
  h=hashlib.sha256()
  with binary.open('rb') as f:
   for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
  assert h.hexdigest()==profile['build_sha256']
  checked.add(str(binary))
 write(P/f'worker-{gpu}.json',{'status':'loading_explorer','pid':os.getpid(),'time':time.time(),'gpu':gpu})
 p2p=v.P2PClient(gpu=str(gpu),size='1200M',eager=True)
 for tid in ids:
  if stopped():break
  verify(P/'reservation.json',gpu);out=P/'recordings'/tid;assert not out.exists()
  write(P/f'worker-{gpu}.json',{'status':'recording','task':tid,'pid':os.getpid(),'started_at':time.time(),'gpu':gpu})
  v.run_episode(p2p,tid,tasks,profiles,plan['ticks'],50,10,plan['text'],out,state,recover=True,idle_nudge=40)
  m=json.loads((out/'meta.json').read_text());assert m['ticks']==plan['ticks'] and len(m['frames'])==plan['ticks']//10 and m['start_check']['ready'] and m['start_check']['dist_cm']<=30 and m['start_check']['dyaw']<=2
  assert m['build_sha256']==profiles[tid]['build_sha256'] and m['policy']==profiles[tid]['policy']
  assert (out/'video.mp4').is_file()
  # Deliver video-decoded frames, exactly as in the original VLA replay exports.
  dest=P/'replay-recordings'/tid;dest.mkdir(parents=True)
  for name in ['meta.json','poses.jsonl','video.mp4']:(dest/name).symlink_to(out/name)
  import importlib.util
  spec=importlib.util.spec_from_file_location('restore',B/'vla_frames_from_video.py');restore=importlib.util.module_from_spec(spec);spec.loader.exec_module(restore)
  assert restore.restore(dest)==f"restored {plan['ticks']//10}"
  write(out/'verification.json',{'passed':True,'time':time.time(),'gpu':gpu,'frames':len(m['frames']),'video_sha256':hashlib.sha256((out/'video.mp4').read_bytes()).hexdigest()})
 write(P/f'worker-{gpu}.json',{'status':'stopped' if stopped() else 'completed','pid':os.getpid(),'time':time.time(),'gpu':gpu})
except BaseException as e:
 write(P/'STOP.json',{'reason':repr(e),'gpu':gpu,'time':time.time()});raise
finally:
 if p2p:p2p.close()
