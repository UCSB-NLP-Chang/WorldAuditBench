"""Fetch completed no-map episodes and automatically run the latest binary judge."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,subprocess,sys,io,tarfile,time,threading,hashlib,csv,fcntl,traceback
B=Path(__file__).resolve().parent;ROOT=B.parents[3];J=B/'judge';J.mkdir(exist_ok=True);JCODE=ROOT/'out/native-agents/judge-7655491';sys.path.insert(0,str(JCODE))
from judge.judge import judge,read_images,validate_result
S=json.loads((B/'episodes-selection.json').read_text());BYID={t['id']:t for t in S['tasks']};CFG=json.loads((ROOT/'out/native-agents/aws-connection.json').read_text());SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i',CFG['identity'],CFG['host'],'python3.12 -'];REMOTE='/mnt/auditor-build/experiment-runs/gemini-unreal-distance-ablation-20260921';LOCK=threading.Lock();STATE={};FUTURES={};AGENT={};FINISHED=False

def remote(code):
 p=subprocess.run(SSH,input=code.encode(),capture_output=True,timeout=240)
 if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace')[-1500:])
 return p.stdout

def summary():
 rows=[]
 for tid,t in BYID.items():
  row={'id':tid,'task_id':t['task_id'],'distance_condition':t['distance_condition'],'family':t['family'],'subcategory':t['subcategory'],'agent_status':AGENT.get(tid,{}).get('status','queued'),'judge_status':STATE.get(tid,{}).get('status','waiting_for_agent')}
  p=J/'cases'/tid/'judge.json'
  if p.exists():row['judge']=validate_result(json.loads(p.read_text()));row['judge_status']='completed'
  rows.append(row)
 graded=[r for r in rows if 'judge' in r];success=sum(r['judge']['score'] for r in graded)
 result={'updated_at':time.time(),'agent_model':'gemini-3.8-flash','thinking_level':'medium','max_actions':40,'judge_model':'gpt-6-astra','reasoning_effort':'medium','minimap_policy':'masked-before-archive-v1','eligible':len(S['tasks']),'agent_completed':sum(r['agent_status']=='completed' for r in rows),'graded':len(graded),'successes':success,'success_rate':success/len(graded) if graded else None,'blocked_backend':sum(r['agent_status']=='blocked_backend' for r in rows),'tasks':rows}
 p=J/'results.json.tmp';p.write_text(json.dumps(result,ensure_ascii=False,indent=2));p.replace(J/'results.json')
 with (J/'results.csv').open('w') as f:
  w=csv.writer(f);w.writerow(['case','family','agent_status','judge_status','score','reason'])
  for r in rows:w.writerow([r['id'],r['family'],r['agent_status'],r['judge_status'],r.get('judge',{}).get('score',''),r.get('judge',{}).get('reason','')])
 return result

def update(tid,**values):
 with LOCK:STATE.setdefault(tid,{}).update(values);r=summary();print(json.dumps({'case':tid,**values,'graded':r['graded']},ensure_ascii=False),flush=True)

def fetch(ids):
 code='''from pathlib import Path
import io,sys,tarfile,json
B=Path(REMOTE);out=io.BytesIO()
with tarfile.open(fileobj=out,mode='w:gz') as tar:
 for tid in IDS:
  ep=B/'cases'/tid/'run/episode';m=json.loads((ep/'meta.json').read_text())
  assert m['status']=='completed' and m['actions_used']==40 and m['done_summary'] and m.get('icl_examples_delivered') and m.get('icl_complete')
  assert m['backend']['minimap_policy']=='masked-before-archive-v1'
  idx={r['ref']:r for r in map(json.loads,(ep/'frames/index.jsonl').read_text().splitlines())}
  refs=list(dict.fromkeys(r for f in m.get('flags',[]) for r in f.get('evidence',[])))
  if not refs:refs=list(dict.fromkeys(['a0','a'+str(m['actions_used'])]))
  assert all(r in idx for r in refs)
  for n in ['meta.json','frames/index.jsonl']+[str(Path('frames')/idx[r]['file']) for r in refs]:
   assert (ep/n).resolve().is_relative_to(ep.resolve())
   tar.add(ep/n,arcname=tid+'/episode/'+n)
sys.stdout.buffer.write(out.getvalue())
'''.replace('REMOTE',repr(REMOTE)).replace('IDS',repr(ids))
 data=remote(code)
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:tar.extractall(J/'cases',filter='data')
 for tid in ids:
  t=BYID[tid];job=J/'cases'/tid;ep=job/'episode';m=json.loads((ep/'meta.json').read_text());idx={r['ref']:r for r in map(json.loads,(ep/'frames/index.jsonl').read_text().splitlines())}
  refs=list(dict.fromkeys(r for f in m.get('flags',[]) for r in f.get('evidence',[])))
  if not refs:refs=list(dict.fromkeys(['a0','a'+str(m['actions_used'])]))
  refs.sort(key=lambda r:(idx[r]['action'],idx[r].get('t_sim',0),r))
  output={'bugs':m.get('flags',[]),'summary':m['done_summary'],'attached_evidence':[{'image':i+1,'ref':r,'file':idx[r]['file']} for i,r in enumerate(refs)]}
  (job/'judge-input.json').write_text(json.dumps(output,ensure_ascii=False,indent=2));(job/'rubric.json').write_text(json.dumps({'case_type':'bug','rubrics':t['rubrics_i18n']['en']},ensure_ascii=False,indent=2));(job/'evidence.json').write_text(json.dumps({'refs':refs,'images':[str(Path('episode/frames')/idx[r]['file']) for r in refs]},indent=2))

def grade(tid):
 job=J/'cases'/tid;p=job/'judge.json';e=json.loads((job/'evidence.json').read_text())
 if p.exists():validate_result(json.loads(p.read_text()));update(tid,status='completed',resumed=True);return
 for attempt in range(1,4):
  update(tid,status='judging',attempt=attempt)
  try:
   provenance={'model':'gpt-6-astra','reasoning_effort':'medium','judge_code_commit':'7655491fa32ce400b03c876372800a2ea0d69465','verified_latest_iclr':'aed425f8044e77d55352dcf94fd5ec1be019093b','minimap_policy':'masked-before-archive-v1','image_selection':'all final active ledger evidence refs, deduplicated and chronological; if none, initial and final observation','evidence_refs':e['refs'],'input_sha256':hashlib.sha256((job/'judge-input.json').read_bytes()).hexdigest(),'rubric_sha256':hashlib.sha256((job/'rubric.json').read_bytes()).hexdigest(),'prompt_sha256':hashlib.sha256((JCODE/'judge/judge_prompt.md').read_bytes()).hexdigest(),'images_sha256':{n:hashlib.sha256((job/n).read_bytes()).hexdigest() for n in e['images']}}
   (job/'judge-provenance.json').write_text(json.dumps(provenance,indent=2))
   result=judge((job/'rubric.json').read_text(),(job/'judge-input.json').read_text(),read_images([job/n for n in e['images']]),model='gpt-6-astra',reasoning_effort='medium',timeout=600)
   tmp=job/'judge.json.tmp';tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2));tmp.replace(p);update(tid,status='completed',score=result['score']);return
  except Exception as exc:
   (job/f'judge-error-{attempt}.log').write_text(traceback.format_exc());update(tid,status='failed' if attempt==3 else 'retry_wait',error=str(exc)[-800:])
   if attempt<3:time.sleep(10*attempt)

def backup():
 files=[p for p in J.rglob('*') if p.is_file() and p.suffix in {'.json','.csv'} and 'episode' not in p.parts]
 buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w:gz') as tar:
  for p in files:tar.add(p,arcname=str(p.relative_to(J)))
 # Stream archive to an SSH process; no credentials are copied.
 cmd=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i',CFG['identity'],CFG['host'],"python3.12 -c \"import pathlib,tarfile,sys; p=pathlib.Path('/mnt/auditor-build/experiment-runs/gemini-unreal-distance-ablation-20260921/judge'); p.mkdir(exist_ok=True); tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz').extractall(p,filter='data')\""]
 p=subprocess.run(cmd,input=buf.getvalue(),capture_output=True,timeout=120)
 if p.returncode:raise RuntimeError('Judge backup failed: '+p.stderr.decode()[-500:])

if __name__=='__main__':
 lock=(J/'pipeline.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 with ThreadPoolExecutor(max_workers=4) as pool:
  while True:
   try:
    status=json.loads(remote("from pathlib import Path\nimport json\nB=Path("+repr(REMOTE)+")\np=json.loads((B/'progress.json').read_text());p['batch_finished']=(B/'batch.finished').exists() and not (B/'recovery.pending').exists();print(json.dumps(p))"));AGENT=status['tasks'];FINISHED=status['batch_finished'];(B/'progress.json').write_text(json.dumps(status,indent=2))
    ids=[tid for tid,d in AGENT.items() if d['status']=='completed' and tid not in FUTURES]
    if ids:
     fetch(ids)
     for tid in ids:FUTURES[tid]=pool.submit(grade,tid)
    with LOCK:result=summary()
    backup()
    pending=[t for t,d in AGENT.items() if d['status'] not in ('completed','blocked_backend','failed')]
    if FINISHED and not pending and all(f.done() for f in FUTURES.values()):
     (J/'available-cases.finished').write_text(json.dumps({'time':time.time(),'graded':result['graded'],'blocked_backend':result['blocked_backend']}));backup();break
   except Exception as e:print('PIPELINE RETRY',repr(e),flush=True)
   time.sleep(45)
 print('JUDGE PIPELINE FINISHED',flush=True)
