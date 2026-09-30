"""Repair the introduced warmup hook after v1 captures, keeping all v1 evidence."""
from pathlib import Path
import json,signal,subprocess,time
import qa_urban_reference as qa
B=qa.B
FAMILIES={'indoor':'AtmosphericResidentialHou','industrial':'FactoryEnvironmentCollect','ancient':'AncientChineseCity','medieval':'MedievalVillage','rural':'RuralAustralia'}
def main():
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,qa.stop)
 refs=json.loads((B/'reference-provenance.json').read_text())['tasks'];overall={'status':'running','model_calls':0,'families':{}}
 for family,name in FAMILIES.items():
  group=[r for r in refs if r['family']==family]
  while not all((B/'qa-reference'/r['id']/'candidate/result.json').exists() for r in group):
   if qa.STOP:raise InterruptedError('Stopped waiting for v1 captures')
   time.sleep(5)
  overall['active']=family;qa.write(B/'remaining-family-warmup-v2-status.json',overall)
  subprocess.run(['python3.12',str(B/'repair_family_warmup.py'),family,name],check=True)
  build=json.loads((B/'builds'/family/'warmup-v2/status.json').read_text());assert build['status']=='compiled_pending_equivalence'
  qa.B=B/(family+'-warmup-v2');qa.GPU=2;qa.JOURNAL=B/(family+'-warmup-v2-reservation.json')
  state={'status':'running','model_calls':0,'tasks':{}};lease=qa.Reservation('/home/ec2-user/unreal-production',qa.JOURNAL,[2])
  try:
   lease.acquire()
   for ref in group:
    tid=ref['id'];binary=qa.stage(ref,Path(build['binary']));new=qa.run(ref,'candidate',binary)
    old=json.loads((B/'qa-reference'/tid/'original/result.json').read_text())['states']
    fields=['actor_state_digest','position_cm','camera_position_cm','yaw_degree','look_degree','map','task_id','simulation_time','world_time']
    diffs={label:{k:[old[label].get(k),new[label].get(k)] for k in fields if old[label].get(k)!=new[label].get(k)} for label in old};diffs={k:v for k,v in diffs.items() if v}
    state['tasks'][tid]={'state_differences':diffs,'candidate_binary':str(binary),'status':'state_equivalent_pending_visual' if not diffs else 'needs_resolution'};qa.write(qa.B/'status.json',state)
   state['status']='state_equivalent_pending_visual' if all(not v['state_differences'] for v in state['tasks'].values()) else 'needs_resolution'
  finally:
   qa.terminate(qa.ACTIVE);lease.release();state['time']=time.time();qa.write(qa.B/'status.json',state)
  overall['families'][family]=state;qa.write(B/'remaining-family-warmup-v2-status.json',overall)
 overall.update(status='finished_pending_visual_and_composition_qa',active=None);qa.write(B/'remaining-family-warmup-v2-status.json',overall)
if __name__=='__main__':main()
