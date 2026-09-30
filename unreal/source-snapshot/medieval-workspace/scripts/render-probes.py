import subprocess,concurrent.futures
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');o=r/'out/house-v3/probe-previews';o.mkdir(exist_ok=True)
def run(id):
 with (o/(id+'.log')).open('w') as f:
  p=subprocess.run(['/opt/UnrealEngine_5.6/Engine/Binaries/Linux/UnrealEditor',str(r/'project/MedievalVillage.uproject'),'/Game/Auditor/MedievalVillage/HouseProbeQA?Task='+id,'-game','-RenderOffscreen','-vulkan','-sm6','-ResX=1280','-ResY=720','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-AuditorTaskTest','-AuditorTestExit','-AuditorCaptureOnTest='+str(o/(id+'.png')),'-ExecCmds=t.MaxFPS 30'],stdout=f,stderr=subprocess.STDOUT,timeout=150);print(id,p.returncode,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:list(p.map(run,['HOUSEQA1','HOUSEQA2','HOUSEQA3']))
