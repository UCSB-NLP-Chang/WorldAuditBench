"""Check real AB/ABC native injection and capture views. Not sufficient for admission."""
from pathlib import Path
import copy,json,math,os,signal,time
import qa_urban_reference as qa
ROOT=qa.B
qa.B=ROOT/'composition-smoke'
qa.JOURNAL=ROOT/'composition-smoke-reservation.json'
qa.GPU=0

def main():
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,qa.stop)
 refs={t['id']:t for t in json.loads((ROOT/'reference-provenance.json').read_text())['tasks']}
 status={'status':'running','models_started':0,'tasks':{}};path=ROOT/'composition-smoke-status.json'
 lease=qa.Reservation('/home/ec2-user/unreal-production',qa.JOURNAL,[0])
 try:
  lease.acquire()
  for tid in ['U014','U015','U032']:
   ref=refs[tid];normal=json.loads((ROOT/'qa-reference'/tid/'candidate/composition-before.json').read_text());normal_by={o['actor']:o for o in normal['meshes']};anchor=ref['policy']['target']
   binary=ROOT/'packages'/('urban-'+tid)/Path(ref['profile']['binary']).relative_to(Path(ref['profile']['binary']).parents[3])
   for condition,count in [('AB',1),('ABC',2)]:
    spec_path=ROOT/'draft-compositions'/tid/(condition+'.json');spec=json.loads(spec_path.read_text());modified=copy.deepcopy(ref);modified['profile'].setdefault('extra_args',[]).append('-AuditorComposition='+str(spec_path))
    qa.run(modified,condition,binary)
    d=qa.B/'qa-reference'/tid/condition;applied=json.loads((d/'composition-status.json').read_text());before=json.loads((d/'composition-before.json').read_text())
    assert applied['status']=='applied' and applied['added_count']==count
    before_by={o['actor']:o for o in before['meshes']};assert before_by[anchor]==normal_by[anchor]
    assert {o['actor'] for o in applied['additions']}=={o['actor'] for o in spec['additions']}
    for s,o in zip(spec['additions'],applied['additions']):
     assert before_by[s['actor']]==normal_by[s['actor']]
     if s['operation']=='offset':assert math.dist(o['position'],[x+y for x,y in zip(s['position'],s['offset'])])<.01
     elif s['operation']=='no_collision':assert o['collision'] is False
    status['tasks'][condition+'__'+tid]={'status':'injection_verified_pending_near_view_and_traversal','added_count':count,'anchor_initial_state_unchanged':True,'models_started':0};qa.write(path,status)
  status['status']='smoke_complete_pending_rendered_routes'
 except Exception as exc:status.update(status='needs_attention',error=repr(exc));raise
 finally:
  qa.terminate(qa.ACTIVE);lease.release();status['time']=time.time();qa.write(path,status)
if __name__=='__main__':main()
