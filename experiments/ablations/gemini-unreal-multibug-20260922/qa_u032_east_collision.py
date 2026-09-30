"""Capture fine-grained native collision trajectories; no model calls."""
from pathlib import Path
import json,signal,time
import qa_composition_routes as q
qa=q.qa;B=q.B;q.GPU=2;q.J=B/'u032-east-collision-reservation.json'
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 refs={r['id']:r for r in json.loads((B/'reference-provenance.json').read_text())['tasks']};lease=qa.Reservation('/home/ec2-user/unreal-production',q.J,[2]);out={'status':'running','model_calls':0,'tasks':[]}
 try:
  lease.acquire()
  for tid,label,source,drafts in [('U032','C','','draft-compositions')]:
   ref=refs[tid];r=json.loads((B/source/'composition-rendered-routes'/tid/'A'/label/'result.json').read_text());assert r['status']=='traversed_pending_visual_review'
   prefix=[{'action':a['action']['action'],'value':a['action']['value']} for a in r['actions']]
   t=next(t for t in json.loads((B/drafts/tid/'targets.json').read_text())['additions'] if t['label']==label)
   if tid=='S06':binary=Path(json.loads((B/'subway-warmup-v2/status.json').read_text())['tasks'][tid]['candidate_binary'])
   else:
    original=Path(ref['profile']['binary']);binary=B/('packages/urban-'+tid)/original.relative_to(original.parents[3])
   route=[r['collision_probe']['after'][:2],[200,722.5832999158744]]
   for c in ['A','AB','ABC']:
    r=q.run(ref,c,label,route,t['normal_state']['center'],binary,output_root=B/'u032-east-collision',prefix_actions=prefix,specification_root=B/drafts,collision_step_cm=20);out['tasks'].append({k:v for k,v in r.items() if k!='actions'});qa.write(B/'u032-east-collision/status.json',out)
  out['status']='captured_pending_review'
 finally:qa.terminate(qa.ACTIVE);lease.release();out['time']=time.time();qa.write(B/'u032-east-collision/status.json',out)
if __name__=='__main__':main()
