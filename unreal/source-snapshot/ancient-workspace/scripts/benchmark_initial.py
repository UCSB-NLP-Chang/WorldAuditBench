import subprocess,time,json,shutil,csv,statistics
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');out=r/'out/performance-fix';out.mkdir(exist_ok=True)
b=r/'dist/ancient-linux-streaming2/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
variants=[('initialhigh','high'),('initialmedium','medium'),('classicshadows','classic')]
for name,settings in variants:
 args=[str(b),'/Game/Auditor/AncientCity/Courtyard','-RenderOffscreen','-vulkan','-sm6','-ResX=1280','-ResY=720','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-csvCompression=0','-ExecCmds=csvprofile frames=220,r.GPUCsvStatsEnabled 1,t.MaxFPS 30']
 
 if settings in ('high','medium'):
  groups={'sg.GlobalIlluminationQuality':2 if settings=='high' else 1,'sg.ReflectionQuality':2 if settings=='high' else 1,'sg.ShadowQuality':2,'sg.EffectsQuality':2,'sg.PostProcessQuality':2}
  args += ['-ini:GameUserSettings:[ScalabilityGroups]:'+k+'='+str(v) for k,v in groups.items()]
 else:
  args += ['-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Enable=0','-ini:Engine:[SystemSettings]:r.VolumetricCloud=0','-ini:Engine:[SystemSettings]:r.VolumetricFog=0']
 with (out/(name+'.log')).open('w') as f:
  p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT)
  try:
   start=time.time()
   while time.time()-start<100:
    time.sleep(1)
    if p.poll() is not None:break
    txt=(out/(name+'.log')).read_text(errors='replace')
    if 'Capture Ended. Writing CSV' in txt:break
   time.sleep(2)
  finally:p.terminate();p.wait(15)
 txt=(out/(name+'.log')).read_text(errors='replace')
 lines=[x for x in txt.splitlines() if 'Capture Ended. Writing CSV' in x]
 if lines:
  path=Path(lines[-1].split('file : ')[-1].strip())
  if not path.is_absolute():path=(b.parent/path).resolve()
  if path.exists():shutil.copy2(path,out/(name+'.csv'))
 print(name,lines,flush=True)
