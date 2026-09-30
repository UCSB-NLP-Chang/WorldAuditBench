import subprocess,time,json,shutil,csv,statistics
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');out=r/'out/npc-reduction/benchmark';out.mkdir(parents=True,exist_ok=True)
b=r/'dist/ancient-sparse-npcs-20260912/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
variants=[('sparse_courtyard','Courtyard'),('sparse_market','Market'),('sparse_tea','TeaHouse')]
for name,settings in variants:
 args=[str(b),'/Game/Auditor/AncientCity/'+settings,'-RenderOffscreen','-vulkan','-sm6','-ResX=1280','-ResY=720','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-csvCompression=0','-ExecCmds=csvprofile frames=220,r.GPUCsvStatsEnabled 1,t.MaxFPS 30'+',r.SkinCache.Mode 0,r.OptimizedWPO 1,r.Nanite.AllowWPODistanceDisable 1,r.SkeletalMeshLODBias 1,r.Nanite.MaxPixelsPerEdge 2']
 
 args += ['-ini:GameUserSettings:[ScalabilityGroups]:'+k+'='+str(v) for k,v in {'sg.GlobalIlluminationQuality':1,'sg.ReflectionQuality':1,'sg.ShadowQuality':2,'sg.EffectsQuality':2,'sg.PostProcessQuality':2}.items()]
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
