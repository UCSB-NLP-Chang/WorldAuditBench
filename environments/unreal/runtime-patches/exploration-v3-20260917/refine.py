"""Refine only failed distance targets; retain explicit, measured exceptions."""
import concurrent.futures,copy,json,math,os,pathlib,signal,subprocess,time,sys
root=pathlib.Path(sys.argv[1]);rows=json.loads((root/'inventory.json').read_text())
def attempt(row,e,name):
 d=root/'refinement'/row['id']/name;d.mkdir(parents=True,exist_ok=True);report=d/'native.json';p=d/'policy.json';p.write_text(json.dumps({'tasks':{row['id']:e}}))
 if report.exists():return json.loads(report.read_text())
 cmd=[row['profile']['binary'],e['map']+'?Task='+('baseline' if e['case_type']!='bug' else row['id']),'-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorSkipSceneMenu','-AuditorExplorationPlan','-AuditorExplorationPolicy='+str(p),'-AuditorExplorationTask='+row['id'],'-AuditorExplorationReport='+str(report),'-abslog='+str(d/'native.log'),'-UserDir='+str(d/'userdata'),'-NoSaveConfig','-ExecCmds=t.MaxFPS 15']
 with (d/'stdout.log').open('w') as log:
  q=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);start=time.monotonic()
  try:
   while not report.exists() and q.poll() is None and time.monotonic()-start<60:time.sleep(.15)
   return json.loads(report.read_text()) if report.exists() else None
  finally:
   if q.poll() is None:
    os.killpg(q.pid,signal.SIGTERM)
    try:q.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(q.pid,signal.SIGKILL);q.wait()
def refine(row):
 tid=row['id'];d=root/'planning'/tid;e=json.loads((d/'policy-plan.json').read_text())['tasks'][tid];initial=json.loads((d/'result.json').read_text());best=None;desired=e['gain_cm'];exception=None;report_path=None
 if initial['status']=='PASS':best=json.loads((d/'native.json').read_text());report_path=str(d/'native.json')
 else:
  # A finer grid can traverse doorways and stairs skipped by the original grid.
  e['grid_cm']=max(20,e['grid_cm']/2);best=attempt(row,e,'fine-desired');report_path=str(root/'refinement'/tid/'fine-desired/native.json') if best else None
  if not best:
   old=row['old_cm']
   if old is None:old=math.dist(e['old_region_spawn'][:2],e['focus'][:2]) if e['case_type']=='bug' else 0
   low=max(0,row['current_cm']-old+25);high=desired;trial=copy.deepcopy(e);trial['gain_cm']=low;r=attempt(row,trial,'minimum-improvement')
   if r:
    best=r;e=trial;report_path=str(root/'refinement'/tid/'minimum-improvement/native.json')
    for n in range(5):
     gain=(low+high)/2;trial=copy.deepcopy(e);trial['gain_cm']=gain;r=attempt(row,trial,'bisect-'+str(n))
     if r:best=r;e=trial;low=gain;report_path=str(root/'refinement'/tid/('bisect-'+str(n))/'native.json')
     else:high=gain
    exception='Connected collision search found a farther start below the desired distance; no claim of global geometric maximum.'
   else:
    keep=copy.deepcopy(row['entry']);keep['bounds_min']=e['bounds_min'];keep['bounds_max']=e['bounds_max'];e=keep;exception='No farther connected spawn found at tested grid resolution; preserve the previously validated start and expand bounds only.'
 if best:
  e['spawn']=best['spawn'];e['yaw']=best['yaw'];e['route_to_old_spawn']=best['route_to_old_spawn']
 # Preserve the explicitly requested grass start for S01/B01: a farther position
 # on the lower plaza is not an acceptable substitute for this authored start.
 if tid in ['B01','S01'] and e['spawn'][2]<600:
  for k in ['spawn','yaw','route_to_old_spawn']:e[k]=row['entry'][k]
  exception='Preserve user-authored upper lawn start; the search proposed a lower-plaza point.';report_path=None;e['gain_cm']=row['entry']['gain_cm']
 e['requested_distance_cm']=((row['old_cm'] or 0)+desired);e['revision_exception']=exception
 result={'id':tid,'entry':e,'report_path':report_path,'exception':exception,'old_cm':row['old_cm'],'previous_cm':row['current_cm'],'new_cm':math.dist(e['spawn'][:2],e['focus'][:2])}
 out=root/'refined';out.mkdir(exist_ok=True);(out/(tid+'.json')).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ['entry','report_path']}),flush=True);return result
while not (root/'plan-summary.json').exists():time.sleep(1)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:result=list(pool.map(refine,rows))
policy={'version':'unreal-exploration-v3-20260917','frozen':True,'tasks':{r['id']:r['entry'] for r in result}}
(root/'policy.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2)+'\n');(root/'refine-summary.json').write_text(json.dumps(result,indent=2));print('REFINEMENT COMPLETE',len(result),flush=True)
