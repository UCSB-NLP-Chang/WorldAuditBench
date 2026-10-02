"""Private CPU/NullRHI route candidates. This is not rendered traversal or trigger QA."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,copy,json,math,os,signal,subprocess,time,threading,hashlib
B=Path(__file__).resolve().parent;S=json.loads((B/'selection.json').read_text());INV={r['id']:r for r in json.loads((B/'reference-policy-inventory.json').read_text())['tasks']};LOCK=threading.Lock();RESULTS={}
def write(p,d):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(d,indent=2));tmp.replace(p)
def profile(t):
 root=Path(t['source_remote'])/'pinned-production';found=[]
 for name in ['audit/runtime.json','shared/runtime-prod.json']:
  r=json.loads((root/name).read_text())
  for p in r['launch_profiles'].values():
   if p.get('build_sha256')==t['build_sha256'] and '-AuditorExplorationTask='+t['id'] in p.get('extra_args',[]):
    if p not in found:found.append(p)
 assert len(found)==1,(t['id'],len(found));return found[0]
def native(t,e,stage,planning=False):
 job=B/'route-preparation'/t['id']/stage;job.mkdir(parents=True,exist_ok=True);report=job/'native.json'
 if report.exists():return json.loads(report.read_text())
 if (job/'native.log').exists() and 'AUDITOR_EXPLORATION_FAIL' in (job/'native.log').read_text(errors='replace'):raise RuntimeError('Previously recorded native geometry failure; preserve it and resolve with a separate candidate stage')
 pol=job/'policy.json';write(pol,{'version':'private-distance-route-preparation','frozen':not planning,'tasks':{t['id']:e}})
 p=profile(t);cmd=[p['binary'],t['map'],'-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorSkipSceneMenu','-AuditorExplorationPolicy='+str(pol),'-AuditorExplorationTask='+t['id'],'-AuditorExplorationReport='+str(report),'-abslog='+str(job/'native.log'),'-UserDir='+str(job/'userdata'),'-NoSaveConfig','-ExecCmds=t.MaxFPS 15']
 if planning:cmd.append('-AuditorExplorationPlan')
 write(job/'command.json',cmd)
 with (job/'stdout.log').open('w') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);write(job/'process.json',{'pid':proc.pid,'created_at':time.time()});start=time.monotonic()
  try:
   while time.monotonic()-start<100 and proc.poll() is None and not report.exists():time.sleep(.2)
   if not report.exists():
    lines=(job/'native.log').read_text(errors='replace').splitlines() if (job/'native.log').exists() else []
    raise RuntimeError('No native report: '+'; '.join(x for x in lines if 'AUDITOR_EXPLORATION_FAIL' in x)[-1500:])
   d=json.loads(report.read_text());assert d['id']==t['id'] and d['status']==('planned' if planning else 'validated');return d
  finally:
   if proc.poll() is None:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
def point_at(route,distance):
 for a,b in zip(route,route[1:]):
  length=math.dist(a,b)
  if distance<=length:return [x+(y-x)*distance/length for x,y in zip(a,b)] if length else a
  distance-=length
 return route[-1]
def run(t):
 tid=t['id'];e=copy.deepcopy(INV[tid]['policy']);override=json.loads((B/'route-overrides.json').read_text()).get(tid,{}) if (B/'route-overrides.json').exists() else {};stage_prefix=override.get('stage_prefix','');result={'id':tid,'native_route_qa':False,'trigger_qa':False,'status':'preparing'}
 try:
  far=native(t,e,'far-start-check');assert math.dist(far['spawn'],e['spawn'])<.1 and far['bounds_min']==e['bounds_min'] and far['bounds_max']==e['bounds_max']
  plan=copy.deepcopy(e)
  for k in ['spawn','yaw','route_to_old_spawn']:plan.pop(k,None)
  plan.update(gain_cm=override.get('inspection_distance_cm',180)-far['old_distance_cm'],grid_cm=override.get('planning_grid_cm',50),max_route_cm=10000)
  target=native(t,plan,stage_prefix+'inspection-anchor-plan',True)
  route=copy.deepcopy(e['route_to_old_spawn']);extension=list(reversed(target['route_to_old_spawn']))
  assert route and extension and math.dist(route[-1],extension[0])<12,(tid,'route anchors differ')
  assert math.dist(route[0],e['spawn'])<12,(tid,'stored route does not begin at current Far spawn')
  route=route+extension[1:]
  # Remove exact repeated lattice vertices; geometric shortcuts still need native traversal QA.
  clean=[];seen={}
  for p in route:
   key=tuple(round(v,1) for v in p)
   if key in seen:
    clean=clean[:seen[key]+1];seen={tuple(round(v,1) for v in q):i for i,q in enumerate(clean)}
   else:seen[key]=len(clean);clean.append(p)
  route=clean;D=sum(math.dist(a,b) for a,b in zip(route,route[1:]));assert D>100
  result.update(status='candidate_geometry_prepared',far_distance_cm=D,inspection_anchor=target['spawn'],inspection_anchor_distance_cm=target['distance_cm'],route=route,arms={})
  for name,fraction in [('near',1/3),('medium',2/3)]:
   candidate=copy.deepcopy(e);candidate['spawn']=point_at(route,D*(1-fraction));candidate['yaw']=e['yaw']
   # Do not claim this inherited route describes the candidate start.
   candidate.pop('route_to_old_spawn',None)
   effective_remaining=D*fraction;adjustment=None
   try:report=native(t,candidate,stage_prefix+name+'-start-check')
   except RuntimeError as original_error:
    # Interpolation across stair risers need not lie on the floor. Try nearby
    # vertices on the same route, within 1m of the intended route position.
    cumulative=[0]
    for a,z in zip(route,route[1:]):cumulative.append(cumulative[-1]+math.dist(a,z))
    choices=sorted(range(len(route)),key=lambda i:abs(cumulative[i]-D*(1-fraction)))
    report=None
    for index in choices[:4]:
     offset=abs(cumulative[index]-D*(1-fraction))
     if offset>100:continue
     candidate['spawn']=route[index]
     try:report=native(t,candidate,stage_prefix+name+'-route-vertex-'+str(index))
     except RuntimeError:continue
     effective_remaining=D-cumulative[index];adjustment={'reason':str(original_error),'route_offset_cm':offset,'vertex_index':index};break
    if report is None:raise RuntimeError('No safe route vertex within 1m of requested '+name+' start')
   assert math.dist(report['spawn'],candidate['spawn'])<.1
   assert report['bounds_min']==e['bounds_min'] and report['bounds_max']==e['bounds_max'] and abs(report['yaw']-e['yaw'])<.1
   result['arms'][name]={'spawn':candidate['spawn'],'remaining_route_cm':effective_remaining,'effective_fraction':effective_remaining/D,'geometry_adjustment':adjustment,'native_floor_and_capsule_check':'passed','policy':candidate,'rendered_route_qa':False,'trigger_state_qa':False}
  result['note']='Candidate only: native floor/capsule checks do not establish rendered target observability, full traversal, dynamic trigger equivalence or a shortest route.'
 except Exception as exc:result.update(status='needs_route_resolution',error=str(exc))
 job=B/'route-preparation'/tid;job.mkdir(parents=True,exist_ok=True);write(job/'result.json',result)
 with LOCK:
  RESULTS[tid]=result;write(B/'route-preparation-progress.json',{'updated_at':time.time(),'pid':os.getpid(),'total':len(S['tasks']),'processed':len(RESULTS),'candidate_geometry_prepared':sum(v['status']=='candidate_geometry_prepared' for v in RESULTS.values()),'tasks':{k:{x:v[x] for x in ['id','status','error'] if x in v} for k,v in RESULTS.items()}})
 print(tid,result['status'],result.get('error',''),flush=True);return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--ids',nargs='*');args=p.parse_args();TASKS=[t for t in S['tasks'] if not args.ids or t['id'] in args.ids]
 for f in (B/'route-preparation').glob('*/result.json'):
  v=json.loads(f.read_text());RESULTS[v['id']]=v
 with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,TASKS))
 write(B/'route-preparation.finished',{'time':time.time(),'processed':len(RESULTS),'note':'Geometry preparation only; no model run or rendered/trigger QA yet.'})
