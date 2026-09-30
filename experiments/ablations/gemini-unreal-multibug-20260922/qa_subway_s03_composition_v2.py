"""Native rendered composition QA on reference-equivalent Subway v2; no model calls."""
from pathlib import Path
import json,signal,time
import qa_composition_routes as routes
qa=routes.qa;B=routes.B
routes.J=B/'subway-s03-composition-v2-reservation.json'
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 validated=json.loads((B/'subway-warmup-v2/status.json').read_text());assert validated['status']=='state_equivalent_pending_visual'
 refs={r['id']:r for r in json.loads((B/'reference-provenance.json').read_text())['tasks']}
 ref=refs['S03'];binary=Path(validated['tasks']['S03']['candidate_binary'])
 targets=json.loads((B/'draft-compositions/S03/targets.json').read_text())['additions']
 a=json.loads((B.parent/'gemini-unreal-distance-ablation-20260921/route-preparation/S03/result.json').read_text());assert a['status']=='candidate_geometry_prepared'
 paths={'A':a['route']};focus={'A':ref['policy']['focus']}
 for t in targets:
  plan=json.loads((B/'composition-route-plans/S03'/(t['label']+'-grid100' if t['label']=='C' else t['label'])/'result.json').read_text());assert plan['status']=='geometry_candidate_pending_rendered_traversal';paths[t['label']]=plan['route'];focus[t['label']]=t['normal_state']['center']
 lease=qa.Reservation('/home/ec2-user/unreal-production',routes.J,[0]);out={'models_started':0,'status':'running','tasks':[]}
 try:
  lease.acquire()
  for condition in ['A','AB','ABC']:
   for label in ['A','B','C']:
    f=list(focus[label])
    if label!='A' and label in condition:
     target=next(t for t in targets if t['label']==label);f[2]+=target['normal_state']['extent'][2]*2
    result=routes.run(ref,condition,label,paths[label],f,binary,output_root=B/'subway-s03-composition-v2');out['tasks'].append({k:v for k,v in result.items() if k!='actions'});qa.write(B/'subway-s03-composition-v2/status.json',out)
  out['status']='captured_pending_review'
 finally:
  qa.terminate(qa.ACTIVE);lease.release();out['time']=time.time();qa.write(B/'subway-s03-composition-v2/status.json',out)
if __name__=='__main__':main()
