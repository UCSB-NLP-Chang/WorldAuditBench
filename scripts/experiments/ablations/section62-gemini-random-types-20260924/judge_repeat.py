from pathlib import Path
import sys,json,time,hashlib,importlib.util
B=Path(__file__).resolve().parent;tid=sys.argv[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def read(p):return json.loads(p.read_text())
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 g=load('primary',B/'judge.py');t=next(t for t in read(B/'episodes-selection.json')['tasks'] if t['id']==tid)
 ep=B/'cases'/tid/'run/episode';meta=read(ep/'meta.json')
 assert meta['status']=='completed' and meta['actions_used']==40 and meta['done_summary'] and meta.get('icl_complete') and meta.get('icl_examples_delivered')
 assert meta['backend']['minimap_policy']=='masked-before-archive-v1'
 job=B/'judge/cases'/tid;job.mkdir(parents=True,exist_ok=False)
 (job/'episode').symlink_to(ep.resolve())
 idx={r['ref']:r for r in map(json.loads,(ep/'frames/index.jsonl').read_text().splitlines())}
 refs=list(dict.fromkeys(r for f in meta.get('flags',[]) for r in f.get('evidence',[])))
 if not refs:refs=list(dict.fromkeys(['a0','a'+str(meta['actions_used'])]))
 assert all(r in idx for r in refs);refs.sort(key=lambda r:(idx[r]['action'],idx[r].get('t_sim',0),r))
 images=[ep/'frames'/idx[r]['file'] for r in refs]
 assert all(p.resolve().is_relative_to(ep.resolve()) for p in images)
 output={'bugs':meta.get('flags',[]),'summary':meta['done_summary'],'attached_evidence':[{'image':i+1,'ref':r,'file':idx[r]['file']} for i,r in enumerate(refs)]}
 rubric={'case_type':'bug','rubrics':t['rubrics_i18n']['en']}
 write(job/'judge-input.json',output);write(job/'rubric.json',rubric);write(job/'evidence.json',{'refs':refs,'images':['episode/frames/'+idx[r]['file'] for r in refs]})
 provenance={'time':time.time(),'model':'gpt-6-astra','reasoning_effort':'medium','judge_code_commit':'7655491fa32ce400b03c876372800a2ea0d69465','judge_code_sha256':sha(B/'judge.py'),'prompt_sha256':sha(B/'judge_prompt.md'),'input_sha256':sha(job/'judge-input.json'),'rubric_sha256':sha(job/'rubric.json'),'images_sha256':{str(p.relative_to(ep)):sha(p) for p in images}}
 write(job/'judge-provenance.json',provenance)
 assert not any((B/n).exists() for n in ['SYSTEM_STOP','STOP.json','API_QUOTA_OR_AUTH_STOP'])
 result=g.judge((job/'rubric.json').read_text(),(job/'judge-input.json').read_text(),g.read_images(images),model='gpt-6-astra',reasoning_effort='medium',timeout=600)
 write(job/'judge.json',result)
 if t['condition']=='A':
  write(job/'metrics.json',{'anchor_success':result['score'],'all_target_success':result['score'],'matched_targets':result['score'],'target_count':1,'metric_source':'Original binary judge; identical to round1 A condition'})
 else:
  aux=load('aux',B/'aux_judge.py');rub=read(B/'rubrics'/(tid+'.json'))
  sources={'summary':output['summary'],**{'flag_'+str(i+1):json.dumps(x,ensure_ascii=False) for i,x in enumerate(output['bugs'])}}
  aux.CURRENT.update(sources=sources,labels=[x['label'] for x in rub['targets']]);payload={**output,'claim_sources':sources}
  write(job/'joint-judge-provenance.json',{'time':time.time(),'model':'gpt-6-astra','reasoning_effort':'medium','prompt_sha256':sha(B/'judge_multibug_prompt.md'),'rubric_sha256':sha(B/'rubrics'/(tid+'.json')),'input_sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest()})
  assert not any((B/n).exists() for n in ['SYSTEM_STOP','STOP.json','API_QUOTA_OR_AUTH_STOP'])
  v=aux.g.judge(json.dumps(rub,ensure_ascii=False),json.dumps(payload,ensure_ascii=False),aux.g.read_images(images),model='gpt-6-astra',reasoning_effort='medium',timeout=600)
  matches=[r for r in v['reports'] if r['assessment']=='target_match'];known=[r for r in v['reports'] if r['assessment']!='uncertain'];supported=[r for r in known if r['assessment'] in ['target_match','supported_incidental']]
  v.update(target_count=len(aux.CURRENT['labels']),matched_targets=[r['matched_target'] for r in matches],all_target_success=int(len(matches)==len(aux.CURRENT['labels'])),target_recall=len(matches)/len(aux.CURRENT['labels']),report_precision_known=len(supported)/len(known) if known else None,uncertain_reports=sum(r['assessment']=='uncertain' for r in v['reports']),model='gpt-6-astra')
  write(job/'joint-target-matches.json',v)
  write(job/'metrics.json',{'anchor_success':result['score'],'all_target_success':v['all_target_success'],'matched_targets':len(matches),'target_count':len(t['condition']),'metric_source':'Original binary A judge plus unchanged joint target-matching judge'})
 print(tid,'graded',flush=True)
if __name__=='__main__':main()
