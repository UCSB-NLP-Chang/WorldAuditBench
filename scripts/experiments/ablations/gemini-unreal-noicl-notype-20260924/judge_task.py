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
 g=load('primary',B/'judge.py');t=next(t for t in read(B/'selection.json')['tasks'] if t['id']==tid)
 ep=B/'cases'/tid/'run/episode';meta=read(ep/'meta.json')
 assert meta['status']=='completed' and meta['actions_used']==40 and meta['done_summary'] and meta.get('icl_complete') and not meta.get('icl_examples_delivered')
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
 assert not any((B/n).exists() for n in ['STOP.json','JUDGE_STOP.json'])
 result=g.judge((job/'rubric.json').read_text(),(job/'judge-input.json').read_text(),g.read_images(images),model='gpt-6-astra',reasoning_effort='medium',timeout=600)
 write(job/'judge.json',result)
 print(tid,'graded',flush=True)
if __name__=='__main__':main()
