"""Render all matched controls for prepared S06 and Indoor additions; no model calls."""
from pathlib import Path
import json,signal,time
import qa_composition_routes as q
import plan_addition_routes as planner
qa=q.qa;B=q.B;q.GPU=1;q.J=B/'medieval-rural-composition-reservation.json'
def main():
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,qa.stop)
 refs={r['id']:r for r in json.loads((B/'reference-provenance.json').read_text())['tasks']};out={'status':'running','model_calls':0,'tasks':[]};lease=None
 try:
  for tid in ['MV01','MV03','MV11','R01','R07','R13']:
   ref=refs[tid];targets=json.loads((B/'draft-compositions'/tid/'targets.json').read_text())['additions'];plans={}
   for t in targets:
    plan=planner.plan(ref,t,output_root=B/'medieval-rural-route-plans')
    if plan['status']=='needs_resolution':plan=planner.plan(ref,t,grid=100,output_root=B/'medieval-rural-route-plans')
    plans[t['label']]=plan
   if any(p['status']!='geometry_candidate_pending_rendered_traversal' for p in plans.values()):
    out['tasks'].append({'id':tid,'status':'geometry_needs_resolution','model_calls':0});qa.write(B/'medieval-rural-composition/status.json',out);continue
   while True:
    p=B/(ref['family']+'-warmup-v2/status.json')
    if p.exists():
     verified=json.loads(p.read_text())
     if tid in verified.get('tasks',{}):break
    if qa.STOP:raise InterruptedError('QA stopped')
    time.sleep(3)
   item=verified['tasks'][tid]
   if item['state_differences']:
    out['tasks'].append({'id':tid,'status':'reference_needs_resolution','model_calls':0});qa.write(B/'medieval-rural-composition/status.json',out);continue
   if lease is None:lease=qa.Reservation('/home/ec2-user/unreal-production',q.J,[1]);lease.acquire()
   original=json.loads((B.parent/'gemini-unreal-distance-ablation-20260921/route-preparation'/tid/'result.json').read_text());assert original['status']=='candidate_geometry_prepared'
   paths={'A':original['route'],**{k:v['route'] for k,v in plans.items()}};focus={'A':ref['policy']['focus'],**{t['label']:t['normal_state']['center'] for t in targets}}
   for condition in ['A','AB','ABC']:
    spec=json.loads((B/'draft-compositions'/tid/(('ABC' if condition=='A' else condition)+'.json')).read_text())
    for label in 'ABC':
     f=list(focus[label])
     if label!='A' and label in condition:
      t=next(t for t in targets if t['label']==label);s=spec['additions'][ord(label)-ord('B')]
      if s['operation']=='offset':f=[x+y for x,y in zip(f,s['offset'])]
      elif s['operation']=='scale':f[2]+=t['normal_state']['extent'][2]*(s['factor']-1)
     r=q.run(ref,condition,label,paths[label],f,Path(item['candidate_binary']),output_root=B/'medieval-rural-composition',specification_root=B/'draft-compositions');out['tasks'].append({k:v for k,v in r.items() if k!='actions'});qa.write(B/'medieval-rural-composition/status.json',out)
  out['status']='captured_pending_review'
 finally:
  qa.terminate(qa.ACTIVE)
  if lease:lease.release()
  out['time']=time.time();qa.write(B/'medieval-rural-composition/status.json',out)
if __name__=='__main__':main()
