from pathlib import Path
import copy, json, random, hashlib, time
B=Path(__file__).resolve().parent
O=B.parent/'gemini-unreal-multibug-20260922'
R=B.parent/'section62-gemini-repeats-20260924'
def read(p):return json.loads(p.read_text())
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
assert not (B/'episodes-selection.json').exists()
old=read(O/'episodes-selection.json');refs=read(O/'reference-provenance.json');rng=random.Random(6202609241)
protected=read(R/'protected-source-hashes.json')
rubrics={
 'G1':{'expected':'The object rests on its normal supporting surface.','criteria':'The specified object floats with a visible unsupported gap below it.'},
 'G3':{'expected':'The object has an ordinary size relative to its surroundings and purpose.','criteria':'The specified object is abnormally oversized relative to nearby objects and its normal purpose.'},
 'C1':{'expected':'The visible solid object blocks the player.','criteria':'The player penetrates or passes through the visible solid body of this specific object; walking around its outside does not qualify.'}}
tasks=[];draws=[];routes={}
for src in sorted([t for t in old['tasks'] if t['condition']=='ABC'],key=lambda t:t['task_id']):
 tid=src['task_id'];targets=copy.deepcopy(src['targets']);spec=read(O/src['composition_spec']);cats=[]
 for target,addition in zip(targets['targets'][1:],spec['additions']):
  normal=target['normal_state'];eligible=[x for x in ['C1','G1','G3'] if x!=src['subcategory']]
  if not(normal['collision'] and normal['pawn_response']==2 and normal['collision_enabled']):eligible.remove('C1') if 'C1' in eligible else None
  cat=rng.choice(eligible);cats.append(cat)
  addition.clear();addition.update({k:normal[k] for k in ['actor','mesh','position','scale','rotation']})
  if cat=='G1':addition.update(operation='offset',offset=[0,0,60])
  elif cat=='G3':addition.update(operation='scale',factor=3)
  else:addition.update(operation='no_collision')
  target.update(subcategory=cat,rubrics=rubrics[cat],status='random_candidate_pending_native_and_visual_QA')
  draws.append({'anchor':tid,'label':target['label'],'actor':target['actor'],'anchor_category':src['subcategory'],'eligible':eligible,'selected':cat})
 review=read(O/'qa-reviews'/tid/'review.json')
 for label in ['A','B','C']:
  candidates=[O/f for f in review['evidence_files'] if f.endswith('/A/'+label+'/result.json')]
  p=candidates[-1];v=read(p);view=read(p.parent/'target-view.json');assert v['status']=='traversed_pending_visual_review'
  steps=v['actions'];cut=next(i for i,x in enumerate(steps) if x['action']['request_id']==view['request_id'])
  actions=[{k:x['action'][k] for k in ['action','value']} for x in steps[:cut+1]]
  routes[tid+'__'+label]={'source':str(p),'source_sha256':sha(p),'actions':actions,'inspection_position':view['position_cm']}
  protected[str(p)]=sha(p);protected[str(p.parent/'target-view.json')]=sha(p.parent/'target-view.json')
 for cond,n in [('AB',1),('ABC',2)]:
  eid=cond+'__'+tid;sp={**spec,'additions':spec['additions'][:n]};write(B/'specs'/tid/(cond+'.json'),sp)
  rubric={**targets,'episode_id':eid,'condition':cond,'targets':targets['targets'][:n+1],'sampling':'Fixed seed random categories excluding anchor category; additional categories may coincide; fixed previously validated distinct objects.'}
  rubric.pop('source_review_sha256',None);rubric.pop('accepted_draft',None);write(B/'rubrics'/(eid+'.json'),rubric)
  t=copy.deepcopy(next(t for t in old['tasks'] if t['id']==eid));prod=B/'production'/eid
  for rel in ['audit/runtime.json','shared/runtime-prod.json']:
   runtime=read(Path(t['private_production'])/rel);profile=copy.deepcopy(next(iter(runtime['launch_profiles'].values())))
   profile['extra_args']=[x for x in profile.get('extra_args',[]) if not x.startswith('-AuditorComposition=')]+['-AuditorComposition='+str(B/'specs'/tid/(cond+'.json'))]
   runtime['launch_profiles']={eid:profile};write(prod/rel,runtime)
  write(prod/'audit/tasks.json',read(Path(t['private_production'])/'audit/tasks.json'))
  t.update(private_production=str(prod),targets=rubric,composition_spec_absolute=str(B/'specs'/tid/(cond+'.json')),composition_sha256=sha(B/'specs'/tid/(cond+'.json')))
  t.pop('composition_spec',None);tasks.append(t)
  for rel in ['audit/runtime.json','shared/runtime-prod.json','audit/tasks.json']:protected[str(prod/rel)]=sha(prod/rel)
random.Random(6202609242).shuffle(tasks)
write(B/'episodes-selection.json',{**old,'tasks':tasks,'seed':6202609241,'cohort_scope':'One pilot round: 21 unchanged anchors, random other-category additions B/C, nested AB and ABC; original 21 A baseline reused.'})
write(B/'random-draws.json',{'seed':6202609241,'replacement_between_B_and_C':True,'exclude_anchor_category':True,'categories':['G1','G3','C1'],'model_outcomes_used':False,'draws':draws})
write(B/'routes.json',routes);write(B/'reference-provenance.json',refs);write(B/'original-results.json',read(R/'original-results.json'));write(B/'protected-source-hashes.json',protected)
write(B/'plan.json',{'time':time.time(),'authorization':'User requested random categories and then explicitly one round first.','new_model_episodes':42,'baseline':'Original 21 A outcomes reused, no A reruns.','gpu':[0,1,2,3],'workers':8,'seed':6202609241,'category_scope':['G1 floating','G3 oversized','C1 missing collision'],'sampling':'Draw B and C independently from eligible supported categories other than A; keep previously validated distinct object locations.','nested':True,'agent_and_judge':'Exact original Gemini agent, anchor-specific instruction/ICL/type hint, 40 actions, 400 tools, medium and original primary/joint judges preserved.','interpretation':'Effect of other-category coexisting anomalies under original anchor-directed audit instructions; do not claim unrestricted all-type auditing.','old_results':'Original same-category batch and stopped repeats kept separate; no overwritten attempts or cleared STOP.','guard':'No paid calls before actual native state/routes/collision and assistant image checks, prompt equivalence and fresh single-use admission.'})
print('Prepared 42 random-category candidates; no model calls.')
