from pathlib import Path
import json,subprocess,time,uuid,math,shutil
w=Path('/home/ubuntu/unreal-auditor/indoor-cabinet-interaction-workspace')
binary=w.parent/'indoor-workspace/dist/indoor-cabinet-interaction-20260913-v1/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou'
results=[]
for control in [False]:
 out=w/'out'/'occlusion';out.mkdir(parents=True,exist_ok=True)
 agent=out/'agent';agent.mkdir(exist_ok=True);review=out/'review';review.mkdir(exist_ok=True);responses=[]
 def request(directory,**fields):
  rid=uuid.uuid4().hex;p=directory/'command.tmp';p.write_text(json.dumps(dict(request_id=rid,**fields)));p.replace(directory/'command.json')
  for attempt in range(900):
   try:
    s=json.loads((directory/'response.json').read_text())
    if s['request_id']==rid:return s
   except (FileNotFoundError,json.JSONDecodeError):pass
   time.sleep(.1)
  raise RuntimeError('IPC timeout '+str(fields))
 def action(name,value=0):
  s=request(agent,action=name,value=value);assert s['result'] in ['ok','interacted'],s
  responses.append(dict(action=name,value=value,state=s));return s
 def plant():
  s=request(review,action='snapshot')
  return next(a for a in s['actors'] if a['tag']=='auditor_actor:StaticMeshActor_927')
 def aim(s,target):
  d=[b-a for a,b in zip(s['camera_position_cm'],target)]
  yaw=math.degrees(math.atan2(d[1],d[0]));pitch=math.degrees(math.atan2(-d[2],math.hypot(d[0],d[1])))
  s=action('turn',(yaw-s['yaw_degree']+180)%360-180);return action('look',pitch-s['look_degree'])
 args=[str(binary),'/Game/Auditor/Regions/LivingRoom?Task=baseline','-AuditorServe','-AuditorIPC='+str(agent),'-AuditorReviewIPC='+str(review),'-AuditorReviewDiagnostics','-AuditorRemoteInput','-RenderOffscreen','-vulkan','-sm5','-windowed','-ResX=1280','-ResY=720','-unattended','-nosound','-ExecCmds=t.MaxFPS 10']
 if control:args+=['-AuditorControl']
 with (out/'game.log').open('w') as f:
  p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT)
  try:
   s=action('snapshot')
   def state():return request(review,action='snapshot')
   center=next(a for a in state()['actors'] if a['tag']=='auditor_actor:StaticMeshActor_2071')['center']
   s=aim(s,[center[0],center[1],s['camera_position_cm'][2]])
   s=action('move_up',470)
   s=aim(s,[-1590,-480,s['camera_position_cm'][2]])
   s=action('move_up',145)
   s=aim(s,center)
   distance=math.sqrt(sum((a-b)**2 for a,b in zip(center,s['camera_position_cm'])))
   print('UNDER_FLOOR',s['position_cm'],'DISTANCE',distance,flush=True)
   assert distance<250,(distance,s['position_cm'])
   assert state()['interaction_prompt']==''
   rejected=request(agent,action='interact',value=0)
   assert rejected['result']=='not_interactable',rejected
   shutil.copy2(agent/'observation.png',out/'blocked.png')
   row=dict(result='PASS',solid_floor_blocks_interaction=True,distance=distance,position=s['position_cm']);results.append(row);(out/'report.json').write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True)
  finally:
   p.terminate()
   try:p.wait(15)
   except subprocess.TimeoutExpired:p.kill();p.wait()
(w/'out/occlusion-results.json').write_text(json.dumps(results,indent=2))
