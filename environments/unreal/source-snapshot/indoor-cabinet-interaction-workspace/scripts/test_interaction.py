from pathlib import Path
import json,subprocess,time,uuid,math,shutil
w=Path('/home/ubuntu/unreal-auditor/indoor-cabinet-interaction-workspace')
binary=w.parent/'indoor-workspace/dist/indoor-cabinet-interaction-20260913-v1/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou'
results=[]
for control in [False]:
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
 args=[str(binary),'/Game/Auditor/Regions/BedroomSuite?Task=baseline','-AuditorServe','-AuditorIPC='+str(agent),'-AuditorReviewIPC='+str(review),'-AuditorReviewDiagnostics','-AuditorRemoteInput','-RenderOffscreen','-vulkan','-sm5','-windowed','-ResX=1280','-ResY=720','-unattended','-nosound','-ExecCmds=t.MaxFPS 10']
 if control:args+=['-AuditorControl']
 with (out/'game.log').open('w') as f:
  p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT)
  try:
   s=action('snapshot')
   def state():return request(review,action='snapshot')
   def cabinet():return next(a for a in state()['actors'] if a['tag']=='auditor_actor:StaticMeshActor_2071')
   center=cabinet()['center'];print('START',s['position_cm'],'CABINET',center,flush=True)
   s=aim(s,center)
   print('FAR',state()['interaction_prompt'],flush=True)
   assert state()['interaction_prompt']==''
   s=action('move_up',300)
   s=aim(s,center)
   print('NEAR',s['position_cm'],state()['interaction_prompt'],flush=True)
   shutil.copy2(agent/'observation.png',out/'near.png')
   assert state()['interaction_prompt']=='Open cabinet'
   s=action('turn',25)
   assert state()['interaction_prompt']=='Open cabinet'
   shutil.copy2(agent/'observation.png',out/'offset-open.png')
   closed=cabinet()['transform']
   s=action('interact');s=action('idle',2)
   assert state()['interaction_prompt']=='Close cabinet'
   assert cabinet()['transform']!=closed
   shutil.copy2(agent/'observation.png',out/'offset-close.png')
   s=action('interact');s=action('idle',2)
   assert state()['interaction_prompt']=='Open cabinet'
   assert cabinet()['transform']==closed
   s=action('turn',65)
   assert state()['interaction_prompt']==''
   rejected=request(agent,action='interact',value=0)
   assert rejected['result']=='not_interactable',rejected
   assert cabinet()['transform']==closed
   row=dict(result='PASS',normal_player_movement=True,range_rejection=True,off_axis_25_degrees=True,open_close_prompt=True,animation=True,facing_away_rejected=True,responses=responses)
   results.append(row);(out/'report.json').write_text(json.dumps(row,indent=2));print(json.dumps({k:v for k,v in row.items() if k!='responses'}),flush=True)
  finally:
   p.terminate()
   try:p.wait(15)
   except subprocess.TimeoutExpired:p.kill();p.wait()
(w/'out/walk-results.json').write_text(json.dumps(results,indent=2))
