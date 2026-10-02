"""Exercise the real streaming run() with mocked native processes and judges; no APIs."""
import ast,types,tempfile,json,threading,concurrent.futures,time,signal,hashlib,os,sys
from pathlib import Path
source=Path(__file__).with_name('streaming_replay.py').read_text()
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='run')
results=[]
for scenario in ['overlap_and_delayed_input','preserve_terminal','root_stop','phase_stop','provider_stop']:
 with tempfile.TemporaryDirectory() as tmp:
  b=Path(tmp);phase=b/'04-vla-half';phase.mkdir();c=b/'code';c.mkdir()
  def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
  def read(p):return json.loads(p.read_text())
  write(b/'source-hashes.json',{});write(b/'streaming-admission.json',{'approved':True,'phases':['04-vla-half'],'files':{}})
  event=threading.Event();launches=[];grades=[];live=[];state={};ready={'T1'}
  if scenario=='preserve_terminal':state={'T1':{'status':'failed'},'T2':{'status':'completed','judge':{'score':0}}};ready={'T3'}
  if scenario=='root_stop':write(b/'STOP.json',{})
  if scenario=='phase_stop':write(phase/'STOP.json',{})
  tasks=[{'id':f'T{i}','frame_count':2} for i in range(1,4)]
  class Batch:
   def __init__(self,args):self.state=state;self.lock=threading.Lock()
   def update(self,tid,**kw):
    with self.lock:self.state.setdefault(tid,{}).update(kw)
   def grade(self,t,profiles):
    grades.append((t['id'],(phase/'recordings.finished.json').exists()));return {'score':1,'reason':'mock'}
   def summary(self,t):pass
  class Proc:
   def __init__(self,cmd,**kw):
    tid=cmd;self.pid=999999;self.returncode=None;self.polls=0;launches.append(tid);live.append(self)
    job=phase/'cases'/tid;write(job/'run/launch.json',{'status':'completed'});write(job/'run/episode/meta.json',{'status':'completed','tool_calls':3,'flags':[]})
    (job/'run/episode/mcp-calls.jsonl').write_text('\n'.join(json.dumps(x) for x in [{'tool':'read_example','images':['example']},{'tool':'observe','images':['f1','f2']},{'tool':'report'}]))
   def poll(self):
    self.polls+=1
    if self.polls>=3:self.returncode=0
    return self.returncode
  def stopped():return event.is_set() or (b/'STOP.json').exists() or (phase/'STOP.json').exists()
  def terminate(p):p.returncode=-15
  def sleep(_):
   if scenario=='overlap_and_delayed_input' and grades:ready.update({'T2','T3'})
   time.sleep(.002)
  cli=types.SimpleNamespace(parse_args=lambda _:types.SimpleNamespace(batch=phase))
  seq=types.ModuleType('sequence');seq.validate_admission=lambda:None;sys.modules['sequence']=seq
  ns=dict(B=b,C=c,PHASE=phase.name,TASKS=tasks,STOP=event,read=read,write=write,hashlib=hashlib,os=os,mod=types.SimpleNamespace(cli=lambda:cli,Batch=Batch),PROFILES={},concurrent=concurrent,signal=signal,json=json,ENV={},command=lambda t,j:t['id'],verify=lambda *_:None,prepare_ready=lambda *_:None,recording_ready=lambda t:t['id'] in ready,stop_active=stopped,terminate=terminate,time=types.SimpleNamespace(time=time.time,sleep=sleep),subprocess=types.SimpleNamespace(Popen=Proc,STDOUT=-2),error_kind=lambda job:'provider authentication/billing/rate-limit STOP' if scenario=='provider_stop' else None)
  exec(compile(ast.Module(body=[node],type_ignores=[]),'<real streaming run>','exec'),ns)
  if scenario in ['root_stop','phase_stop']:
   try:ns['run']();raise RuntimeError('STOP was ignored')
   except AssertionError:pass
   assert not launches
  else:
   ns['run']()
   assert len(launches)==len(set(launches))
   if scenario=='overlap_and_delayed_input':assert set(launches)=={'T1','T2','T3'} and len(grades)==3 and all(not x[1] for x in grades)
   if scenario=='preserve_terminal':assert launches==['T3'] and state['T1']['status']=='failed' and state['T2']['judge']=={'score':0}
   if scenario=='provider_stop':assert launches==['T1'] and not grades and read(b/'STOP.json')['reason'].startswith('provider')
  results.append({'case':scenario,'passed':True,'native_launches':launches,'graded':[x[0] for x in grades]})
print(json.dumps({'passed':True,'model_calls':0,'cases':results},indent=2))
