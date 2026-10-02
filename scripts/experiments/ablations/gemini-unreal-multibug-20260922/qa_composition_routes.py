"""Walk native paired routes and capture each target; diagnostic, never a model run."""
from pathlib import Path
import copy,json,math,os,signal,subprocess,time,uuid
import qa_urban_reference as qa
B=qa.B
J=B/'composition-routes-reservation.json'
GPU=0

def corners(route):
 out=[]
 for i in range(1,len(route)):
  if i<len(route)-1:
   a=[route[i][k]-route[i-1][k] for k in (0,1)];c=[route[i+1][k]-route[i][k] for k in (0,1)]
   if abs(a[0]*c[1]-a[1]*c[0])<.1 and sum(x*y for x,y in zip(a,c))>0:continue
  out.append(route[i])
 return out

def run(ref,condition,label,route,focus,binary,output_root=None,prefix_actions=None,specification_root=None,collision_step_cm=None):
 tid=ref['id'];d=(output_root or B)/'composition-rendered-routes'/tid/condition/label;d.mkdir(parents=True,exist_ok=False)
 p=ref['profile'];args=[x for x in p.get('game_args',[])+p.get('extra_args',[]) if not x.lower().startswith(('-pixelstreaming','-graphicsadapter','-auditoripc','-abslog','-auditorremote','-resx','-resy'))]
 cmd=[str(binary),p['runtime_map'],'-RenderOffscreen','-windowed','-ResX=960','-ResY=540','-nosound','-unattended','-AuditorServe','-AuditorRemoteTask='+tid,'-AuditorIPC='+str(d),'-abslog='+str(d/'native.log'),'-graphicsadapter='+str(GPU),'-UserDir='+str(d/'user'),'-NoSaveConfig','-AuditorCompositionInventory',*args]
 if condition!='A':cmd.append('-AuditorComposition='+str((specification_root or B/'draft-compositions')/tid/(condition+'.json')))
 qa.write(d/'launch-command.json',cmd);qa.verify(J,GPU)
 result={'id':tid,'condition':condition,'target':label,'models_started':0,'ready_for_model':False,'actions':[]}
 with (d/'stdout.log').open('w') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);qa.ACTIVE=proc
  qa.write(d/'process.json',{'pid':proc.pid,'time':time.time()})
  def wait(req):
   deadline=time.monotonic()+180
   while time.monotonic()<deadline:
    if qa.STOP:raise InterruptedError('QA stopped')
    qa.verify(J,GPU)
    if proc.poll() is not None:raise RuntimeError('Native exited '+str(proc.returncode))
    try:s=json.loads((d/'response.json').read_text())
    except (OSError,ValueError):s={}
    if s.get('request_id')==req and s.get('paused') and s.get('frames'):
     assert s['result'] in ['ready','ok','blocked'],s['result'];return s
    time.sleep(.1)
   raise TimeoutError('Native response timeout')
  def capture(name,s):
   qa.write(d/(name+'.json'),s);__import__('shutil').copy2(d/s['frames'][-1]['file'],d/(name+'.png'))
  def action(kind,value):
   r={'request_id':uuid.uuid4().hex,'action':kind,'value':value};qa.write(d/'command.json',r);s=wait(r['request_id']);result['actions'].append({'action':r,'state':{k:v for k,v in s.items() if k!='frames'}});return s
  try:
   s=wait('');assert math.dist(s['position_cm'],ref['policy']['spawn'])<10;capture('initial',s)
   for item in prefix_actions or []:
    s=action(item['action'],item['value'])
   for point in corners(route):
    for attempt in range(max(6,math.ceil(math.dist(s['position_cm'][:2],point[:2])/400)+4)):
     pos=s['position_cm'];distance=math.dist(pos[:2],point[:2])
     if distance<10:break
     yaw=math.degrees(math.atan2(point[1]-pos[1],point[0]-pos[0]));turn=(yaw-s['yaw_degree']+180)%360-180
     if abs(turn)>.1:s=action('turn',turn)
     before=s['position_cm'];s=action('move_up',min(distance,400))
     if math.dist(before[:2],s['position_cm'][:2])<1:raise RuntimeError('Route blocked near '+str(point))
    if math.dist(s['position_cm'][:2],point[:2])>18:raise RuntimeError('Waypoint not reached '+str(point))
   camera=s.get('camera_position_cm',s['position_cm']);yaw=math.degrees(math.atan2(focus[1]-camera[1],focus[0]-camera[0]));turn=(yaw-s['yaw_degree']+180)%360-180
   if abs(turn)>.1:s=action('turn',turn)
   desired=-math.degrees(math.atan2(focus[2]-camera[2],max(1,math.dist(camera[:2],focus[:2]))));look=desired-s.get('look_degree',0)
   if abs(look)>.1:s=action('look',look)
   capture('target-view',s)
   assert 'AUDITOR_OUT_OF_BOUNDS_RESET' not in (d/'native.log').read_text(errors='replace')
   result.update(status='traversed_pending_visual_review',inspection_position=s['position_cm'],focus=focus)
   if label in ['B','C'] and ref['subcategory']=='C1':
    before=s['position_cm'];distance=math.dist(before[:2],focus[:2]);remaining=min(distance+150,650)
    if collision_step_cm is None:s=action('move_up',remaining)
    else:
     assert 1<=collision_step_cm<=100
     trace=[]
     while remaining>1e-4:
      amount=min(collision_step_cm,remaining);s=action('move_up',amount);remaining-=amount
      trace.append({'position_cm':s['position_cm'],'result':s['result'],'distance_to_center':math.dist(s['position_cm'][:2],focus[:2])})
      capture('probe-step-%02d'%len(trace),s)
     result['collision_trace']=trace
    capture('collision-probe',s)
    result['collision_probe']={'before':before,'after':s['position_cm'],'distance_to_center':distance,'displacement':math.dist(before[:2],s['position_cm'][:2]),'interpretation':'pending comparison against normal control and object/world geometry'}
  except Exception as exc:result.update(status='needs_resolution',error=repr(exc));
  finally:
   qa.terminate(proc);qa.ACTIVE=None
 result['time']=time.time();qa.write(d/'result.json',result);print(tid,condition,label,result['status'],result.get('error',''),flush=True);return result

def main():
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,qa.stop)
 refs={t['id']:t for t in json.loads((B/'reference-provenance.json').read_text())['tasks']};lease=qa.Reservation('/home/ec2-user/unreal-production',J,[0]);results=[]
 try:
  lease.acquire()
  for tid in ['U014','U015','U032']:
   ref=refs[tid];binary=B/'packages'/('urban-'+tid)/Path(ref['profile']['binary']).relative_to(Path(ref['profile']['binary']).parents[3])
   targets=json.loads((B/'draft-compositions'/tid/'targets.json').read_text())['additions']
   a=json.loads((B.parent/'gemini-unreal-distance-ablation-20260921/route-preparation'/tid/'result.json').read_text());assert a['status']=='candidate_geometry_prepared'
   routes={'A':a['route']};focus={'A':ref['policy']['focus']}
   for t in targets:
    label=t['label'];path=B/'composition-route-plans'/tid/(label+'-grid100');path=path if path.exists() else B/'composition-route-plans'/tid/label
    n=json.loads((path/'native.json').read_text());extension=list(reversed(n['route_to_old_spawn']));assert math.dist(ref['policy']['route_to_old_spawn'][-1],extension[0])<12
    routes[label]=ref['policy']['route_to_old_spawn']+extension[1:];focus[label]=t['normal_state']['center']
   for condition in ['A','AB','ABC']:
    for label in ['A','B','C']:
     f=list(focus[label]);active=label in condition
     if active and label!='A' and ref['subcategory']=='G1':f[2]+=60
     result=run(ref,condition,label,routes[label],f,binary);results.append({k:v for k,v in result.items() if k!='actions'})
     qa.write(B/'composition-routes-status.json',{'status':'running','tasks':results,'model_calls':0})
     if qa.STOP:raise InterruptedError('QA stopped')
  qa.write(B/'composition-routes-status.json',{'status':'captured_pending_review','tasks':results,'model_calls':0})
 finally:qa.terminate(qa.ACTIVE);lease.release()
if __name__=='__main__':main()
