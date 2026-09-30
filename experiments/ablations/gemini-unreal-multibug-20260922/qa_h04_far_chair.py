"""Diagnose the far chair from the table's outside edge using real native moves."""
from pathlib import Path
import json,signal,time
import qa_composition_routes as q
qa=q.qa;B=q.B;q.GPU=3;q.J=B/'h04-far-chair-reservation.json'
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 ref=next(r for r in json.loads((B/'reference-provenance.json').read_text())['tasks'] if r['id']=='H04')
 state=json.loads((B/'indoor-warmup-v2/status.json').read_text());binary=Path(state['tasks']['H04']['candidate_binary']);assert not state['tasks']['H04']['state_differences']
 route=ref['policy']['route_to_old_spawn']+[[110,-810,231.279],[125,-680,231.279],[125,-350,231.279],[100,-270,231.279],[-32.8,-270,231.279]]
 target=json.loads((B/'draft-compositions/H04/targets.json').read_text())['additions'][1]
 lease=qa.Reservation('/home/ec2-user/unreal-production',q.J,[3]);out={'model_calls':0,'status':'running','tasks':[]}
 try:
  lease.acquire()
  for condition in ['A','AB','ABC']:
   r=q.run(ref,condition,'C',route,target['normal_state']['center'],binary,output_root=B/'h04-far-chair');out['tasks'].append({k:v for k,v in r.items() if k!='actions'});qa.write(B/'h04-far-chair/status.json',out)
  out['status']='captured_pending_review'
 finally:qa.terminate(qa.ACTIVE);lease.release();out['time']=time.time();qa.write(B/'h04-far-chair/status.json',out)
if __name__=='__main__':main()
