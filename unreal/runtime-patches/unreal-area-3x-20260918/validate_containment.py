from pathlib import Path
import json,subprocess,time,signal,os,math,uuid,traceback
root=Path(__file__).parent
profiles=json.loads((root/'qa-profiles.json').read_text());policy=json.loads((root/'policy.json').read_text())
results=[]
for tid,e in policy['tasks'].items():
 if tid not in ['HB01','HB02','HB03','B01']:continue
 if os.environ.get('QA_FAMILY') and e['family']!=os.environ['QA_FAMILY']:continue
 d=root/'containment-qa'/tid;d.mkdir(parents=True,exist_ok=True)
 if (d/'result.json').exists():results.append(json.loads((d/'result.json').read_text()));continue
 prof=profiles[tid]['profile'];cmd=[prof['binary'],prof['runtime_map'],'-RenderOffscreen','-windowed','-ResX=640','-ResY=360','-nosound','-unattended','-AuditorServe','-AuditorIPC='+str(d),'-AuditorExplorationPolicy='+str(root/'policy.json'),'-AuditorExplorationTask='+tid,'-AuditorExplorationReport='+str(d/'validation.json'),'-abslog='+str(d/'native.log'),'-graphicsadapter=0','-UserDir='+str(d/'user')]+prof['game_args']
 f=(d/'stdout.log').open('w');p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);history=[]
 def read():
  try:return json.loads((d/'response.json').read_text())
  except:return {}
 def wait(req):
  end=time.monotonic()+90
  while time.monotonic()<end:
   r=read()
   if r.get('request_id')==req and r.get('paused') and r.get('frames'):return r
   if p.poll() is not None:raise RuntimeError('Native process exited')
   time.sleep(.08)
  raise RuntimeError('Native command timed out')
 def action(kind,val):
  q={'request_id':uuid.uuid4().hex,'action':kind,'value':val};tmp=d/'command.tmp';tmp.write_text(json.dumps(q));tmp.replace(d/'command.json');r=wait(q['request_id']);history.append({'action':q,'position':r['position_cm'],'clearance':r['boundary_clearance_cm'],'result':r['result']});return r
 try:
  state=wait('');start=state['position_cm'];assert math.dist(start,e['spawn'])<10
  route=e.get('route_to_old_spawn',[]);points=[]
  for i in range(1,len(route)):
   if i<len(route)-1:
    a=[route[i][j]-route[i-1][j] for j in (0,1)];b=[route[i+1][j]-route[i][j] for j in (0,1)]
    if abs(a[0]*b[1]-a[1]*b[0])<.1 and sum(a[j]*b[j] for j in (0,1))>0:continue
   points.append(route[i])
  for point in points:
   for attempt in range(6):
    pos=state['position_cm'];distance=math.dist(pos[:2],point[:2])
    if distance<10:break
    yaw=math.degrees(math.atan2(point[1]-pos[1],point[0]-pos[0]));turn=(yaw-state['yaw_degree']+180)%360-180
    if abs(turn)>.1:state=action('turn',turn)
    state=action('move_up',min(distance,1500))
   if math.dist(state['position_cm'][:2],point[:2])>18:raise RuntimeError('Unreachable waypoint '+str(point)+' actual '+str(state['position_cm']))
  def goto(x,y):
   global state
   for attempt in range(6):
    pos=state['position_cm'];distance=math.dist(pos[:2],[x,y])
    if distance<10:return
    yaw=math.degrees(math.atan2(y-pos[1],x-pos[0]));turn=(yaw-state['yaw_degree']+180)%360-180
    if abs(turn)>.1:state=action('turn',turn)
    state=action('move_up',min(distance,1500))
   assert math.dist(state['position_cm'][:2],[x,y])<18, ('Blocked passage',state['position_cm'],[x,y])
  def block(x,y,axis,bound):
   global state
   pos=state['position_cm'];yaw=math.degrees(math.atan2(y-pos[1],x-pos[0]));turn=(yaw-state['yaw_degree']+180)%360-180
   state=action('turn',turn);state=action('move_up',math.dist(pos[:2],[x,y]))
   assert abs(state['position_cm'][axis]-bound)<4, ('Containment ineffective',state['position_cm'],axis,bound)
   assert abs(state['boundary_clearance_cm'])<4,state
   assert e['old_bounds_min'][2]<state['position_cm'][2]<e['old_bounds_max'][2],state
  if tid=='HB01':
   for xy in [(-1040,-660),(-1040,-410),(-890,-410),(-890,-460),(-685,-460),(-685,-960)]:goto(*xy)
   block(-865,-960,0,-740)
   for xy in [(-685,-960),(-685,-1030),(-505,-1042),(-685,-1030),(-685,-460),(-890,-460),(-890,-410),(-1040,-410),(-1040,-660),(-1090,-660)]:goto(*xy)
  elif tid=='HB02':
   for xy in [(-260,-650),(-300,-450),(-490,-450),(-590,-450)]:goto(*xy)
   block(-900,-450,0,-600)
   for xy in [(-490,-450),(-300,-450),(-260,-650),(-110,-810)]:goto(*xy)
  elif tid=='HB03':
   for xy in [(-1000,-650),(-1000,-475),(-865,-475)]:goto(*xy)
   block(-865,-800,1,-505)
   for xy in [(-865,-475),(-1000,-475),(-1000,-650),(-1050,-650)]:goto(*xy)
  else:
   for xy in [(-300,4600),(-300,4800),(-300,5300),(-750,5300),(-750,5700),(-750,6100),(-350,6100),(-350,6200)]:goto(*xy)
   block(-350,6500,1,6220)
   for xy in [(-350,6100),(-750,6100),(-750,5700),(-750,5300),(-300,5300),(-300,4800),(-300,4600),(0,4600)]:goto(*xy)
  assert 'AUDITOR_OUT_OF_BOUNDS_RESET' not in (d/'native.log').read_text(), 'Unexpected boundary recovery'
  result={'id':tid,'status':'PASS','spawn':start,'end':state['position_cm'],'spawn_clearance':min(start[j]-e['bounds_min'][j]-30 for j in (0,1)),'actions':history}
 except Exception as exc:result={'id':tid,'status':'FAIL','error':str(exc),'actions':history}
 finally:
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  f.close()
 (d/'result.json').write_text(json.dumps(result,indent=2));results.append(result);print(tid,result['status'],result.get('error',''),flush=True)
 (root/'containment-summary.json').write_text(json.dumps(results,indent=2))
