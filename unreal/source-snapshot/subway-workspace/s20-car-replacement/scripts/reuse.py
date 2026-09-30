from pathlib import Path
import subprocess,json,time,uuid,sys,os
w=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20-car-replacement')
cases={'subway':('S20','/Game/Auditor/Subway/Platform','PrivateCarTemplate'),'indoor':('H13','/Game/Auditor/Regions/KitchenDining','StaticMeshActor_173'),'ancient':('A18','/Game/Auditor/AncientCity/Courtyard','Scenery_SM_doorMain_SM_Door_MainEntrance_01_5'),'industrial':('I19','/Game/Auditor/Industrial/AssemblyHall','ConfigurationTray'),'medieval':('MV17','/Game/Auditor/MedievalVillage/Windmill',None)}
if os.getenv('CONFIGURATION_REUSE_CASE')=='A21':cases['ancient']=('A21','/Game/Auditor/AncientCity/TeaHouse','EraDrinkCan')
for family in sys.argv[1:]:
 tid,map,target=cases[family];out=w/'out'/('reuse-'+('a21' if os.getenv('CONFIGURATION_REUSE_CASE')=='A21' else family));out.mkdir(exist_ok=True);binary=json.loads((w/'out/build.json').read_text())['binary']
 def request(**fields):
  rid=uuid.uuid4().hex;tmp=out/'command.tmp';tmp.write_text(json.dumps(dict(request_id=rid,**fields)));tmp.replace(out/'command.json');deadline=time.time()+80
  while time.time()<deadline:
   try:
    d=json.loads((out/'response.json').read_text())
    if d['request_id']==rid and d['status']!='switching':assert d['status']=='ready',d;return d
   except (FileNotFoundError,json.JSONDecodeError):pass
   time.sleep(.1)
  raise TimeoutError(fields)
 def selected(d):
  rows=[a for a in d['actors'] if target is None or a['tag']=='auditor_actor:'+target]
  if target:assert len(rows)==1,(family,target,[a['tag'] for a in d['actors']])
  return sorted(rows,key=lambda a:a['tag'])
 with (out/'game.log').open('w') as log:
  p=subprocess.Popen([binary,map,'-nullrhi','-unattended','-nosound','-AuditorRemoteInput','-AuditorReviewDiagnostics','-AuditorReviewIPC='+str(out),'-ExecCmds=t.MaxFPS 30'],stdout=log,stderr=subprocess.STDOUT)
  try:
   request(action='snapshot');results=[]
   for cycle in range(2):
    clean=request(action='switch',map=map,task='baseline');bug=request(action='switch',map=map,task=tid);restored=request(action='switch',map=map,task='baseline')
    assert clean['pid']==bug['pid']==restored['pid']==p.pid
    assert selected(clean)==selected(restored),(family,'not restored')
    # Semantic additions clone a hidden source; its own transform correctly stays fixed.
    assert not any(a['tag']=='auditor_actor:PlatformPrivateCar' for a in clean['actors']+restored['actors'])
    cars=[a for a in bug['actors'] if a['tag']=='auditor_actor:PlatformPrivateCar'];assert len(cars)==1 and cars[0]['collision'] and not cars[0]['hidden']
    assert bug['task']==tid and restored['task']=='baseline'
    results.append(dict(case=tid,ok=True,cycle=cycle,pid=p.pid,target=target,restored=True))
   (out/'report.json').write_text(json.dumps(results,indent=2));print(json.dumps(results),flush=True)
  finally:
   p.terminate()
   try:p.wait(15)
   except subprocess.TimeoutExpired:p.kill();p.wait()
