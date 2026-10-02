"""Incremental full-cohort native QA; never starts or approves model runs."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import fcntl,json,os,sys,time,signal,shutil
B=Path(__file__).resolve().parent
sys.path.insert(0,str(B));import qa_native_routes as route
from batch_reservation import Reservation
S=json.loads((B/'selection.json').read_text());EXPECTED={t['id'] for t in S['tasks']};STOP=route.STOP

def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return {}
def state(status,**kw):route.write(B/'full126-qa-handoff.json',dict(updated_at=time.time(),pid=os.getpid(),status=status,model_runs_started=0,**kw))
def archive_control(names):
 d=B/('full126-qa-control-'+str(time.time_ns()));d.mkdir()
 for name in names:
  p=B/name
  if p.exists():
   if 'reservation' in name:assert read(p).get('status')=='released'
   shutil.move(p,d/name)
 return d

def work(slot):
 while not STOP.is_set():
  try:t,arm=QUEUE.get(timeout=1)
  except __import__('queue').Empty:
   if DONE.is_set():return
   continue
  try:
   r=route.run_arm(t,arm,slot)
   if not r['status'].startswith('route_passed'):state('route_needs_review',task=t['id'],arm=arm,error=r.get('error'))
  except Exception as exc:
   r=dict(id=t['id'],arm=arm,status='needs_resolution',error=repr(exc),ready_for_model=False);d=B/'rendered-route-qa'/t['id']/arm;d.mkdir(parents=True,exist_ok=True);route.write(d/'result.json',r)
   with route.LOCK:route.RESULTS[t['id']+'/'+arm]=r
  finally:QUEUE.task_done()

if __name__=='__main__':
 import queue,threading
 QUEUE=queue.Queue();DONE=threading.Event();lock=(B/'rendered-qa.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,lambda *_:STOP.set())
 budget=B.parent/'gemini-unreal-budget20-20260921';assert read(budget/'judge/results.json')['graded']==126 and read(budget/'reservation.json')['status']=='released' and (budget/'batch.finished').exists()
 assert read(B.parent/'muse-threejs-20260921/USER_PAUSE.json')['state']=='paused'
 assert not (B/'batch.started').exists()
 archive_control(['qa-reservation.json','rendered-qa.finished'])
 for p in (B/'rendered-route-qa').glob('*/*/result.json'):
  r=read(p);route.RESULTS[r['id']+'/'+r['arm']]={k:v for k,v in r.items() if k!='actions'}
 reservation=Reservation('/home/ec2-user/unreal-production',B/'qa-reservation.json',[0,1,2,3]);reservation.acquire();submitted=set(route.RESULTS)
 try:
  with ThreadPoolExecutor(max_workers=8) as pool:
   workers=[pool.submit(work,i) for i in range(8)]
   while not STOP.is_set():
    geo={tid:read(B/'route-preparation'/tid/'result.json') for tid in EXPECTED}
    for t in S['tasks']:
     if geo[t['id']].get('status')!='candidate_geometry_prepared':continue
     for arm in ['far','near','medium']:
      key=t['id']+'/'+arm
      if key not in submitted:submitted.add(key);QUEUE.put((t,arm))
    all_terminal=all(x.get('status') in ['candidate_geometry_prepared','needs_route_resolution'] for x in geo.values())
    state('rendered_routes_running',geometry_ready=sum(x.get('status')=='candidate_geometry_prepared' for x in geo.values()),route_results=len(route.RESULTS),route_total=378,queued=QUEUE.qsize(),ready_for_model=False)
    if all_terminal:break
    time.sleep(5)
   DONE.set()
   for w in workers:w.result()
  results=list(route.RESULTS.values());route.write(B/'rendered-qa.finished',dict(time=time.time(),processed=len(results),expected=378,stopped=STOP.is_set(),ready_for_model=False))
  state('rendered_routes_done_needs_visual_review',processed=len(results),passed=sum(x.get('status','').startswith('route_passed') for x in results),expected=378,ready_for_model=False)
 finally:reservation.release()
