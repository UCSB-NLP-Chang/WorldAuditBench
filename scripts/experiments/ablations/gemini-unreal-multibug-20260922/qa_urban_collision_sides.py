"""Separate collision-control directions; keeps the earlier diagnostic captures."""
from pathlib import Path
import json,signal,time
import qa_composition_routes as q
qa=q.qa;B=q.B;q.J=B/'urban-collision-sides-reservation.json';q.GPU=3
refs={r['id']:r for r in json.loads((B/'reference-provenance.json').read_text())['tasks']}
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 lease=qa.Reservation('/home/ec2-user/unreal-production',q.J,[3]);out={'status':'running','model_calls':0,'tasks':[]}
 try:
  lease.acquire()
  for tid,label in [('U015','C'),('U032','B')]:
   ref=refs[tid];targets=json.loads((B/'draft-compositions'/tid/'targets.json').read_text())['additions'];target=next(t for t in targets if t['label']==label);focus=target['normal_state']['center']
   path=B/'composition-route-plans'/tid/(label+'-grid100');path=path if path.exists() else B/'composition-route-plans'/tid/label
   n=json.loads((path/'native.json').read_text());extension=list(reversed(n['route_to_old_spawn']));points=ref['policy']['route_to_old_spawn']+extension[1:]
   if tid=='U015':points += [[-2700,-1100,193.8],[-2700,focus[1],193.8]]
   else:points += [[-3850,-1350,193.8],[-3890,-1600,193.8],[-3890,focus[1],193.8]]
   original=Path(ref['profile']['binary']);binary=B/'packages'/('urban-'+tid)/original.relative_to(original.parents[3])
   for condition in ['A','AB','ABC']:
    result=q.run(ref,condition,label,points,focus,binary,output_root=B/'urban-collision-sides');out['tasks'].append({k:v for k,v in result.items() if k!='actions'});qa.write(B/'urban-collision-sides/status.json',out)
  out['status']='captured_pending_review'
 finally:qa.terminate(qa.ACTIVE);lease.release();out['time']=time.time();qa.write(B/'urban-collision-sides/status.json',out)
if __name__=='__main__':main()
