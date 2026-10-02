from pathlib import Path
import subprocess
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');out=r/'out/render-streaming2';out.mkdir(exist_ok=True)
binary=r/'dist/ancient-linux-streaming2/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
for name,map,flags in [
 ('A13-shadow','/Game/Auditor/AncientCity/Courtyard?Task=A13',['-AuditorReviewPitch=-38']),
 ('A13-shadow-clean','/Game/Auditor/AncientCity/Courtyard',['-AuditorReviewReference=A13','-AuditorReviewPitch=-38']),
 ('A02-support','/Game/Auditor/AncientCity/Courtyard?Task=A02',['-AuditorReviewPitch=-22']),
 ('A20-texture','/Game/Auditor/AncientCity/Market?Task=A20',[])]:
 image=out/(name+'.png');image.unlink(missing_ok=True)
 with (out/(name+'.log')).open('w') as f:
  code=subprocess.run([str(binary),map,'-RenderOffscreen','-vulkan','-sm6','-ResX=1280','-ResY=720','-ForceRes','-unattended','-nosound','-AuditorRemoteInput','-AuditorReview','-AuditorCapture='+str(image),'-AuditorTestExit','-ExecCmds=t.MaxFPS 30,r.Streaming.PoolSize 3072',*flags],stdout=f,stderr=subprocess.STDOUT,timeout=90).returncode
 assert code==0 and image.exists(),name
 print(name+' PASS',flush=True)

