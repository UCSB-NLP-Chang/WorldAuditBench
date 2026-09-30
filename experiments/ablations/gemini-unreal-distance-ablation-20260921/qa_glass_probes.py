"""Rendered native route QA after the ICL batch; no model calls or live Review edits."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import copy,fcntl,hashlib,json,math,os,shutil,signal,subprocess,sys,threading,time,uuid
B=Path(__file__).resolve().parent;S=json.loads((B/'selection.json').read_text());STOP=threading.Event();LOCK=threading.Lock();RESULTS={}
sys.path.insert(0,str(B.parent/'gemini-unreal-icl-ablation-20260921/code'))
from batch_reservation import verify
from prepare_routes import profile

def write(p,j):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(j,indent=2));tmp.replace(p)
def terminate(p):
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
def corners(route):
 out=[]
 for i in range(1,len(route)):
  if i<len(route)-1:
   a=[route[i][k]-route[i-1][k] for k in (0,1)];b=[route[i+1][k]-route[i][k] for k in (0,1)]
   if abs(a[0]*b[1]-a[1]*b[0])<.1 and sum(x*y for x,y in zip(a,b))>0:continue
  out.append(route[i])
 return out
def route_from_arm(result,arm):
 full=result['route']
 if arm=='far':return full
 a=result['arms'][arm];offset=result['far_distance_cm']-a['remaining_route_cm'];passed=0
 for i,(p,q) in enumerate(zip(full,full[1:])):
  length=math.dist(p,q)
  if passed+length>=offset-.1:return [a['spawn'],*full[i+1:]]
  passed+=length
 raise ValueError('Arm is outside its frozen candidate route')
def run_arm(t,arm,slot):
 gpu=slot//2;tid=t['id'];geom=json.loads((B/'route-preparation'/tid/'result.json').read_text());assert geom['status']=='candidate_geometry_prepared'
 original=json.loads((Path(t['source_remote'])/'pinned-production/policies'/t['policy_sha256']).read_text())['tasks'][tid]
 e=copy.deepcopy(original if arm=='far' else geom['arms'][arm]['policy']);route=route_from_arm(geom,arm)
 d=B/'rendered-glass-probe-qa'/tid/arm;d.mkdir(parents=True,exist_ok=True)
 if (d/'result.json').exists():return json.loads((d/'result.json').read_text())
 pol=d/'policy.json';write(pol,{'version':'distance-rendered-qa-private','frozen':True,'tasks':{tid:e}})
 p=profile(t);args=[x for x in p.get('game_args',[])+p.get('extra_args',[]) if not x.lower().startswith(('-pixelstreaming','-graphicsadapter','-auditoripc','-abslog','-auditorremote','-auditorexploration','-resx','-resy'))]
 cmd=[p['binary'],t['map'],'-RenderOffscreen','-windowed','-ResX=960','-ResY=540','-nosound','-unattended','-AuditorServe','-AuditorRemoteTask='+tid,'-AuditorIPC='+str(d),'-AuditorExplorationPolicy='+str(pol),'-AuditorExplorationTask='+tid,'-AuditorExplorationReport='+str(d/'spawn-validation.json'),'-abslog='+str(d/'native.log'),'-graphicsadapter='+str(gpu),'-UserDir='+str(d/'user'),'-NoSaveConfig',*args]
 write(d/'launch-command.json',cmd);verify(B/'glass-probe-reservation.json',gpu)
 admission_deadline=time.monotonic()+180
 while True:
  if STOP.is_set():raise RuntimeError('QA stop requested')
  free=int(subprocess.check_output(['nvidia-smi','--id='+str(gpu),'--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip())
  if free>=6144:break
  if time.monotonic()>admission_deadline:raise RuntimeError('Not enough GPU memory for QA; no model was started')
  time.sleep(2)
 history=[];result={'id':tid,'arm':arm,'status':'running','visual_target_qa':'pending','trigger_state_qa':'pending','ready_for_model':False};start=time.monotonic()
 with (d/'stdout.log').open('w') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);write(d/'process.json',{'pid':proc.pid,'slot':slot,'started_at':time.time(),'command_sha256':hashlib.sha256(json.dumps(cmd).encode()).hexdigest()})
  def wait(req):
   deadline=time.monotonic()+90
   while time.monotonic()<deadline:
    if STOP.is_set():raise RuntimeError('QA stop requested')
    verify(B/'glass-probe-reservation.json',gpu)
    if proc.poll() is not None:raise RuntimeError('Native process exited')
    try:state=json.loads((d/'response.json').read_text())
    except (FileNotFoundError,json.JSONDecodeError):state={}
    if state.get('request_id')==req and state.get('paused') and state.get('frames'):
     if state.get('result') not in ['ok','ready','reset','blocked']:raise RuntimeError('Native response '+str(state.get('result')))
     return state
    time.sleep(.08)
   raise TimeoutError('Native action timed out')
  def save_frame(label,state):
   write(d/(label+'-state.json'),state);f=d/'observation.png'
   if not f.exists() and state.get('frames'):f=d/state['frames'][-1]['file']
   assert f.exists();shutil.copy2(f,d/(label+'.png'))
   lines=(d/'native.log').read_text(errors='replace').splitlines() if (d/'native.log').exists() else []
   evidence=[line for line in lines if any(tag in line for tag in ['AUDITOR_STATE_', 'AUDITOR_TASK_', 'AUDITOR_SCENARIO_', 'AUDITOR_OUT_OF_BOUNDS'])]
   write(d/(label+'-trigger-evidence.json'),{'simulation_time':state.get('simulation_time'),'native_log_markers':evidence,'image_sha256':hashlib.sha256((d/(label+'.png')).read_bytes()).hexdigest(),'absence_of_markers_proves_equivalence':False})
  def action(kind,value):
   q={'request_id':uuid.uuid4().hex,'action':kind,'value':value};write(d/'command.json',q);state=wait(q['request_id']);history.append({'action':q,'state':{k:v for k,v in state.items() if k!='frames'}});return state
  try:
   state=wait('');save_frame('initial',state)
   assert math.dist(state['position_cm'],e['spawn'])<10
   assert abs((state['yaw_degree']-e['yaw']+180)%360-180)<.2
   initial_time=state.get('simulation_time');visited=0
   for point in corners(route):
    for attempt in range(max(6,math.ceil(math.dist(state['position_cm'][:2],point[:2])/500)+4)):
     pos=state['position_cm'];distance=math.dist(pos[:2],point[:2])
     if distance<10:break
     yaw=math.degrees(math.atan2(point[1]-pos[1],point[0]-pos[0]));turn=(yaw-state['yaw_degree']+180)%360-180
     if abs(turn)>.1:state=action('turn',turn)
     before=state['position_cm'];state=action('move_up',min(distance,500))
     if math.dist(before[:2],state['position_cm'][:2])<1:raise RuntimeError('Movement blocked near '+str(point))
    if math.dist(state['position_cm'][:2],point[:2])>18:raise RuntimeError('Waypoint not reached: '+str(point))
    if tid=='A15' and abs(point[0]+1610)<1 and abs(point[1]-5340)<1:
     camera=state.get('camera_position_cm',state['position_cm']);focus=e['focus'];oldyaw=state['yaw_degree'];oldlook=state.get('look_degree',0)
     yaw=math.degrees(math.atan2(focus[1]-camera[1],focus[0]-camera[0]));state=action('turn',(yaw-oldyaw+180)%360-180)
     pitch=-math.degrees(math.atan2(focus[2]-camera[2],max(1,math.dist(camera[:2],focus[:2]))));state=action('look',pitch-state.get('look_degree',0));save_frame('common-approach-before',state)
     state=action('look',oldlook-state.get('look_degree',0));state=action('turn',(oldyaw-state['yaw_degree']+180)%360-180)
    visited+=1
   assert 'AUDITOR_OUT_OF_BOUNDS_RESET' not in (d/'native.log').read_text(errors='replace')
   save_frame('anchor-before-look',state)
   camera=state.get('camera_position_cm',state['position_cm']);focus=e['focus'];yaw=math.degrees(math.atan2(focus[1]-camera[1],focus[0]-camera[0]));turn=(yaw-state['yaw_degree']+180)%360-180
   if abs(turn)>.1:state=action('turn',turn)
   desired=-math.degrees(math.atan2(focus[2]-camera[2],max(1,math.dist(camera[:2],focus[:2]))));look=desired-state.get('look_degree',0)
   if abs(look)>.1:state=action('look',look)
   save_frame('target-view',state)
   def aim(label,focus=None):
    nonlocal state
    camera=state.get('camera_position_cm',state['position_cm']);focus=focus or e['focus'];yaw=math.degrees(math.atan2(focus[1]-camera[1],focus[0]-camera[0]));turn=(yaw-state['yaw_degree']+180)%360-180
    if abs(turn)>.1:state=action('turn',turn)
    desired=-math.degrees(math.atan2(focus[2]-camera[2],max(1,math.dist(camera[:2],focus[:2]))));look=desired-state.get('look_degree',0)
    if abs(look)>.1:state=action('look',look)
    save_frame(label,state)
   def walk_probe(points,label,allow_blocked=False):
    nonlocal state
    for index,point in enumerate(points):
     for _ in range(24):
      pos=state['position_cm'];distance=math.dist(pos[:2],point[:2])
      if distance<12:break
      yaw=math.degrees(math.atan2(point[1]-pos[1],point[0]-pos[0]));turn=(yaw-state['yaw_degree']+180)%360-180
      if abs(turn)>.1:state=action('turn',turn)
      before=state['position_cm'];state=action('move_up',min(distance,150))
      if math.dist(before[:2],state['position_cm'][:2])<1:
       aim(label+'-blocked-'+str(index))
       if allow_blocked:return False
       raise RuntimeError('Remaining probe blocked '+str(point))
     
     if math.dist(state['position_cm'][:2],point[:2])>=18:
      aim(label+'-unreached-'+str(index))
      if allow_blocked:return False
      raise RuntimeError('Probe waypoint not reached '+str(point))
     aim(label+'-waypoint-'+str(index))
    return True
   anchor=list(state['position_cm'])
   if tid=='S14':
    state=action('turn',180);state=action('idle',2)
    walk_probe(corners(list(reversed(geom['route']))),'leave')
    aim('before-return-detour')
    # The original return corridor is obstructed after the bin moves. Observe
    # the moved bin before taking a different native path within unchanged bounds.
    walk_probe([[400,4950,anchor[2]]],'return-approach')
    aim('moved-bin-before-detour')
    walk_probe([[400,5300,anchor[2]],[770,5300,anchor[2]],anchor],'return-detour')
    aim('return-detour-final')
   elif tid=='A15':
    state=action('turn',180);state=action('idle',2)
    walk_probe(corners(list(reversed(geom['route']))),'leave')
    idx=next(i for i,p in enumerate(geom['route']) if abs(p[0]+1610)<1 and abs(p[1]-5340)<1)
    walk_probe(corners(geom['route'][:idx+1]),'return-approach')
    aim('common-approach-after')
    # Preserve the blocked original return and observe from the valid approach;
    # this does not claim a full return to the now-obstructed inspection point.
   elif tid=='S22':
    # Published pinned-build walking QA uses the stair lane at x=-750.
    # All points are inside the unchanged S22 bounds; no teleport or jump.
    walk_probe([[-750,5300,anchor[2]],[-750,5700,anchor[2]],[-750,6100,anchor[2]],[0,6100,anchor[2]]],'published-stair-lane')
    aim('upper-lawn-backside-target')
    walk_probe([[-750,6100,state['position_cm'][2]],[-750,5700,anchor[2]],[-750,5300,anchor[2]],anchor],'return-front-via-stairs')
    aim('front-restored-target')
   elif tid=='U021':
    walk_probe([[600,-1100,anchor[2]],[1500,-1100,anchor[2]],[1560,-1250,anchor[2]]],'published-glass-approach')
    aim('glass-side-a',[1000,-1655,180])
    walk_probe([[1660,-1400,anchor[2]]],'glass-sideways')
    aim('glass-side-b',[1000,-1655,180])
    walk_probe([[1560,-1250,anchor[2]]],'glass-return')
    aim('glass-side-a-restored',[1000,-1655,180])
   elif tid=='H08':
    # QA-only closer path around table/chairs, preserving task policy.
    walk_probe([[-245,-810,anchor[2]],[-300,-810,anchor[2]],[-300,-660,anchor[2]],[-245,-660,anchor[2]]],'closer-left-of-table')
    aim('inside-threshold-target')
    walk_probe([[-300,-660,anchor[2]],[-300,-810,anchor[2]],[-245,-810,anchor[2]],anchor],'outside-threshold-return')
    aim('outside-threshold-target')
   elif tid=='H11':
    departure=json.loads((B/'route-preparation/H11/departure-path-v4/native.json').read_text())['route_to_old_spawn']
    state=action('turn',180);state=action('idle',2)
    walk_probe([departure[-1]],'to-departure-root')
    walk_probe(corners(list(reversed(departure))),'verified-departure')
    state=action('turn',180);state=action('idle',2);aim('farther-away-target')
    walk_probe(corners(departure),'verified-return');walk_probe([anchor],'restore-anchor');aim('farther-return-target')
   elif tid=='R05':
    for pitch in [-10,-20,-30,-40,-50,-60]:
     aim('canopy-base-'+str(abs(pitch)))
     state=action('look',pitch-state.get('look_degree',0));save_frame('canopy-centered-'+str(abs(pitch)),state)
     state=action('turn',35);save_frame('canopy-offset-'+str(abs(pitch)),state)
   elif tid=='R03':
    points=corners(list(reversed(geom['route'])))
    # Back off on the already validated route so the tall panel fits in frame.
    for index,point in enumerate(points[:3]):
     walk_probe([point],'backoff-'+str(index))
     for pitch in [-15,-30,-45,-60]:
      aim('backoff-'+str(index)+'-base')
      state=action('look',pitch-state.get('look_degree',0));save_frame('panel-'+str(index)+'-pitch-'+str(abs(pitch)),state)
   assert 'AUDITOR_OUT_OF_BOUNDS_RESET' not in (d/'native.log').read_text(errors='replace')
   result.update(status='route_passed_pending_visual_and_trigger_review',spawn=e['spawn'],yaw=e['yaw'],inspection_anchor=state['position_cm'],waypoints_walked=visited,initial_simulation_time=initial_time,final_simulation_time=state.get('simulation_time'),bounds_unchanged=True,actor_digest_comparison='Not used: includes player position; not a target-state equivalence test.')
  except Exception as exc:result.update(status='needs_resolution',error=str(exc))
  finally:terminate(proc)
 result.update(elapsed_seconds=time.monotonic()-start,actions=history);write(d/'result.json',result)
 with LOCK:
  RESULTS[tid+'/'+arm]={k:v for k,v in result.items() if k!='actions'};write(B/'glass-probe-progress.json',{'updated_at':time.time(),'pid':os.getpid(),'total':3,'processed':len(RESULTS),'tasks':RESULTS,'ready_for_model':False})
 print(tid,arm,result['status'],result.get('error',''),flush=True);return result

def worker(slot,tasks):
 for t in tasks:
  for arm in ['far','near','medium']:
   if STOP.is_set():return
   try:run_arm(t,arm,slot)
   except Exception as exc:
    with LOCK:
     RESULTS[t['id']+'/'+arm]={'id':t['id'],'arm':arm,'status':'needs_resolution','error':str(exc),'ready_for_model':False}
     d=B/'rendered-glass-probe-qa'/t['id']/arm;d.mkdir(parents=True,exist_ok=True);write(d/'result.json',RESULTS[t['id']+'/'+arm])
     write(B/'glass-probe-progress.json',{'updated_at':time.time(),'pid':os.getpid(),'total':3,'processed':len(RESULTS),'tasks':RESULTS,'ready_for_model':False})
    print(t['id'],arm,'setup failure',repr(exc),flush=True)
if __name__=='__main__':
 lock=(B/'glass-probe.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,lambda *_:STOP.set())
 for gpu in [0,1,2,3]:verify(B/'glass-probe-reservation.json',gpu)
 for f in (B/'rendered-glass-probe-qa').glob('*/*/result.json'):
  v=json.loads(f.read_text());RESULTS[v['id']+'/'+v['arm']]={k:x for k,x in v.items() if k!='actions'}
 with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda i:worker(i,[t for t in S['tasks'] if t['id'] in ['U021']][i::8]),range(8)))
 write(B/'glass-probe.finished',{'time':time.time(),'processed':len(RESULTS),'stopped':STOP.is_set(),'ready_for_model':False,'note':'Requires target visibility and temporal-trigger review before paid episodes.'})
