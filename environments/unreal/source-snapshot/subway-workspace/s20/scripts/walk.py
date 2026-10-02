from pathlib import Path
import json,subprocess,time,uuid,shutil
w=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20');binary=json.loads((w/'out/build.json').read_text())['binary'];results=[]
for task in ['baseline','S20']:
 out=w/'out'/('walk-'+task);out.mkdir(exist_ok=True)
 for n in ['command.json','response.json']:(out/n).unlink(missing_ok=True)
 def response(rid=None):
  deadline=time.time()+100
  while time.time()<deadline:
   if p.poll() is not None:raise RuntimeError('Game exited')
   try:
    d=json.loads((out/'response.json').read_text())
    if rid is None or d['request_id']==rid:return d
   except (FileNotFoundError,json.JSONDecodeError):pass
   time.sleep(.1)
  raise TimeoutError(rid)
 def req(action,value):
  rid=uuid.uuid4().hex;tmp=out/'command.tmp';tmp.write_text(json.dumps(dict(request_id=rid,action=action,value=value)));tmp.replace(out/'command.json');d=response(rid);results.append(dict(task=task,action=action,value=value,result=d['result'],position=d['position_cm'],distance=d['actual_distance_cm']));return d
 with (out/'game.log').open('w') as log:
  p=subprocess.Popen([binary,'/Game/Auditor/Subway/Platform?Task='+task,'-vulkan','-sm6','-RenderOffscreen','-ResX=1280','-ResY=800','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-AuditorServe','-AuditorIPC='+str(out),'-ExecCmds=t.MaxFPS 30,DisableAllScreenMessages'],stdout=log,stderr=subprocess.STDOUT)
  try:
   start=response();assert start['result']=='ready';shutil.copy2(out/'observation.png',w/'out'/('spawn-'+task+'.png'))
   req('turn',-90);req('move_up',40);req('turn',90)
   hit=req('move_up',400)
   if task=='baseline':assert hit['result']=='ok' and hit['actual_distance_cm']>399
   else:
    assert hit['result']=='blocked' and 60<hit['actual_distance_cm']<250,hit
    req('turn',90);d=req('move_up',170);assert d['result']=='ok',d
    req('turn',-90);d=req('move_up',700);assert d['result']=='ok',d
    req('turn',-90);d=req('move_up',170);assert d['result']=='ok',d
    req('turn',-90);shutil.copy2(out/'observation.png',w/'out/bypass.png')
  finally:
   p.terminate()
   try:p.wait(15)
   except subprocess.TimeoutExpired:p.kill();p.wait()
(w/'out/walk.json').write_text(json.dumps(dict(status='PASS',checks=results),indent=2));print('WALK_PASS',flush=True)
