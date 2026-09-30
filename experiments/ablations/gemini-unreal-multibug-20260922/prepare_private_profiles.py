"""Materialize private AB/ABC catalogs after reviewed composition specs exist.
This prepares files only. It does not acquire GPUs, issue admission or call models.
"""
from pathlib import Path
import copy,json,random
from admission_guard import digest
B=Path(__file__).resolve().parent

def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def candidate_runtime(ref,family):
 tid=ref['id']
 if family=='urban':
  receipt=B/'builds'/family/'build.json';build=json.loads(receipt.read_text());assert build['status']=='compiled'
  binary=B/'packages'/(family+'-'+tid)/Path(ref['profile']['binary']).relative_to(Path(ref['profile']['binary']).parents[3])
  equivalence=B/'reference-qa-status.json'
 else:
  receipt=B/'builds'/family/'warmup-v2/status.json';build=json.loads(receipt.read_text());assert build['exit_code']==0
  equivalence=B/(family+'-warmup-v2/status.json');q=json.loads(equivalence.read_text())['tasks'][tid]
  assert not q['state_differences'],'Candidate must match original states including world_time'
  binary=Path(q['candidate_binary'])
  assert (B/(family+'-warmup-v2/packages')).resolve() in binary.resolve().parents
 assert digest(binary)==build['binary_sha256'],'Candidate differs from the reviewed build'
 return binary,build['binary_sha256'],{'build_receipt':str(receipt.relative_to(B)),'build_receipt_sha256':digest(receipt),'equivalence_receipt':str(equivalence.relative_to(B)),'equivalence_receipt_sha256':digest(equivalence)}
def main():
 assert not (B/'episodes-selection.json').exists(),'Do not overwrite a frozen selection'
 candidates=json.loads((B/'candidate-anchors.json').read_text())
 refs={t['id']:t for t in json.loads((B/'reference-provenance.json').read_text())['tasks']}
 review=json.loads((B/'qa-review.json').read_text())
 assert len(review['episodes'])==42 and review['model_calls']==0
 tasks=[]
 for t in candidates['tasks']:
  tid=t['id'];ref=refs[tid];binary,build_hash,runtime_provenance=candidate_runtime(ref,t['family'])
  original=Path(t['source_remote'])/'pinned-production'
  for cond,count in [('AB',1),('ABC',2)]:
   eid=cond+'__'+tid;spec_path=B/'specs'/(eid+'.json');spec=json.loads(spec_path.read_text());q=review['episodes'][eid]
   assert all(q[k] is True for k in ['reference_equivalence_passed','anchor_unchanged','added_distinct','all_targets_reachable','normal_controls_reviewed','render_review_passed'])
   assert spec['task_id']==tid and len(spec['additions'])==count
   prod=B/'production'/eid;assert not prod.exists()
   profile=copy.deepcopy(ref['profile']);profile['binary']=str(binary);profile['build_sha256']=build_hash
   assert not any(x.startswith('-AuditorComposition') for x in profile.get('extra_args',[]))
   profile.setdefault('extra_args',[]).append('-AuditorComposition='+str(spec_path))
   for name in ['audit/runtime.json','shared/runtime-prod.json']:
    runtime=json.loads((original/name).read_text());runtime['launch_profiles']={eid:profile};write(prod/name,runtime)
   task=copy.deepcopy(t);task['build_sha256']=build_hash;task.pop('source_remote',None)
   write(prod/'audit/tasks.json',{'tasks':[task]})
   tasks.append({**t,'id':eid,'task_id':tid,'condition':cond,'reference_run':ref['selected_run'],'composition_spec':str(spec_path.relative_to(B)),'composition_sha256':digest(spec_path),'private_production':str(prod),'binary_path':str(binary),'build_sha256':build_hash,'runtime_provenance':runtime_provenance,'policy_path':ref['policy_source'],'policy_sha256':ref['policy_sha256'],'targets':json.loads((B/'rubrics'/(eid+'.json')).read_text())})
 random.Random(620220922).shuffle(tasks)
 write(B/'episodes-selection.json',{'model':'gemini-3.8-flash','thinking_level':'medium','max_actions':40,'max_tool_calls':400,'seed':620220922,'minimap_policy':'masked-before-archive-v1','cohort_scope':'21 static G1/G3/C1 anchors across seven Unreal families, nested AB and ABC','tasks':tasks})
if __name__=='__main__':main()
