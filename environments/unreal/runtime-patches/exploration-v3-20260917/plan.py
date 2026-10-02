"""Private NullRHI planning; never writes a live policy or uses a GPU."""
import argparse,concurrent.futures,copy,json,math,os,pathlib,signal,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--workers',type=int,default=3);p.add_argument('--ids',nargs='*');a=p.parse_args();root=a.root;rows=json.loads((root/'inventory.json').read_text())
def run(row):
 tid=row['id'];d=root/'planning'/tid;d.mkdir(parents=True,exist_ok=True)
 if (d/'result.json').exists():return json.loads((d/'result.json').read_text())
 e=copy.deepcopy(row['entry']);old=row['old_cm']
 if old is None:old=0 if e['case_type']!='bug' else math.dist(e['old_region_spawn'][:2],e['focus'][:2])
 for i in [0,1]:
  center=(e['old_bounds_max'][i]+e['old_bounds_min'][i])/2;half=(e['old_bounds_max'][i]-e['old_bounds_min'][i])*math.sqrt(3)/2
  e['bounds_min'][i]=min(e['bounds_min'][i],center-half);e['bounds_max'][i]=max(e['bounds_max'][i],center+half)
 addition=300 if e['family']=='indoor' else 600
 required=max(old*2,row['current_cm']+addition);e['gain_cm']=required-old;e['max_route_cm']=max(8000,e['gain_cm']*4)
 for key in ['spawn','yaw','route_to_old_spawn']:e.pop(key,None)
 policy={'version':'unreal-exploration-v3-plan','tasks':{tid:e}};(d/'policy-plan.json').write_text(json.dumps(policy));report=d/'native.json'
 cmd=[row['profile']['binary'],e['map']+'?Task='+('baseline' if e['case_type']!='bug' else tid),'-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorSkipSceneMenu','-AuditorExplorationPlan','-AuditorExplorationPolicy='+str(d/'policy-plan.json'),'-AuditorExplorationTask='+tid,'-AuditorExplorationReport='+str(report),'-abslog='+str(d/'native.log'),'-UserDir='+str(d/'userdata'),'-NoSaveConfig','-ExecCmds=t.MaxFPS 15']
 (d/'command.json').write_text(json.dumps(cmd));start=time.time()
 with (d/'stdout.log').open('w') as log:
  q=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   while not report.exists() and q.poll() is None and time.time()-start<100:time.sleep(.25)
   if report.exists():
    r=json.loads(report.read_text());assert r['status']=='planned' and r['id']==tid
    result={'id':tid,'status':'PASS','old_cm':r['old_distance_cm'],'current_cm':row['current_cm'],'new_cm':r['distance_cm'],'elapsed':time.time()-start}
   else:
    logs=(d/'native.log').read_text(errors='replace') if (d/'native.log').exists() else ''
    result={'id':tid,'status':'FAIL','elapsed':time.time()-start,'error':[l for l in logs.splitlines() if 'AUDITOR_EXPLORATION_FAIL' in l][-2:]}
  finally:
   if q.poll() is None:
    os.killpg(q.pid,signal.SIGTERM)
    try:q.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(q.pid,signal.SIGKILL);q.wait()
 (d/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:r=list(pool.map(run,[x for x in rows if not a.ids or x['id'] in a.ids]))
(root/'plan-summary.json').write_text(json.dumps(r,indent=2));print('FINISHED',len(r),sum(x['status']=='PASS' for x in r),flush=True)
