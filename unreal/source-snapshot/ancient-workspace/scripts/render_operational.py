import json,subprocess,os
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');o=r/'out/operational-v1';b=r/'dist/ancient-operational-20260913-v1/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
args=json.loads((r/'environments/ancient-chinese-city/streaming-settings.json').read_text())['game_args']
res=[]
for control in [True,False]:
 name='A17-control' if control else 'A17-closed'
 with (o/(name+'.log')).open('w') as f:
  p=subprocess.run([str(b),'/Game/Auditor/AncientCity/Courtyard?Task=A17','-RenderOffscreen','-ResX=1280','-ResY=720','-ForceRes','-unattended','-nosound','-AuditorRemoteInput','-AuditorTaskTest','-AuditorTestExit','-AuditorCaptureOnTest='+str(o/(name+'.png')),*(['-AuditorControl'] if control else []),*args],stdout=f,stderr=subprocess.STDOUT,timeout=90)
 res.append(dict(name=name,ok=p.returncode==0 and (o/(name+'.png')).exists()))
 print(res[-1],flush=True)
(o/'renders.json').write_text(json.dumps(res,indent=2));assert all(x['ok'] for x in res)

