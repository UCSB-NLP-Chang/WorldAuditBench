from pathlib import Path
import json,subprocess,time,signal,os,math,uuid,traceback
root=Path(__file__).parent
profiles=json.loads((root/'qa-profiles.json').read_text());policy=json.loads((root/'policy.json').read_text())
results=[]
for tid,e in policy['tasks'].items():
 if os.environ.get('QA_FAMILY') and e['family']!=os.environ['QA_FAMILY']:continue
 d=root/'task-route-qa'/tid;d.mkdir(parents=True,exist_ok=True)
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
 (root/'task-route-summary.json').write_text(json.dumps(results,indent=2))
