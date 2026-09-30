from pathlib import Path
import json,subprocess,time,uuid,math,shutil
w=Path('/home/ubuntu/unreal-auditor/indoor-h10-start-workspace')
binary=w.parent/'indoor-workspace/dist/indoor-h10-start-20260913-v2/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou'
results=[]
for control in [True,False]:
 out=w/'out'/('walk-control' if control else 'walk-bug');out.mkdir(parents=True,exist_ok=True)
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
 args=[str(binary),'/Game/Auditor/Regions/LivingRoom?Task=H10','-AuditorServe','-AuditorIPC='+str(agent),'-AuditorReviewIPC='+str(review),'-AuditorReviewDiagnostics','-AuditorRemoteInput','-RenderOffscreen','-vulkan','-sm5','-windowed','-ResX=1280','-ResY=720','-unattended','-nosound','-ExecCmds=t.MaxFPS 10']
 if control:args+=['-AuditorControl']
 with (out/'game.log').open('w') as f:
  p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT)
  try:
   s=action('snapshot');assert s['task_id']=='H10'
   start=s['position_cm'];yaw=s['yaw_degree'];pitch=s['look_degree']
   assert math.hypot(start[0]+1090,start[1]+710)<2,s
   assert not plant()['hidden']
   shutil.copy2(agent/'observation.png',out/'initial.png')
   s=aim(s,[-1090,-1080,s['camera_position_cm'][2]])
   s=action('move_up',370);assert s['actual_distance_cm']>350,s
   assert not plant()['hidden'],'Must not disappear before return'
   s=aim(s,[start[0],start[1],s['camera_position_cm'][2]])
   s=action('move_up',math.hypot(s['position_cm'][0]-start[0],s['position_cm'][1]-start[1]))
   s=action('turn',(yaw-s['yaw_degree']+180)%360-180);s=action('look',pitch-s['look_degree'])
   s=action('idle',.5)
   after=plant();assert after['hidden']==(not control),after
   shutil.copy2(agent/'observation.png',out/'returned.png')
   row=dict(result='PASS',control=control,normal_player_movement=True,initial_visible=True,visible_before_return=True,hidden_after_return=after['hidden'],responses=responses)
   results.append(row);(out/'report.json').write_text(json.dumps(row,indent=2));print(json.dumps({k:v for k,v in row.items() if k!='responses'}),flush=True)
  finally:
   p.terminate()
   try:p.wait(15)
   except subprocess.TimeoutExpired:p.kill();p.wait()
(w/'out/walk-results.json').write_text(json.dumps(results,indent=2))
