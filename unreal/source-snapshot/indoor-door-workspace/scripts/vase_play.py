import json,subprocess,time,uuid,math,shutil
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/indoor-door-workspace');out=w/'out/vase-play';out.mkdir(exist_ok=True)
binary=w.parent/'indoor-workspace/dist/indoor-door-vase-20260913-v3/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou'
responses=[]
def request(action,value=0):
 id=uuid.uuid4().hex;p=out/'command.tmp';p.write_text(json.dumps(dict(request_id=id,action=action,value=value)));p.replace(out/'command.json')
 for _ in range(900):
  try:
   s=json.loads((out/'response.json').read_text())
   if s['request_id']==id:
    assert s['result'] in ['ok','interacted','blocked'],s
    responses.append(dict(action=action,value=value,state=s));return s
  except (FileNotFoundError,json.JSONDecodeError):pass
  time.sleep(.1)
 raise RuntimeError(action+' timed out')
def aim(s,target):
 p=s['camera_position_cm'];d=[b-a for a,b in zip(p,target)];yaw=math.degrees(math.atan2(d[1],d[0]));pitch=math.degrees(math.atan2(-d[2],math.hypot(d[0],d[1])))
 s=request('turn',(yaw-s['yaw_degree']+180)%360-180);return request('look',pitch-s['look_degree'])
with (out/'game.log').open('w') as f:
 p=subprocess.Popen([str(binary),'/Game/Auditor/Regions/LivingRoom?Task=H09','-AuditorServe','-AuditorIPC='+str(out),'-AuditorRemoteInput','-RenderOffscreen','-vulkan','-sm5','-windowed','-ResX=1280','-ResY=720','-unattended','-nosound'],stdout=f,stderr=subprocess.STDOUT)
 try:
  s=request('snapshot');assert s['task_id']=='H09'
  # Walk the existing open route around the seating area to the two vases.
  for x,y in [(-1090,-1040),(-1460,-1040),(-1460,-1130)]:
   pos=s['position_cm'];distance=math.hypot(x-pos[0],y-pos[1]);s=aim(s,[x,y,s['camera_position_cm'][2]])
   s=request('move_up',distance);assert s['actual_distance_cm']>distance-12,s
  s=aim(s,[-1515,-955,165]);shutil.copy2(out/'observation.png',out/'approach.png')
  distance=math.hypot(s['position_cm'][0]+1515,s['position_cm'][1]+955)
  s=request('move_up',distance+40)
  clearance=math.hypot(s['position_cm'][0]+1515,s['position_cm'][1]+955)
  assert s['result']=='blocked' and 35<clearance<65,(s,clearance)
  (out/'report.json').write_text(json.dumps(dict(result='PASS',normal_player_route=True,reference_vase_blocks_player=True,clearance_cm=clearance,responses=responses),indent=2));print('Walkable route and solid vase collision: PASS')
 finally:
  p.terminate()
  try:p.wait(15)
  except subprocess.TimeoutExpired:p.kill();p.wait()
