"""Wait for all 50 ICL runs + grades, then reserve GPU0 for native route QA only."""
from pathlib import Path
import fcntl,json,os,signal,subprocess,sys,time
B=Path(__file__).resolve().parent;C=B.parent/'gemini-unreal-icl-ablation-20260921'
sys.path.insert(0,str(C/'code'))
from batch_reservation import Reservation
STOP=False

def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return {}
def write(p,j):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(j,indent=2));tmp.replace(p)
def state(status,**kw):
 write(B/'qa-handoff.json',dict(status=status,updated_at=time.time(),pid=os.getpid(),model_runs_started=0,**kw))
def gate():
 p=read(C/'progress.json');j=read(C/'judge/results.json');r=read(C/'reservation.json')
 complete=sum(v.get('status')=='completed' for v in p.get('tasks',{}).values())
 scored={t['id'] for t in j.get('tasks',[]) if t.get('judge_status')=='completed' and t.get('judge',{}).get('score') in [0,1]}
 expected={t['id'] for t in read(B/'selection.json')['tasks']}
 muse=read(B.parent/'muse-threejs-20260921/USER_PAUSE.json');muse_r=read(B.parent/'muse-threejs-20260921/reservation.json')
 ready=muse.get('state')=='paused' and muse_r.get('status')=='released' and complete==50 and len(p.get('tasks',{}))==50 and scored==expected and (C/'batch.finished').exists() and r.get('status')=='released'
 return ready,dict(icl_completed=complete,icl_graded=len(scored),icl_reservation=r.get('status'))
def stop(*_):
 global STOP
 STOP=True
if __name__=='__main__':
 lock=(B/'qa-handoff.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,stop)
 reservation=None;proc=None
 try:
  while not STOP:
   ready,detail=gate()
   state('waiting_for_icl_completion',**detail)
   if ready:break
   time.sleep(15)
  if STOP:raise RuntimeError('QA handoff stopped before admission')
  if read(B/'route-preparation-progress.json').get('candidate_geometry_prepared')!=50:raise RuntimeError('Candidate geometry is incomplete')
  if (B/'rendered-qa.finished').exists():raise RuntimeError('Existing QA finish marker: review it rather than repeating')
  reservation=Reservation('/home/ec2-user/unreal-production',B/'qa-reservation.json',[0,1,2,3]);reservation.acquire()
  with (B/'rendered-qa.log').open('a') as log:
   proc=subprocess.Popen([sys.executable,'-u',str(B/'qa_native_routes.py')],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   while proc.poll() is None and not STOP:
    state('native_route_qa_running',qa_pid=proc.pid,ready_for_model=False);time.sleep(10)
   if STOP:proc.send_signal(signal.SIGTERM)
   try:rc=proc.wait(timeout=45)
   except subprocess.TimeoutExpired:raise RuntimeError('QA shutdown did not finish: keeping reservation for inspection')
   state('native_qa_done_requires_visual_and_trigger_review' if rc==0 else 'needs_attention',exit_code=rc,ready_for_model=False)
 except Exception as exc:
  state('needs_attention',error=str(exc),ready_for_model=False);print(repr(exc),flush=True)
 finally:
  # Child waits and terminates all of its native process groups before normal exit.
  if reservation is not None and (proc is None or proc.poll() is not None):reservation.release()
