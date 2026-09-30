"""Freeze reviewed nested compositions before any model episode is admitted."""
from pathlib import Path
import json,copy,time
from admission_guard import digest
B=Path(__file__).resolve().parent

def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:f.write(json.dumps(x,indent=2)+'\n')
def main():
 assert not any((B/n).exists() for n in ['episodes-selection.json','qa-review.json','admission.json','batch.started','progress.json'])
 anchors=json.loads((B/'candidate-anchors.json').read_text())['tasks'];assert len(anchors)==21
 reviews={};episodes={}
 for task in anchors:
  tid=task['id'];rp=B/'qa-reviews'/tid/'review.json';r=json.loads(rp.read_text())
  assert r['status']=='anchor_composition_QA_passed' and r['model_calls']==0
  for rel,h in r['evidence_sha256'].items():assert digest(B/rel)==h,(tid,rel)
  draft=B/r.get('accepted_draft','draft-compositions/'+tid);targets=json.loads((draft/'targets.json').read_text())
  assert targets['selection_used_model_outcomes'] is False
  original={'label':'A','actor':targets['A']['actor'],'description':task['title'],'subcategory':task['subcategory'],'rubrics':targets['A']['rubrics']}
  for cond,n in [('AB',1),('ABC',2)]:
   eid=cond+'__'+tid;spec=json.loads((draft/(cond+'.json')).read_text());assert len(spec['additions'])==n
   write(B/'specs'/(eid+'.json'),spec)
   added=copy.deepcopy(targets['additions'][:n])
   for a in added:
    a['status']='reviewed_before_model'
    if a['subcategory']=='C1':a['rubrics']['criteria']='The player penetrates or passes through the visible solid body of this specific object; walking around its outside does not qualify.'
   rubric={'episode_id':eid,'anchor_id':tid,'condition':cond,'targets':[original,*added],'matching':'one-to-one specific reports to targets; one vague report cannot earn several matches','source_review_sha256':digest(rp),'accepted_draft':str(draft.relative_to(B))}
   write(B/'rubrics'/(eid+'.json'),rubric)
   q=copy.deepcopy(r);q['evidence_files']=list(dict.fromkeys(q['evidence_files']+[str(rp.relative_to(B))]));episodes[eid]=q
  reviews[tid]={'review_sha256':digest(rp),'accepted_draft':str(draft.relative_to(B))}
 write(B/'qa-review.json',{'status':'all_21_reviewed_before_model','model_calls':0,'time':time.time(),'episodes':episodes})
 write(B/'cohort-freeze.json',{'time':time.time(),'model_calls':0,'anchors':reviews,'new_episodes':42,'existing_baselines_reused':21,'selection_used_model_outcomes':False})
 print('Frozen21 anchors and42 nested composition specs/rubrics; model calls0')
if __name__=='__main__':main()
