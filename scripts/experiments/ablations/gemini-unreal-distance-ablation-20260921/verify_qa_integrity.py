"""Read-only remote integrity check for reviewed current252 episode evidence."""
from pathlib import Path
import json,hashlib,time
B=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
cache={}
def sha(p):
 p=Path(p)
 if str(p) not in cache:cache[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 return cache[str(p)]
R=read(B/'episode-qa-evidence-review.json');S=read(B/'episodes-selection.json')['tasks'];assert len(S)==252 and R['evidence_hashes_passed'] and R['episode_count']==252
assert not (B/'batch.started').exists() and not (B/'progress.json').exists()
for t in S:
 k=t['task_id'];a=t['distance_condition'];q=R['episodes'][t['id']];assert q['policy_sha256']==t['policy_sha256']
 for p,h in q['evidence_sha256'].items():assert sha(B/p)==h,('evidence changed',p)
 production=Path(t['private_production']);profiles=[]
 for n in ['audit/runtime.json','shared/runtime-prod.json']:
  for p in read(production/n)['launch_profiles'].values():
   if p.get('build_sha256')==t['build_sha256'] and '-AuditorExplorationTask='+k in p.get('extra_args',[]) and p not in profiles:profiles.append(p)
 assert len(profiles)==1
 profile=profiles[0];assert sha(profile['binary'])==t['build_sha256'],('binary',k)
 paths=[Path(x.split('=',1)[1]) for x in profile['extra_args'] if x.startswith('-AuditorExplorationPolicy=')];assert len(paths)==1 and sha(paths[0])==t['policy_sha256']
 ep=read(paths[0])['tasks'][k];rp=read(B/'rendered-route-qa'/k/a/'policy.json')['tasks'][k];assert ep==rp,('rendered entry',t['id'])
 result=read(B/'rendered-route-qa'/k/a/'result.json');assert result['status']=='route_passed_pending_visual_and_trigger_review' and result['initial_simulation_time']==0 and result['bounds_unchanged']
 # Fresh all3 source evidence is backed by audit; verify hashes have not changed.
for t in read(B/'native-initialization-identity-audit.json')['tasks']:
 assert t['passed']
 for a,x in t['arms'].items():
  d=B/'rendered-route-qa'/t['id']/a
  for field,name in [('initial_image_sha256','initial.png'),('launch_command_sha256','launch-command.json'),('initial_state_sha256','initial-state.json')]:assert sha(d/name)==x[field],(t['id'],a,field)
for prefix,n in [('remaining-probe',6),('glass-probe',3),('pot-probe',3),('resolution-probe',12),('final-probe',15)]:
 f=read(B/(prefix+'.finished'));assert f['processed']==n and not f['stopped'];assert read(B/(prefix+'-reservation.json'))['status']=='released'
result={'verified_at':time.time(),'passed':True,'episodes':252,'native_identity_tasks':126,'evidence_files':R['unique_evidence_files_checked'],'all_unique_files_hashed':len(cache),'review_sha256':sha(B/'episode-qa-evidence-review.json'),'note':'Read-only verification of actual reviewed evidence, current pinned binary/policy and native rendered route entries. No model invocation.'}
(B/'qa-integrity-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
