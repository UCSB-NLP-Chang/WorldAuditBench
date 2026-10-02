from pathlib import Path
import json,sys,copy,math,time,subprocess,os,concurrent.futures
B=Path(__file__).resolve().parent;O=B.parent/'gemini-unreal-multibug-20260922'
sys.path.insert(0,str(O));import qa_composition_routes as q
q.J=B/'qa-reservation.json'
def read(p):return json.loads(p.read_text())
def write(p,v):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2));tmp.replace(p)
S=read(B/'episodes-selection.json');REFS={r['id']:r for r in read(B/'reference-provenance.json')['tasks']};ROUTES=read(B/'routes.json')
def execute(item):
 tid,cond,label,slot=item;q.GPU=slot//2;q.J=B/'qa-reservation.json';ref=copy.deepcopy(REFS[tid]);t=next(t for t in S['tasks'] if t['task_id']==tid and t['condition']=='ABC')
 target=next(x for x in t['targets']['targets'] if x['label']==label);route=ROUTES[tid+'__'+label]
 ref['subcategory']=target['subcategory'];focus=list(ref['policy']['focus'] if label=='A' else target['normal_state']['center'])
 if label!='A' and label in cond:
  sp=read(B/'specs'/tid/(cond+'.json'))['additions'][ord(label)-ord('B')]
  if sp['operation']=='offset':focus=[a+b for a,b in zip(focus,sp['offset'])]
  elif sp['operation']=='scale':focus[2]+=target['normal_state']['extent'][2]*(sp['factor']-1)
 result=q.run(ref,cond,label,[],focus,Path(t['binary_path']),output_root=B/'qa',prefix_actions=route['actions'],specification_root=B/'specs',collision_step_cm=20)
 d=B/'qa/composition-rendered-routes'/tid/cond/label
 if result['status']=='traversed_pending_visual_review':
  deviation=math.dist(result['inspection_position'][:2],route['inspection_position'][:2]);result['route_endpoint_deviation_cm']=deviation
  if deviation>18:result.update(status='needs_resolution',error='Replayed route endpoint drift '+str(deviation))
  inv=read(d/'composition-before.json')['meshes'];anchor=[x for x in inv if x['actor']==REFS[tid]['policy']['target'] or 'auditor_actor:'+REFS[tid]['policy']['target'] in x['tags']];assert len(anchor)==1
  result['anchor_before_injection']=anchor[0]
  if cond!='A':
   applied=read(d/'composition-status.json');assert applied['status']=='applied' and applied['added_count']==len(cond)-1
   assert target['actor'] not in [x['actor'] for x in applied['additions']] if label=='A' else True
  write(d/'result.json',result)
 return {k:v for k,v in result.items() if k not in ['actions','anchor_before_injection']}
def worker(slot,items):
 out=[]
 for tid,cond,label in items:
  if (B/'QA_STOP').exists():break
  try:r=execute((tid,cond,label,slot))
  except Exception as e:r={'id':tid,'condition':cond,'target':label,'status':'needs_resolution','error':repr(e),'models_started':0}
  out.append(r);write(B/f'qa-worker-{slot}.json',out)
 return out
def main():
 assert not (B/'admission.consumed.json').exists()
 assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
 lease=q.qa.Reservation('/home/ec2-user/unreal-production',q.J,[0,1,2,3]);jobs=[]
 for tid in sorted(REFS):
  for cond,labels in [('A','BC'),('AB','AB'),('ABC','ABC')]:
   jobs.extend((tid,cond,l) for l in labels)
 try:
  lease.acquire()
  with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
   futures=[pool.submit(worker,i,jobs[i::8]) for i in range(8)];results=[]
   for f in concurrent.futures.as_completed(futures):results+=f.result()
 finally:lease.release()
 write(B/'native-qa-status.json',{'time':time.time(),'model_calls':0,'expected':147,'captured':len(results),'traversed':sum(r['status']=='traversed_pending_visual_review' for r in results),'status':'awaiting_resolution_or_assistant_visual_review','results':results})
if __name__=='__main__':main()
