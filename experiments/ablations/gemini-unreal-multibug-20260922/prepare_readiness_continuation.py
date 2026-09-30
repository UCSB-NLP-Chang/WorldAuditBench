from pathlib import Path
import json,time
from admission_guard import digest
from readiness_continuation_guard import validate
B=Path(__file__).resolve().parent

def main():
 assert not (B/'readiness-continuation-admission.json').exists()
 old=(B/'coordinator.py').read_text();fixed=(B/'coordinator_readiness_v2.py').read_text()
 assert fixed==old.replace("assert (native_root/'response.json').exists()","if not (native_root/'response.json').exists():\n      if STOP.wait(.5):raise RuntimeError('Batch interrupted')\n      continue")
 p=json.loads((B/'progress.json').read_text());s=json.loads((B/'episodes-selection.json').read_text());completed=[tid for tid,d in p['tasks'].items() if d['status']=='completed'];eligible=[t['id'] for t in s['tasks'] if t['id'] not in completed]
 files={}
 def add(p):files[str(p)]=digest(p)
 for n in ['progress.json','DRAIN.json','batch.finished','reservation.json','admission.json','admission.consumed.json','startup-readiness-diagnosis.json','coordinator.py','coordinator_readiness_v2.py','readiness_continuation.py','readiness_continuation_guard.py','readiness-fix-preflight/status.json','readiness-fix-preflight/reservation.json']:
  add(B/n)
 for tid,d in p['tasks'].items():
  if d['status']=='completed':
   for n in ['launch.json','episode/meta.json','episode/mcp-calls.jsonl','episode-config.json','prompt.txt']:add(Path(d['run_dir'])/n)
  elif d['status']=='failed':
   for n in ['agent.log','environment.log','result.json']:add(B/'cases'/tid/'attempt-1'/n)
 a={'schema':'reviewed-pre-model-readiness-continuation-v1','time':time.time(),'files':files,'preserved_completed':completed,'next_attempt':{tid:2 if p['tasks'][tid]['status']=='failed' else 1 for tid in eligible},'dispatch_order':eligible,'archive_directory':'readiness-phase1-archive-'+str(int(time.time())),'rationale':'Original42 Gemini execution authorized.7model-completed retained;32neverattempted plus3 proven pre-model native startup failures receive first model execution. No paid model retry. Original attempts and old control records archived, never overwritten.'}
 with (B/'readiness-continuation-admission.json').open('x') as f:f.write(json.dumps(a,indent=2)+'\n')
 validate();print('Reviewed continuation35 validated;7completed preserved;3pre-API retries only; not consumed')
if __name__=='__main__':main()
