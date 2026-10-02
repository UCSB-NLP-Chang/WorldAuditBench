"""Exercise corrected coordinator readiness on three pre-model failures, intercept all model launches."""
from pathlib import Path
import importlib.util,json,time,copy
B=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('coordinator_readiness_fix',B/'coordinator_readiness_v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ORIGINAL=B;D=B/'readiness-fix-preflight';m.B=D
REAL_POPEN=m.subprocess.Popen;INTERCEPTED=[]
def popen(cmd,*args,**kwargs):
 if any(str(x).endswith('launch_composition.py') for x in cmd):
  INTERCEPTED.append([str(x) for x in cmd]);raise RuntimeError('PREFLIGHT_MODEL_INTERCEPT_NO_CALL')
 return REAL_POPEN(cmd,*args,**kwargs)
m.subprocess.Popen=popen

def main():
 assert not D.exists();D.mkdir();s=json.loads((ORIGINAL/'episodes-selection.json').read_text());by={t['id']:t for t in s['tasks']};out={'status':'running','model_calls':0,'cases':[]}
 lease=m.Reservation(Path('/home/ec2-user/unreal-production'),D/'reservation.json',[0])
 try:
  lease.acquire()
  for tid in ['ABC__S06','AB__I15','ABC__A02']:
   t=copy.deepcopy(by[tid]);t['composition_spec']=str(ORIGINAL/t['composition_spec']);before=len(INTERCEPTED)
   m.attempt(t,0,1)
   job=D/'cases'/tid/'attempt-1'
   assert len(INTERCEPTED)==before+1 and (job/'composition-verification.json').exists() and not (job/'run').exists()
   out['cases'].append({'id':tid,'composition_verified_before_intercept':True,'model_calls':0});(D/'status.json').write_text(json.dumps(out,indent=2)+'\n')
  out['status']='passed'
 finally:lease.release();out['time']=time.time();(D/'status.json').write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
