"""Private native geometry planning only; no model calls and no baseline mutation."""
from pathlib import Path
import copy,json,math,os,signal,subprocess,time
B=Path(__file__).resolve().parent

def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def plan(ref,target,grid=50,output_root=None):
 tid=ref['id'];label=target['label'];stage=label if grid==50 else label+'-grid'+str(grid);job=(output_root or B/'composition-route-plans')/tid/stage;job.mkdir(parents=True,exist_ok=False)
 base=B.parent/'gemini-unreal-distance-ablation-20260921/route-preparation'/tid/'far-start-check/native.json';prior=json.loads(base.read_text());assert prior['status']=='validated'
 e=copy.deepcopy(ref['policy']);e['focus']=target['normal_state']['center']
 for k in ['spawn','yaw','route_to_old_spawn']:e.pop(k,None)
 e.update(gain_cm=220-math.dist(prior['old_spawn'][:2],e['focus'][:2]),grid_cm=grid,max_route_cm=10000)
 policy=job/'policy.json';report=job/'native.json';write(policy,{'version':'multibug-private-route-plan','frozen':False,'tasks':{tid:e}})
 p=ref['profile'];args=[x for x in p.get('game_args',[])+p.get('extra_args',[]) if not x.lower().startswith(('-pixelstreaming','-graphicsadapter','-auditoripc','-abslog','-auditorremote','-auditorexploration','-resx','-resy','-rendersoffscreen','-renderoffscreen'))]
 cmd=[p['binary'],p['runtime_map'],'-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorSkipSceneMenu','-AuditorExplorationPolicy='+str(policy),'-AuditorExplorationTask='+tid,'-AuditorExplorationReport='+str(report),'-AuditorExplorationPlan','-abslog='+str(job/'native.log'),'-UserDir='+str(job/'user'),'-NoSaveConfig','-ExecCmds=t.MaxFPS 15',*args]
 write(job/'command.json',cmd)
 with (job/'stdout.log').open('w') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);write(job/'process.json',{'pid':proc.pid,'time':time.time(),'models_started':0})
  try:
   end=time.monotonic()+120
   while time.monotonic()<end and proc.poll() is None and not report.exists():time.sleep(.2)
   if not report.exists():raise RuntimeError('No native planning report')
   r=json.loads(report.read_text());assert r['status']=='planned' and 190<=r['distance_cm']<=450,('Inspection distance outside 190–450 cm',r.get('distance_cm'))
   original_route=ref['policy']['route_to_old_spawn'];extension=list(reversed(r['route_to_old_spawn']))
   assert math.dist(original_route[-1],extension[0])<12,'Route roots differ'
   assert r['bounds_min']==ref['policy']['bounds_min'] and r['bounds_max']==ref['policy']['bounds_max']
   result={'id':tid,'label':label,'status':'geometry_candidate_pending_rendered_traversal','route':original_route+extension[1:],'inspection_anchor':r['spawn'],'normal_focus':e['focus'],'models_started':0}
  except Exception as exc:result={'id':tid,'label':label,'status':'needs_resolution','error':repr(exc),'models_started':0}
  finally:
   if proc.poll() is None:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
 write(job/'result.json',result);print(tid,label,result['status'],result.get('error',''),flush=True)
 return result

def main():
 refs={t['id']:t for t in json.loads((B/'reference-provenance.json').read_text())['tasks']}
 results=[]
 for tid in ['U014','U015','U032']:
  for target in json.loads((B/'draft-compositions'/tid/'targets.json').read_text())['additions']:results.append(plan(refs[tid],target))
 write(B/'composition-route-plans-status.json',{'tasks':results,'models_started':0,'time':time.time()})
if __name__=='__main__':main()
