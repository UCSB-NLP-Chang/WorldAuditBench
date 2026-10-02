"""Auxiliary one-to-one target matching; leaves original A binary judgments untouched."""
from pathlib import Path
import json,importlib.util,sys,time,hashlib,fcntl,traceback
B=Path(__file__).resolve().parent;ROOT=B.parents[3];J=B/'judge';CODE=B/'judge.py'
spec=importlib.util.spec_from_file_location('auxiliary_multibug_judge',CODE);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
g.PROMPT_PATH=B/'judge_multibug_prompt.md'
report_schema={'type':'object','properties':{'report_id':{'type':'string'},'source_id':{'type':'string'},'quote':{'type':'string'},'matched_target':{'type':'string','enum':['A','B','C','none']},'assessment':{'type':'string','enum':['target_match','supported_incidental','unsupported','uncertain']},'reason':{'type':'string'}},'required':['report_id','source_id','quote','matched_target','assessment','reason'],'additionalProperties':False}
g.SCHEMA={'type':'object','properties':{'reports':{'type':'array','items':report_schema}},'required':['reports'],'additionalProperties':False}
CURRENT={}
def validate(v):
 assert isinstance(v,dict) and set(v)=={'reports'} and isinstance(v['reports'],list)
 ids=set();matched=set();spans={}
 for r in v['reports']:
  assert set(r)==set(report_schema['required']) and all(isinstance(x,str) for x in r.values())
  assert r['report_id'] and r['report_id'] not in ids;ids.add(r['report_id'])
  source=CURRENT['sources'][r['source_id']];assert r['quote'] and r['quote'] in source
  a=source.index(r['quote']);z=a+len(r['quote']);assert all(z<=x or a>=y for x,y in spans.get(r['source_id'],[]));spans.setdefault(r['source_id'],[]).append((a,z))
  if r['assessment']=='target_match':assert r['matched_target'] in CURRENT['labels'] and r['matched_target'] not in matched;matched.add(r['matched_target'])
  else:assert r['matched_target']=='none' and r['assessment'] in ['supported_incidental','unsupported','uncertain']
  assert r['reason'].strip()
 return v
g.validate_result=validate

def main():
 lock=(J/'auxiliary.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 while True:
  selection=json.loads((B/'episodes-selection.json').read_text());pending=False
  for t in selection['tasks']:
   job=J/'cases'/t['id'];result=job/'joint-target-matches.json'
   if result.exists() or (job/'joint-judge-error.json').exists():continue
   if not (job/'evidence.json').exists():continue
   output=json.loads((job/'judge-input.json').read_text());rubric=json.loads((B/'rubrics'/(t['id']+'.json')).read_text());ev=json.loads((job/'evidence.json').read_text())
   sources={'summary':output['summary'],**{'flag_'+str(i+1):json.dumps(x,ensure_ascii=False) for i,x in enumerate(output['bugs'])}}
   CURRENT.clear();CURRENT.update(sources=sources,labels=[x['label'] for x in rubric['targets']])
   payload={**output,'claim_sources':sources}
   provenance={'model':'gpt-6-astra','reasoning_effort':'medium','original_A_metric':'Separately judged by unchanged original binary judge; do not replace it with joint matches','prompt_sha256':hashlib.sha256(g.PROMPT_PATH.read_bytes()).hexdigest(),'rubric_sha256':hashlib.sha256((B/'rubrics'/(t['id']+'.json')).read_bytes()).hexdigest(),'input_sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest(),'time':time.time()}
   (job/'joint-judge-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
   try:
    v=g.judge(json.dumps(rubric,ensure_ascii=False),json.dumps(payload,ensure_ascii=False),g.read_images([job/n for n in ev['images']]),model='gpt-6-astra',reasoning_effort='medium',timeout=600)
    matches=[r for r in v['reports'] if r['assessment']=='target_match'];known=[r for r in v['reports'] if r['assessment']!='uncertain'];supported=[r for r in known if r['assessment'] in ['target_match','supported_incidental']]
    v.update(target_count=len(CURRENT['labels']),matched_targets=[r['matched_target'] for r in matches],all_target_success=int(len(matches)==len(CURRENT['labels'])),target_recall=len(matches)/len(CURRENT['labels']),report_precision_known=len(supported)/len(known) if known else None,uncertain_reports=sum(r['assessment']=='uncertain' for r in v['reports']),model='gpt-6-astra')
    with result.open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    print(t['id'],'joint judged',v['matched_targets'],flush=True)
   except Exception as e:(job/'joint-judge-error.json').write_text(json.dumps({'time':time.time(),'error':repr(e),'traceback':traceback.format_exc(),'no_score':True},indent=2));print(t['id'],'joint failed; no fabricated score',flush=True)
  if (J/'available-cases.finished').exists():break
  time.sleep(30)
if __name__=='__main__':main()
