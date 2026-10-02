"""Approach the waste bin from the verified alley path, without teleporting."""
from pathlib import Path
import json,signal,time
import qa_composition_routes as q
qa=q.qa;B=q.B;q.GPU=3;q.J=B/'u032-reverse-collision-reservation.json'
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 ref=next(r for r in json.loads((B/'reference-provenance.json').read_text())['tasks'] if r['id']=='U032')
 original=Path(ref['profile']['binary']);binary=B/'packages/urban-U032'/original.relative_to(original.parents[3])
 prefix=json.loads((B/'composition-rendered-routes/U032/A/B/result.json').read_text());assert prefix['status']=='traversed_pending_visual_review'
 actions=[{'action':r['action']['action'],'value':r['action']['value']} for r in prefix['actions']]
 target=json.loads((B/'draft-compositions/U032/targets.json').read_text())['additions'][0]
 lease=qa.Reservation('/home/ec2-user/unreal-production',q.J,[3]);out={'model_calls':0,'status':'running','tasks':[]}
 try:
  lease.acquire()
  for condition in ['A','AB','ABC']:
   r=q.run(ref,condition,'B',[],target['normal_state']['center'],binary,output_root=B/'u032-reverse-collision',prefix_actions=actions);out['tasks'].append({k:v for k,v in r.items() if k!='actions'});qa.write(B/'u032-reverse-collision/status.json',out)
  out['status']='captured_pending_review'
 finally:qa.terminate(qa.ACTIVE);lease.release();out['time']=time.time();qa.write(B/'u032-reverse-collision/status.json',out)
if __name__=='__main__':main()
