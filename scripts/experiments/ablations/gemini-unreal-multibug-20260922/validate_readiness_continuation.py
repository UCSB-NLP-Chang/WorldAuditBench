from pathlib import Path
from unittest.mock import patch
import json,time,copy
import readiness_continuation_guard as g
B=Path(__file__).resolve().parent

def main():
 a,progress,s=g.validate();old_read=Path.read_text;old_exists=Path.exists;old_digest=g.digest;cache={};first=a['dispatch_order'][0];done=a['preserved_completed'][0]
 def cached(p):
  p=Path(p);st=p.stat();k=(str(p),st.st_size,st.st_mtime_ns)
  if k not in cache:cache[k]=old_digest(p)
  return cache[k]
 out=[]
 for case in ['consumed','source_changed','completed_changed','prior_model_run','new_attempt_exists','QA_failed','lease_active','wrong_attempt']:
  def read(p,*args,**kwargs):
   text=old_read(p,*args,**kwargs)
   if p in [B/'progress.json',B/'readiness-fix-preflight/status.json',B/'reservation.json',B/'readiness-continuation-admission.json']:
    d=json.loads(text)
    if case=='completed_changed' and p==B/'progress.json':d['tasks'][done]['status']='failed'
    if case=='QA_failed' and p==B/'readiness-fix-preflight/status.json':d['status']='failed'
    if case=='lease_active' and p==B/'reservation.json':d['status']='active'
    if case=='wrong_attempt' and p==B/'readiness-continuation-admission.json':d['next_attempt'][first]=3
    return json.dumps(d)
   return text
  def exists(p):
   bad=(case=='consumed' and p==B/'readiness-continuation.consumed.json') or (case=='prior_model_run' and p==B/'cases/ABC__S06/attempt-1/run') or (case=='new_attempt_exists' and p==B/'cases'/first/('attempt-'+str(a['next_attempt'][first])))
   return bad or old_exists(p)
  def digest(p):return '0'*64 if case=='source_changed' and Path(p)==B/'coordinator_readiness_v2.py' else cached(p)
  try:
   with patch.object(Path,'read_text',read),patch.object(Path,'exists',exists),patch.object(g,'digest',digest):g.validate()
  except AssertionError:out.append({'case':case,'rejected':True})
  else:raise RuntimeError('Negative admitted:'+case)
 with (B/'readiness-continuation-validation.json').open('x') as f:f.write(json.dumps({'time':time.time(),'status':'passed','actual_positive':True,'negative_tests':out,'non_mutating_fault_injection':True,'model_calls':0,'admission_sha256':old_digest(B/'readiness-continuation-admission.json')},indent=2)+'\n')
 print('Actual continuation positive+8negative passed')
if __name__=='__main__':main()
