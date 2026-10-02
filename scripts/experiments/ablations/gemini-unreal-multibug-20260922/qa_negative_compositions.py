"""Exercise native composition rejection using invalid specs and zero model calls."""
from pathlib import Path
import copy,json,os,signal,subprocess,time
import qa_urban_reference as qa
B=qa.B;J=B/'composition-negative-reservation.json'
def main():
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,qa.stop)
 ref=next(t for t in json.loads((B/'reference-provenance.json').read_text())['tasks'] if t['id']=='U014');p=ref['profile']
 spec=json.loads((B/'draft-compositions/U014/AB.json').read_text());variants={}
 v=copy.deepcopy(spec);v['task_id']='wrong';variants['wrong_task']=v
 v=copy.deepcopy(spec);v['map']='/WrongMap';variants['wrong_map']=v
 v=copy.deepcopy(spec);v['additions'][0]['position'][0]+=1;variants['changed_normal_state']=v
 v=copy.deepcopy(spec);v['additions']*=2;variants['duplicate_actor']=v
 v=copy.deepcopy(spec);v['additions']*=3;variants['too_many_additions']=v
 v=copy.deepcopy(spec);v['additions'][0]['actor']='not_present';variants['missing_actor']=v
 results=[];lease=qa.Reservation('/home/ec2-user/unreal-production',J,[2]);proc=None
 try:
  lease.acquire()
  for name,value in variants.items():
   d=B/'composition-negative-qa'/name;d.mkdir(parents=True,exist_ok=False);qa.write(d/'invalid-spec.json',value)
   binary=B/'packages/urban-U014'/Path(p['binary']).relative_to(Path(p['binary']).parents[3]);args=[x for x in p.get('game_args',[])+p.get('extra_args',[]) if not x.lower().startswith(('-pixelstreaming','-graphicsadapter','-auditoripc','-abslog','-auditorremote','-resx','-resy'))]
   cmd=[str(binary),p['runtime_map'],'-RenderOffscreen','-windowed','-ResX=960','-ResY=540','-nosound','-unattended','-AuditorServe','-AuditorRemoteTask=U014','-AuditorIPC='+str(d),'-abslog='+str(d/'native.log'),'-graphicsadapter=2','-UserDir='+str(d/'user'),'-NoSaveConfig','-AuditorComposition='+str(d/'invalid-spec.json'),*args];qa.write(d/'launch-command.json',cmd)
   with (d/'stdout.log').open('w') as log:
    proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);qa.write(d/'process.json',{'pid':proc.pid,'time':time.time()});deadline=time.monotonic()+180
    try:
     while proc.poll() is None and time.monotonic()<deadline:
      if qa.STOP:raise InterruptedError('QA stop')
      qa.verify(J,2);time.sleep(.2)
     assert proc.poll()==73,('Expected explicit rejection exit',proc.poll())
     status=json.loads((d/'composition-status.json').read_text());assert status['status']=='rejected'
     results.append({'case':name,'exit_code':proc.returncode,'reason':status['reason'],'passed':True})
    finally:qa.terminate(proc);proc=None
   qa.write(B/'composition-negative-qa-status.json',{'model_calls':0,'tests':results,'status':'running'})
  qa.write(B/'composition-negative-qa-status.json',{'model_calls':0,'tests':results,'status':'passed'})
 except Exception as exc:
  qa.write(B/'composition-negative-qa-status.json',{'model_calls':0,'tests':results,'status':'needs_attention','error':repr(exc)});raise
 finally:qa.terminate(proc);lease.release()
if __name__=='__main__':main()
