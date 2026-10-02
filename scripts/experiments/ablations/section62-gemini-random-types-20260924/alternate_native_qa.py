from pathlib import Path
import copy,json,subprocess,concurrent.futures,time
import native_qa as q
B=Path(__file__).resolve().parent;J=B/'qa-alternate-v2-reservation.json'
def run(item):
 tid,cond,label,gpu=item;q.q.GPU=gpu;q.q.J=J;ref=copy.deepcopy(q.REFS[tid]);t=next(t for t in q.S['tasks'] if t['id']=='ABC__'+tid);target=next(x for x in t['targets']['targets'] if x['label']==label);focus=list(target['normal_state']['center']);ref['subcategory']=target['subcategory']
 if cond!='A':
  sp=q.read(B/'specs'/tid/(cond+'.json'))['additions'][ord(label)-ord('B')]
  if sp['operation']=='scale':focus[2]+=target['normal_state']['extent'][2]*(sp['factor']-1)
  elif sp['operation']=='offset':focus=[a+b for a,b in zip(focus,sp['offset'])]
 route_key='H03__C' if tid=='H03' else 'U032__A'
 return q.q.run(ref,cond,label,[],focus,Path(t['binary_path']),output_root=B/'qa-alternate-v2',prefix_actions=q.ROUTES[route_key]['actions'],specification_root=B/'specs')
assert (B/'qa-final-result.json').exists() and not (B/'admission.consumed.json').exists()
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
lease=q.q.qa.Reservation('/home/ec2-user/unreal-production',J,[0,1,2,3])
try:
 lease.acquire()
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(run,[('H03','A','B',0),('H03','AB','B',1),('H03','ABC','B',2),('U032','ABC','C',3)]))
finally:lease.release()
(B/'qa-alternate-v2-result.json').write_text(json.dumps({'time':time.time(),'model_calls':0,'results':rows},indent=2)+'\n')
