"""Execute only the five authorized Section 6.1 conditions, in priority order."""
from pathlib import Path
import sys,os,json,time,subprocess,signal,fcntl,hashlib
B=Path(__file__).resolve().parent;PY=str(B/'code/out/native-agents/venv/bin/python');CURRENT=None;stop_requested=False
PHASES=['01-vla-noicl','02-vla-near','03-vlm-60steps','04-vla-half','05-vla-onehalf']
def read(p):return json.loads(p.read_text())
def write(p,v):
 temp=p.with_suffix('.tmp');temp.write_text(json.dumps(v,indent=2)+'\n');temp.replace(p)
def status(phase,stage,**kw):write(B/'sequence-status.json',{'time':time.time(),'pid':os.getpid(),'phase':phase,'stage':stage,**kw})
def stopping(phase):return stop_requested or any(p.exists() for p in [B/'STOP.json',B/phase/'STOP.json',B/phase/'SYSTEM_STOP.json'])
def terminate(p):
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=60)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
def run(phase,stage,args):
 global CURRENT
 assert not stopping(phase),'STOP active'
 status(phase,stage)
 with (B/phase/(stage+'.log')).open('x') as log:
  CURRENT=subprocess.Popen(args,cwd=B,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  status(phase,stage,child_pid=CURRENT.pid)
  while CURRENT.poll() is None:
   if stopping(phase):terminate(CURRENT);raise RuntimeError('STOP active')
   time.sleep(5)
  assert CURRENT.returncode==0,(phase,stage,'exit',CURRENT.returncode)
 CURRENT=None

def validate_admission():
 review=read(B/'sequence-admission.json');assert review['approved']
 for n,h in review['files'].items():assert hashlib.sha256((B/n).read_bytes()).hexdigest()==h,n
 assert read(B/'recording-preflight.json')['passed']
 assert read(B/'explorer-preflight.json')['passed']
 assert read(B/'native-preflight.json')['passed']
 assert read(B/'03-vlm-60steps/preflight.json')['passed']
 assert set(read(B/'03-vlm-60steps/selection.json')['sampled_ids_sha256']) # source cohort hash present
 assert len(read(B/'tasks.json'))==126

def main():
 validate_admission()
 lock=(B/'sequence.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 with (B/'sequence-admission.consumed').open('x') as f:f.write(str(os.getpid()))
 phase=PHASES[0];pid=int((B/'replay.pid').read_text());status(phase,'waiting_for_active_replay',child_pid=pid)
 while True:
  if stopping(phase):raise RuntimeError('Replay STOP active')
  cmd=Path('/proc')/str(pid)/'cmdline'
  if not cmd.exists() or not cmd.read_bytes():break
  assert b'replay_runner.py' in cmd.read_bytes(),'PID no longer belongs to admitted replay'
  time.sleep(5)
 finished=read(B/phase/'finished.json')
 assert finished['time']>(B/phase/'verified-resume-admission.consumed').stat().st_mtime and not finished['stopped']
 run(phase,'finalize',[PY,str(B/'finalize_phase.py'),phase])
 for phase in PHASES[1:]:
  validate_admission()
  if phase=='03-vlm-60steps':
   assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPUs not idle'
   run(phase,'native-audit',[PY,str(B/phase/'coordinator.py')])
  else:
   run(phase,'record',[PY,str(B/'record_controller.py'),phase])
   assert read(B/phase/'recordings.finished.json')['verified']==126
   run(phase,'replay-preflight',[PY,str(B/'replay_icl_runner.py'),'preflight',phase])
   assert read(B/phase/'replay-preflight.json')['passed']
   run(phase,'replay',[PY,str(B/'replay_icl_runner.py'),'run',phase])
  run(phase,'finalize',[PY,str(B/'finalize_phase.py'),phase])
 write(B/'all-experiments.finished.json',{'time':time.time(),'phases':{p:read(B/p/'verified.finished.json') for p in PHASES}})
 status('all','completed')
def signal_stop(*_):
 global stop_requested
 stop_requested=True
for s in [signal.SIGTERM,signal.SIGINT]:signal.signal(s,signal_stop)
if __name__=='__main__':
 try:main()
 except BaseException as e:
  if CURRENT:terminate(CURRENT)
  status('sequence','stopped',error=repr(e));raise
