import json,time,subprocess,uuid
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');out=r/'out/editor-warm';out.mkdir(exist_ok=True)
with (out/'game.log').open('w') as log:
 p=subprocess.Popen(['/opt/UnrealEngine_5.6/Engine/Binaries/Linux/UnrealEditor',str(r/'project/MedievalVillage.uproject'),'/Game/Auditor/MedievalVillage/Market','-game','-RenderOffscreen','-vulkan','-sm6','-ResX=1280','-ResY=720','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-AuditorReview','-AuditorReviewDiagnostics','-AuditorReviewIPC='+str(out),'-ExecCmds=t.MaxFPS 30'],stdout=log,stderr=subprocess.STDOUT)
 try:
  for i in range(12):
   time.sleep(15)
   assert p.poll() is None
  q=dict(request_id=uuid.uuid4().hex,action='capture',path=str(out/'warm.png'));tmp=out/'command.tmp';tmp.write_text(json.dumps(q));tmp.replace(out/'command.json')
  time.sleep(5)
 finally:p.terminate();p.wait(30)
