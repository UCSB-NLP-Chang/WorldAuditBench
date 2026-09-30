"""Isolated Section 6.1 replay; one attempt per task, authentic native CLI and judge."""
from pathlib import Path
import json,os,sys,time,subprocess,signal,threading,hashlib,importlib.util,concurrent.futures,re
B=Path(__file__).resolve().parent;C=B/'code';R=Path('/home/ec2-user/game-auditing');OLD=Path('/home/ec2-user/gemini-medieval-20260919')
sys.path.insert(0,str(C))
spec=importlib.util.spec_from_file_location('replay',C/'scripts/native-agents/run_vla_replay.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
TASKS=json.loads((B/'tasks.json').read_text());DEFS=json.loads((B/'category-definitions.json').read_text());PROFILES=json.loads((B/'profiles.json').read_text())['tasks']
ENV=dict(os.environ,PATH=str(OLD/'node-v22.23.2-linux-x64/bin')+':'+os.environ['PATH'])
for k in ['GEMINI_API_KEY','GOOGLE_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','GOOGLE_APPLICATION_CREDENTIALS']:ENV.pop(k,None)
PYTHON=C/'out/native-agents/venv/bin/python';STOP=threading.Event()
def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def command(t,job,dry=False):
 instruction=t['instruction']+'\n\nThis task\'s specific subcategory is '+t['subcategory']+'.\n'+DEFS[t['subcategory']]
 scene=job/'scene.txt';scene.parent.mkdir(parents=True,exist_ok=True);scene.write_text(t['scene']+'\n')
 cmd=[str(PYTHON),str(B/'launch_noicl.py'),'gemini','--environment','vla-replay','--replay-dir',t['recording'],'--replay-mode','vqa','--task',t['id'],'--scene-description-file',str(scene),'--model','gemini-3.8-flash','--gemini-thinking','medium','--max-actions','0','--max-tool-calls','400','--observation','on-demand','--preview-every','5','--instruction',instruction,'--no-icl','--gemini-auth','gemini-api-key','--gemini-api-key-file',str(OLD/'.gemini-api-key'),'--cli',str(OLD/'cli/node_modules/.bin/gemini'),'--run-dir',str(job/'run')]
 if dry:cmd+=['--dry-run']
 return cmd

def verify(t,job):
 run=job/'run';cfg=read(run/'episode-config.json');ref=read(Path(t['baseline_run'])/'episode-config.json');settings=read(run/'gemini-settings.json');bs=read(Path(t['baseline_run'])/'gemini-settings.json');launch=read(run/'launch.json')
 assert cfg['icl']=={'enabled':False} and not (run/'icl').exists()
 for k in ['replay_dir','recording','preview_every','replay_mode','inline_full_res','max_actions','max_tool_calls','observation','seed','require_full_budget','scene_description']:assert cfg[k]==ref[k],(t['id'],k)
 for k in ['model','tools','mcp','security','context','modelConfigs','hooksConfig']:assert settings[k]==bs[k],(t['id'],k)
 assert launch['model_requested']=='gemini-3.8-flash' and launch['reasoning_requested']=='medium'
 assert launch['tools']==['observe','report'],launch['tools']
 assert DEFS[t['subcategory']] in (run/'prompt.txt').read_text()
 assert 'reference answer' not in (run/'prompt.txt').read_text().lower()
 assert hashlib.sha256((run/'after-agent.py').read_bytes()).hexdigest()==hashlib.sha256((Path(t['baseline_run'])/'after-agent.py').read_bytes()).hexdigest()
 return {'id':t['id'],'passed':True,'prompt_sha256':launch['prompt_sha256'],'recording':t['recording']}

def preflight():
 def one(t):
  job=B/'dry-noicl-v2'/t['id'];cmd=command(t,job,True)
  p=subprocess.run(cmd,env=ENV,cwd=C,capture_output=True,text=True);assert p.returncode==0,(t['id'],p.stderr[-600:]);return verify(t,job)
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(one,TASKS))
 write(B/'preflight-noicl.json',{'time':time.time(),'passed':len(results)==126,'model_calls':0,'tasks':results})
 print('PASS',len(results),'native dry-run configurations; zero model calls',flush=True)

def error_kind(job):
 s=''
 for p in [job/'launcher.log',job/'run/native-stderr.log']:
  if p.exists():
   with p.open('rb') as f:f.seek(max(0,p.stat().st_size-50000));s+='\n'+f.read().decode(errors='replace')
 p=job/'run/native-events.jsonl'
 if p.exists():
  with p.open('rb') as f:
   f.seek(max(0,p.stat().st_size-100000))
   for raw in f:
    try:e=json.loads(raw)
    except Exception:continue
    if e.get('type')=='error' or (e.get('type')=='result' and (e.get('error') or e.get('status')=='error')):s+='\n'+json.dumps(e)
 low=s.lower()
 if re.search(r'(?:http|status|code|error|"code")\W{0,10}(401|402|403|429)\b',low) or any(x in low for x in ['resource_exhausted','api_key_invalid','quota exceeded','invalid api key']):return 'provider authentication/billing/rate-limit STOP'
 if any(x in low for x in ['no space left on device','enospc','fetch failed','econnreset','etimedout']):return 'infrastructure STOP'
 return None

def terminate(p):
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()

def run():
 phase=B/'01-vla-noicl';phase.mkdir(exist_ok=True)
 assert read(B/'preflight-noicl.json')['passed']
 for n,h in read(B/'source-hashes.json').items():assert hashlib.sha256((C/n).read_bytes()).hexdigest()==h,n
 assert not (B/'STOP.json').exists()
 with (phase/'verified-resume-admission.consumed').open('x') as f:f.write(str(os.getpid()))
 args=mod.cli().parse_args(['--recordings','/home/ec2-user/vla-recordings/vla-ue-v1','--batch',str(phase),'--client','gemini','--model','gemini-3.8-flash','--replay-mode','vqa','--no-icl','--judge-python',str(C/'.venv/bin/python')])
 batch=mod.Batch(args)
 for t in TASKS:batch.state.setdefault(t['id'],{'status':'queued'})
 write(phase/'selection.json',{'tasks':[{k:v for k,v in t.items() if k not in ['scene','instruction']} for t in TASKS],'model':'gemini-3.8-flash','thinking':'medium','icl':False,'subcategory_definition':True,'workers':4})
 judgepool=concurrent.futures.ThreadPoolExecutor(max_workers=2);judges=[]
 def grade(t,job):
  import copy
  ga=copy.copy(args);ga.batch=job.parent.parent
  gb=mod.Batch(ga)
  try:
   jp=job/'judge.json'
   result=read(jp) if jp.exists() else gb.grade(t,PROFILES)
   batch.update(t['id'],judge=result,judge_error=None)
  except Exception as e:batch.update(t['id'],judge_error=str(e)[-500:])
 def stop(reason,tid):
  STOP.set();write(B/'STOP.json',{'time':time.time(),'reason':reason,'task':tid})
 def worker(t):
  if STOP.is_set() or (B/'STOP.json').exists():return
  tid=t['id'];job=phase/'cases'/tid
  attempt=1
  if job.exists():
   assert tid in ['A01','A02','A03','A04','A06','A07','A08'],tid
   job=phase/'infrastructure-recovery'/'cases'/tid;attempt=2
  assert not job.exists();job.mkdir(parents=True);start=time.time();batch.update(tid,status='running',started_at=start,attempt=attempt,run_dir=str(job/'run'))
  try:
   with (job/'launcher.log').open('w') as log:
    p=subprocess.Popen(command(t,job),cwd=C,env=ENV,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    batch.update(tid,launcher_pid=p.pid)
    while p.poll() is None:
     why=error_kind(job)
     if why:stop(why,tid)
     if time.time()-start>5400:stop('90-minute timeout',tid)
     if STOP.is_set() or (B/'STOP.json').exists():terminate(p);break
     time.sleep(2)
   why=error_kind(job)
   if why:stop(why,tid)
   launch=read(job/'run/launch.json');meta=read(job/'run/episode/meta.json') if (job/'run/episode/meta.json').exists() else {}
   verify(t,job)
   complete=p.returncode==0 and launch.get('status')=='completed' and meta.get('status')=='completed'
   if complete:
    calls=[json.loads(l) for l in (job/'run/episode/mcp-calls.jsonl').read_text().splitlines() if l.strip()]
    assert all(c['tool'] in ['observe','report'] for c in calls)
    assert any(c['tool']=='observe' and len(c.get('images',[]))>=120 and not c.get('is_error') for c in calls)
   status='completed' if complete else 'interrupted' if STOP.is_set() or (B/'STOP.json').exists() else 'failed'
   batch.update(tid,status=status,exit_code=p.returncode,elapsed_seconds=round(time.time()-start,1),tool_calls=meta.get('tool_calls'),flags_count=len(meta.get('flags',[])))
   if complete:judges.append(judgepool.submit(grade,t,job))
  except Exception as e:
   batch.update(tid,status='failed',error=repr(e));stop('orchestration/verification exception: '+repr(e),tid)
 for t in TASKS:
  if batch.state[t['id']]['status']=='completed' and not batch.state[t['id']].get('judge'):judges.append(judgepool.submit(grade,t,phase/'cases'/t['id']))
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,lambda *_:STOP.set())
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(worker,[t for t in TASKS if batch.state[t['id']]['status']=='queued']))
 judgepool.shutdown(wait=True);batch.summary(TASKS)
 write(phase/'finished.json',{'time':time.time(),'stopped':STOP.is_set() or (B/'STOP.json').exists(),'counts':dict(__import__('collections').Counter(v['status'] for v in batch.state.values()))})
if __name__=='__main__':
 if sys.argv[1]=='preflight':preflight()
 elif sys.argv[1]=='run':run()
