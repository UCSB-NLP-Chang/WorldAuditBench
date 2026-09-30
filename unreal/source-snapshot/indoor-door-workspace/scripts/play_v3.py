import json,subprocess,time,uuid,math,shutil
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/indoor-door-workspace');out=w/'out/play-v3';out.mkdir(exist_ok=True)
binary=w.parent/'indoor-workspace/dist/indoor-door-vase-20260913-v3/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou'
responses=[]
def request(action,value=0):
 id=uuid.uuid4().hex;p=out/'command.tmp';p.write_text(json.dumps(dict(request_id=id,action=action,value=value)));p.replace(out/'command.json')
 for _ in range(900):
  try:
   s=json.loads((out/'response.json').read_text())
   if s['request_id']==id:
    assert s['result'] in ['ok','interacted'],s
    responses.append(dict(action=action,value=value,state=s));return s
  except (FileNotFoundError,json.JSONDecodeError):pass
  time.sleep(.1)
 raise RuntimeError(action+' timed out')
def aim(s,target):
 p=s['camera_position_cm'];d=[b-a for a,b in zip(p,target)];yaw=math.degrees(math.atan2(d[1],d[0]));pitch=math.degrees(math.atan2(-d[2],math.hypot(d[0],d[1])))
 s=request('turn',(yaw-s['yaw_degree']+180)%360-180);return request('look',pitch-s['look_degree'])
with (out/'game.log').open('w') as f:
 p=subprocess.Popen([str(binary),'/Game/Auditor/Regions/BedroomSuite?Task=H15','-AuditorServe','-AuditorIPC='+str(out),'-AuditorRemoteInput','-RenderOffscreen','-vulkan','-sm5','-windowed','-ResX=1280','-ResY=720','-unattended','-nosound'],stdout=f,stderr=subprocess.STDOUT)
 try:
  s=request('snapshot');assert s['task_id']=='H15'
  s=aim(s,[-1125,-560,s['camera_position_cm'][2]])
  s=request('move_up',117);assert s['actual_distance_cm']>105,s
  s=aim(s,[-925.94,-465.28,550.85]);shutil.copy2(out/'observation.png',out/'closed.png')
  s=request('interact');assert s['result']=='interacted'
  s=request('idle',1.15);shutil.copy2(out/'observation.png',out/'crossing.png')
  request('idle',2);s=request('snapshot');s=aim(s,[-969.974,-424.65,550.85])
  s=request('interact');assert s['result']=='interacted';request('idle',3);shutil.copy2(out/'observation.png',out/'closed-again.png')
  (out/'report.json').write_text(json.dumps(dict(result='PASS',normal_player_movement=True,real_interaction=True,responses=responses),indent=2));print('Real player walked from spawn and opened/closed bedroom door: PASS')
 finally:
  p.terminate()
  try:p.wait(15)
  except subprocess.TimeoutExpired:p.kill();p.wait()
