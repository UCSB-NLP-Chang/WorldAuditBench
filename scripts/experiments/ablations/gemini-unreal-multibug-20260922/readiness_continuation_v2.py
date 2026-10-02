"""Resume35 first model executions after a reviewed pre-frame startup race; no model retry."""
from pathlib import Path
import importlib.util,json,time,fcntl,signal,threading,copy
from concurrent.futures import ThreadPoolExecutor
from readiness_continuation_guard_v2 import consume,validate
B=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('corrected_coordinator',B/'coordinator_readiness_v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def main():
 lock=(B/'coordinator.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 a,old,s=validate();archive=B/a['archive_directory'];archive.mkdir(exist_ok=False)
 (B/'reservation.json').rename(archive/'reservation.json')
 m.STATE=copy.deepcopy(old['tasks'])
 by={t['id']:t for t in s['tasks']}
 for tid in a['dispatch_order']:
  m.STATE[tid]={'status':'queued','family':by[tid]['family'],'protocol_group':'category-icl-multibug','next_attempt':a['next_attempt'][tid],'prior_native_only_failure':a['next_attempt'][tid]==2};m.Q.put(by[tid])
 def worker(slot):
  if m.STOP.wait(slot*2):return
  while not m.STOP.is_set() and not m.DRAIN.is_set():
   if (B/'SYSTEM_STOP').exists():m.STOP.set();return
   if (B/'DRAIN.json').exists():m.DRAIN.set();return
   try:t=m.Q.get_nowait()
   except m.queue.Empty:return
   try:m.attempt(t,slot,a['next_attempt'][t['id']])
   except Exception as e:m.save(t['id'],status='failed',error=repr(e))
   finally:m.control_after_failure(t['id']);m.Q.task_done()
 lease=m.Reservation(Path('/home/ec2-user/unreal-production'),B/'reservation.json',[0,1,2,3])
 try:
  lease.acquire()
  consume()
  for name in ['progress.json','DRAIN.json','batch.finished','batch.started']:
   p=B/name;assert p.exists();p.rename(archive/name)
  with (B/'batch.started').open('x') as f:f.write(str(__import__('os').getpid()))
  for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,lambda *_:m.STOP.set())
  threading.Thread(target=m.heartbeat,daemon=True).start();m.save(a['dispatch_order'][0])
  with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(worker,range(8)))
 finally:lease.release()
 (B/'batch.finished').write_text(json.dumps({'time':time.time(),'completed':sum(x['status']=='completed' for x in m.STATE.values()),'failed':sum(x['status']=='failed' for x in m.STATE.values()),'eligible':42,'stopped':m.STOP.is_set(),'drained':m.DRAIN.is_set(),'phase':'reviewed-readiness-continuation'},indent=2)+'\n')
if __name__=='__main__':main()
