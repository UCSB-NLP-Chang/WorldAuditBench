"""Capture fine-grained native collision trajectories; no model calls."""
from pathlib import Path
import json,signal,time
import qa_composition_routes as q
qa=q.qa;B=q.B;q.GPU=1;q.J=B/'rural-ground-views-reservation.json'
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 refs={r['id']:r for r in json.loads((B/'reference-provenance.json').read_text())['tasks']};lease=qa.Reservation('/home/ec2-user/unreal-production',q.J,[1]);out={'status':'running','model_calls':0,'tasks':[]}
 try:
  lease.acquire()
  for tid,label,source,drafts in [(tid,l,'medieval-rural-composition','draft-compositions') for tid in ['R01','R07','R13'] for l in ['B','C']]:
   ref=refs[tid];r=json.loads((B/source/'composition-rendered-routes'/tid/'A'/label/'result.json').read_text());assert r['status']=='traversed_pending_visual_review'
   prefix=[{'action':a['action']['action'],'value':a['action']['value']} for a in r['actions']]
   t=next(t for t in json.loads((B/drafts/tid/'targets.json').read_text())['additions'] if t['label']==label)
   if tid.startswith('R'):binary=Path(json.loads((B/'rural-warmup-v2/status.json').read_text())['tasks'][tid]['candidate_binary'])
   else:
    original=Path(ref['profile']['binary']);binary=B/('packages/urban-'+tid)/original.relative_to(original.parents[3])
   for c in ['A','ABC']:
    focus=list(t['normal_state']['center']);focus[2]-=t['normal_state']['extent'][2]
    r=q.run(ref,c,label,[],focus,binary,output_root=B/'rural-ground-views',prefix_actions=prefix,specification_root=B/drafts,collision_step_cm=20);out['tasks'].append({k:v for k,v in r.items() if k!='actions'});qa.write(B/'rural-ground-views/status.json',out)
  out['status']='captured_pending_review'
 finally:qa.terminate(qa.ACTIVE);lease.release();out['time']=time.time();qa.write(B/'rural-ground-views/status.json',out)
if __name__=='__main__':main()
