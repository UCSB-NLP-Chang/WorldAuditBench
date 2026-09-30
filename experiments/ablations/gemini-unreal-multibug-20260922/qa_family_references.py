"""Capture historical-vs-candidate A-only states, without any model calls."""
from pathlib import Path
import json,os,signal,time
import qa_urban_reference as qa
B=qa.B
qa.GPU=1
qa.JOURNAL=B/'family-reference-qa-reservation.json'
def main():
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,qa.stop)
 result={'status':'waiting_for_build','models_started':0,'pid':os.getpid(),'tasks':{}}
 target=B/'family-reference-qa-status.json';qa.write(target,result)
 refs=[t for t in json.loads((B/'reference-provenance.json').read_text())['tasks'] if t['family']!='urban']
 reservation=None
 try:
  for ref in refs:
   path=B/'builds'/ref['family']/'build.json'
   while not path.exists():
    if qa.STOP:raise InterruptedError('QA interrupted')
    time.sleep(5)
   build=json.loads(path.read_text())
   if build['status']!='compiled':
    result['tasks'][ref['id']]={'status':'build_failed'};qa.write(target,result);continue
   if reservation is None:
    reservation=qa.Reservation('/home/ec2-user/unreal-production',qa.JOURNAL,[qa.GPU]);reservation.acquire()
   result['status']='native_reference_qa_running';result['active']=ref['id'];qa.write(target,result)
   candidate=qa.stage(ref,Path(build['binary']))
   old=qa.run(ref,'original',ref['profile']['binary']);new=qa.run(ref,'candidate',candidate)
   fields=['actor_state_digest','position_cm','camera_position_cm','yaw_degree','look_degree','map','task_id','simulation_time']
   differences={label:{key:[old[label].get(key),new[label].get(key)] for key in fields if old[label].get(key)!=new[label].get(key)} for label in old}
   result['tasks'][ref['id']]={'status':'pending_visual_review','state_differences':{k:v for k,v in differences.items() if v},'candidate_binary':str(candidate)};qa.write(target,result)
  result['status']='native_captures_complete_pending_visual_review'
 except Exception as e:result.update(status='needs_attention',error=repr(e));raise
 finally:
  qa.terminate(qa.ACTIVE)
  if reservation:reservation.release()
  result['time']=time.time();qa.write(target,result)
if __name__=='__main__':main()
