from pathlib import Path
import subprocess,json,time,uuid,argparse
p=argparse.ArgumentParser();p.add_argument('--render',action='store_true');args=p.parse_args()
r=Path('/home/ubuntu/unreal-auditor/indoor-workspace');w=r.parent/'indoor-h10-start-workspace';out=w/'out'/('initial-render' if args.render else 'initial-native');out.mkdir(parents=True,exist_ok=True)
binary=r/'dist/indoor-h10-start-20260913-v2/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou'
def request(**fields):
 rid=uuid.uuid4().hex;temp=out/'command.tmp';temp.write_text(json.dumps(dict(request_id=rid,**fields)));temp.replace(out/'command.json')
 deadline=time.time()+90
 while time.time()<deadline:
  try:
   data=json.loads((out/'response.json').read_text())
   if data['request_id']==rid and data['status']!='switching':
    assert data['status']=='ready',data
    return data
  except (FileNotFoundError,json.JSONDecodeError):pass
  time.sleep(.1)
 raise RuntimeError('IPC timeout')
argv=[str(binary),'/Game/Auditor/Regions/LivingRoom?Task=H10','-unattended','-nosound','-AuditorRemoteInput','-AuditorReviewDiagnostics','-ExecCmds=t.MaxFPS 10','-AuditorReviewIPC='+str(out)]
argv+=['-RenderOffscreen','-vulkan','-sm5','-windowed','-ResX=1280','-ResY=720'] if args.render else ['-nullrhi']
with (out/'game.log').open('w') as f:
 process=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT)
 try:
  results=[]
  for index in range(2):
   if index:
    request(action='switch',map='/Game/Auditor/Regions/LivingRoom',task='baseline')
    request(action='switch',map='/Game/Auditor/Regions/LivingRoom',task='H10')
   else:request(action='snapshot')
   time.sleep(2)
   state=request(action='snapshot');assert state['task']=='H10' and state['pid']==process.pid
   assert sum((a-b)**2 for a,b in zip(state['position'][:2],[-1090,-710]))<1,state['position']
   plant=next(a for a in state['actors'] if a['tag']=='auditor_actor:StaticMeshActor_927')
   assert not plant['hidden'] and plant['collision']
   row=dict(result='PASS',mode='cold_start' if index==0 else 'same_process_return',position=state['position'],plant_visible=True,pid=state['pid'])
   if args.render:
    captured=request(action='capture');png=out/(captured['request_id']+'.png')
    for attempt in range(100):
     if png.exists() and png.stat().st_size>1000:break
     time.sleep(.1)
    assert png.exists();dest=out/('initial-'+str(index)+'.png');png.replace(dest);row['image']=str(dest)
   results.append(row);print(json.dumps(row),flush=True)
  (out/'results.json').write_text(json.dumps(results,indent=2))
 finally:
  process.terminate()
  try:process.wait(15)
  except subprocess.TimeoutExpired:process.kill();process.wait()
