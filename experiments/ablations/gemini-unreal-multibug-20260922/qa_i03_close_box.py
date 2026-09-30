"""Render I03 at an explicitly closer checkpoint; retain the coarse-grid failure."""
from pathlib import Path
import json,math,signal,time
import qa_composition_routes as q
qa=q.qa;B=q.B;q.GPU=2;q.J=B/'i03-close-box-reservation.json'
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 ref=next(r for r in json.loads((B/'reference-provenance.json').read_text())['tasks'] if r['id']=='I03');targets=json.loads((B/'draft-compositions/I03/targets.json').read_text())['additions']
 binary=Path(json.loads((B/'industrial-warmup-v2/status.json').read_text())['tasks']['I03']['candidate_binary'])
 a=json.loads((B.parent/'gemini-unreal-distance-ablation-20260921/route-preparation/I03/result.json').read_text());paths={'A':a['route']};focus={'A':ref['policy']['focus']}
 for t in targets:
  label=t['label'];p=B/'ancient-industrial-route-plans/I03'/label
  if label=='B':paths[label]=json.loads((p/'result.json').read_text())['route']
  else:
   p=B/'ancient-industrial-route-plans/I03/C-grid100';native=json.loads((p/'native.json').read_text());assert native['status']=='planned';extension=list(reversed(native['route_to_old_spawn']));route=ref['policy']['route_to_old_spawn']+extension[1:];last=route[-1];c=t['normal_state']['center'];dist=math.dist(last[:2],c[:2]);assert 450<dist<500
   route.append([last[0]+(c[0]-last[0])*75/dist,last[1]+(c[1]-last[1])*75/dist,last[2]]);paths[label]=route
  focus[label]=t['normal_state']['center']
 lease=None;out={'status':'waiting_for_warmup_QA','model_calls':0,'tasks':[]};qa.write(B/'i03-close-box/status.json',out)
 try:
  while True:
   p=B/'remaining-family-warmup-v2-status.json';s=json.loads(p.read_text())
   if len(s.get('families',{}))==5 and all(json.loads((B/(fam+'-warmup-v2-reservation.json')).read_text())['status']=='released' for fam in s['families']):break
   if qa.STOP:raise InterruptedError('QA stopped')
   time.sleep(5)
  lease=qa.Reservation('/home/ec2-user/unreal-production',q.J,[2]);lease.acquire();out['status']='running'
  for condition in ['A','AB','ABC']:
   for label in 'ABC':
    f=list(focus[label])
    if label!='A' and label in condition:f[2]+=next(t for t in targets if t['label']==label)['normal_state']['extent'][2]*2
    r=q.run(ref,condition,label,paths[label],f,binary,output_root=B/'i03-close-box');out['tasks'].append({k:v for k,v in r.items() if k!='actions'});qa.write(B/'i03-close-box/status.json',out)
  out['status']='captured_pending_review'
 finally:
  qa.terminate(qa.ACTIVE)
  if lease:lease.release()
  out['time']=time.time();qa.write(B/'i03-close-box/status.json',out)
if __name__=='__main__':main()
