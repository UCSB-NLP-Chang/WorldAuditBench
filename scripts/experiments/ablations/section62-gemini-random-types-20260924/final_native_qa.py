from pathlib import Path
import json,time,subprocess,concurrent.futures,copy,math,os
B=Path(__file__).resolve().parent
while not (B/'qa-repair-result.json').exists():
 if (B/'QA_STOP').exists():raise RuntimeError('QA stopped')
 time.sleep(5)
import native_qa as q
assert not (B/'admission.consumed.json').exists()
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
J=B/'qa-final-reservation.json';lease=q.q.qa.Reservation('/home/ec2-user/unreal-production',J,[0,1,2,3]);verify=q.q.qa.verify

def worker(slot,jobs):
 q.q.qa.verify=lambda journal,gpu:verify(J,gpu)
 rows=[]
 for job in jobs:
  if (B/'QA_STOP').exists():raise RuntimeError('QA stopped')
  tid,cond,label=job
  if tid=='S06':r=q.execute((tid,cond,label,slot))
  else:
   q.q.GPU=slot//2;q.q.J=J;ref=copy.deepcopy(q.REFS[tid]);t=next(t for t in q.S['tasks'] if t['id']==cond+'__'+tid);target=next(x for x in t['targets']['targets'] if x['label']==label);ref['subcategory']=target['subcategory'];focus=list(target['normal_state']['center'])
   sp=q.read(B/'specs'/tid/(cond+'.json'))['additions'][ord(label)-ord('B')]
   if sp['operation']=='scale':focus[2]+=target['normal_state']['extent'][2]*(sp['factor']-1)
   elif sp['operation']=='offset':focus=[a+b for a,b in zip(focus,sp['offset'])]
   extra=[{'action':'move_down','value':300}] if tid=='U032' else [{'action':'turn','value':-32.3},{'action':'move_up','value':260}]
   actions=q.ROUTES[tid+'__'+label]['actions']+extra
   r=q.q.run(ref,cond,label,[],focus,Path(t['binary_path']),output_root=B/'qa-alternate',prefix_actions=actions,specification_root=B/'specs')
  rows.append(r)
  (B/f'qa-final-worker-{slot}.json').write_text(json.dumps(rows,indent=2)+'\n')
 return rows
jobs=[('S06',c,l) for c,labels in [('A','BC'),('AB','AB'),('ABC','ABC')] for l in labels]+[('U032','ABC','C'),('H03','AB','B'),('H03','ABC','B')]
try:
 lease.acquire();(B/'qa-final.started').write_text(str(os.getpid()))
 with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:rows=sum([f.result() for f in [pool.submit(worker,i,jobs[i::8]) for i in range(8)]],[])
finally:lease.release()
(B/'qa-final-result.json').write_text(json.dumps({'time':time.time(),'model_calls':0,'results':rows},indent=2)+'\n')
