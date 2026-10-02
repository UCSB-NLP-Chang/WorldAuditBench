"""Consolidate already visually reviewed evidence; never infer missing visual passes."""
from pathlib import Path
import json,hashlib,time,re,shutil
B=Path(__file__).resolve().parent
def read(n):return json.loads((B/n).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def evidence(x):
 out={}
 if isinstance(x,dict):
  if 'path' in x and 'sha256' in x:out[x['path']]=x['sha256']
  for k,v in x.items():
   if isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) and ('/' in k or k.endswith(('.json','.png'))):out[k]=v
   elif isinstance(v,(dict,list)):out.update(evidence(v))
 elif isinstance(x,list):
  for v in x:out.update(evidence(v))
 normalized={}
 for p,h in out.items():
  if p.startswith('/'):
   marker=B.name+'/'
   assert marker in p,p
   p=p.split(marker,1)[1]
  normalized[p]=h
 return normalized
S=read('episodes-selection.json')['tasks'];V=read('visual-qa-review.json')['tasks'];N=read('full126-trigger-visual-review.json')['tasks'];T=read('trigger-visual-review.json')['review'];F=read('followup-visual-review.json')
I={t['id']:t for t in read('native-initialization-identity-audit.json')['tasks']};P={t['id']:t for t in read('rendered-policy-correspondence.json')['tasks']}
original={t['id']:t for t in read('selection.json')['tasks']};dynamic={k for k,t in original.items() if t.get('subcategory','').startswith('T') or t.get('subcategory') in ['V1','V2']}
assert len(dynamic)==47 and len(S)==252 and len(I)==126 and all(v['passed'] for v in I.values())
assert len(P)==252 and all(v['passed'] for v in P.values())
D={}
for k in dynamic:
 if k in N:
  r=N[k];assert r['trigger_state_verified'],k;src=['full126-trigger-visual-review.json'];ev=evidence(r);note=r['note']
 elif k=='U023':
  r=T[k];assert r['trigger_state_verified'];src=['trigger-visual-review.json','u023-pinned-state-verification.json'];ev=evidence(r);ev['u023-pinned-state-verification.json']=sha(B/'u023-pinned-state-verification.json');note=r['initial_state_verification']
 elif k in F['review']:
  r=F['review'][k];assert r.get('target_transition_observed_all_arms') or k=='S16' and 'All three arms visibly' in r['note'],k
  src=['followup-visual-review.json'];ev=evidence(r['new_trigger_evidence'] if k=='S11' else r['evidence']);note=r['note']
 elif k in F['temporal_common_pretrigger_review']:
  r=F['temporal_common_pretrigger_review'][k];assert r['all_arms_pretrigger_visual_state_matches'] and r['all_arms_transition_observed'];src=['trigger-visual-review.json','followup-visual-review.json'];ev=evidence(T[k]);note=T[k]['note']+' Initialtime0 READY and actual common pretrigger/transition frames reviewed.'
 elif k in F['angle_visibility_review']:
  r=F['angle_visibility_review'][k];assert r['target_visible_at_offset_all_arms'] and r['disappearance_on_return_all_arms'];src=['trigger-visual-review.json','followup-visual-review.json'];ev=evidence(T[k]);note=r['note']
 else:raise AssertionError('Missing task-specific trigger review '+k)
 assert all(any('/'+arm+'/' in p for p in ev) for arm in ['far','near','medium']),(k,'incomplete arm image evidence')
 D[k]={'trigger_state_verified':True,'review_sources':src,'evidence':ev,'note':note}
E={};all_ev={};errors=[]
for t in S:
 k=t['task_id'];arm=t['id'].split('__')[0];r=V[k];assert r['target_visible'] and I[k]['passed'] and P[t['id']]['passed']
 assert P[t['id']]['model_policy_sha256']==t['policy_sha256'],t['id']
 # New supplemental visibility views supersede historical target framing.
 ev=evidence(r.get('supplemental_evidence') or r.get('visibility_evidence') or r.get('images',{}))
 assert ev,(k,'missing visibility evidence')
 sources=['visual-qa-review.json','native-initialization-identity-audit.json','rendered-policy-correspondence.json']
 note='Static task: original bug/map/build unchanged; target actually visible and native initialization identity verified.'
 if k in D:ev.update(D[k]['evidence']);sources+=D[k]['review_sources'];note=D[k]['note']
 all_ev.update(ev)
 E[t['id']]={'task_id':k,'arm':arm,'policy_sha256':t['policy_sha256'],'route_passed':True,'target_visible':True,'trigger_state_verified':True,'dynamic_trigger_task':k in D,'initial_simulation_time':0,'review_sources':sources,'evidence_sha256':ev,'trigger_review_note':note,'initialization_scope':'Same pinned executable/map/task, original task entry apart from allowed spawn/route, independent process/UserDir, affirmative native ready and time0 pose. No claim of hidden-memory digest equality across spawns.'}
for p,h in all_ev.items():
 f=B/p
 if not f.exists():errors.append({'path':p,'error':'missing_local'})
 elif sha(f)!=h:errors.append({'path':p,'error':'hash_mismatch','expected':h,'actual':sha(f)})
out={'created_at':time.time(),'episodes':E,'episode_count':len(E),'dynamic_task_groups':len(D),'unique_evidence_files_checked':len(all_ev),'hash_errors':errors,'evidence_hashes_passed':not errors,'current_policy_matches':True,'approved':False,'ready_for_model':False,'pending':['Remote exact evidence/current rendered policy/result verification before approval'],'note':'Explicit task-specific visual reviews consolidated. This file is not a model launch approval.'}
p=B/'episode-qa-evidence-review.json'
if p.exists() and read(p.name).get('episode_count')==100:shutil.copy2(p,B/'episode-qa-evidence-review-scope50-preserved.json')
p.write_text(json.dumps(out,indent=2));print(json.dumps({'episodes':len(E),'dynamic':len(D),'evidence_files':len(all_ev),'errors':errors[:25],'error_count':len(errors)},indent=2))
