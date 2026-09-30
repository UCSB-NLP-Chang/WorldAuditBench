"""Check the timing repair against preserved original native captures, no model calls."""
from pathlib import Path
import json,signal,time
import qa_urban_reference as qa
B=qa.B
qa.B=B/'subway-warmup-v2';qa.GPU=2;qa.JOURNAL=B/'subway-warmup-v2-reservation.json'
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 state={'status':'waiting_for_build','model_calls':0,'tasks':{}};qa.write(qa.B/'status.json',state)
 while True:
  p=B/'builds/subway/warmup-v2/status.json'
  if p.exists():
   build=json.loads(p.read_text())
   if build['status']!='compiling':break
  if qa.STOP:raise InterruptedError('Stopped before native QA')
  time.sleep(5)
 assert build['status']=='compiled_pending_equivalence',build['status']
 lease=qa.Reservation('/home/ec2-user/unreal-production',qa.JOURNAL,[2])
 try:
  lease.acquire()
  refs=[r for r in json.loads((B/'reference-provenance.json').read_text())['tasks'] if r['family']=='subway']
  for ref in refs:
   tid=ref['id'];binary=qa.stage(ref,Path(build['binary']));new=qa.run(ref,'candidate',binary)
   old=json.loads((B/'qa-reference'/tid/'original/result.json').read_text())['states']
   fields=['actor_state_digest','position_cm','camera_position_cm','yaw_degree','look_degree','map','task_id','simulation_time','world_time']
   diffs={label:{k:[old[label].get(k),new[label].get(k)] for k in fields if old[label].get(k)!=new[label].get(k)} for label in old}
   diffs={k:v for k,v in diffs.items() if v}
   state['tasks'][tid]={'state_differences':diffs,'candidate_binary':str(binary),'status':'state_equivalent_pending_visual' if not diffs else 'needs_resolution'}
   qa.write(qa.B/'status.json',state)
  state['status']='state_equivalent_pending_visual' if all(not v['state_differences'] for v in state['tasks'].values()) else 'needs_resolution'
 finally:
  qa.terminate(qa.ACTIVE);lease.release();state['time']=time.time();qa.write(qa.B/'status.json',state)
if __name__=='__main__':main()
