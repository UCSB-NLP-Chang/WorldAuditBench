from pathlib import Path
import subprocess,json
w=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20-car-replacement');b=json.loads((w/'out/build.json').read_text())['binary'];results=[]
for name,task,yaw in [('bug','S20',None),('clean','baseline',None),('side','S20',-90)]:
 png=w/'out'/(name+'.png');args=[b,'/Game/Auditor/Subway/Platform?Task='+task,'-vulkan','-sm6','-RenderOffscreen','-ResX=1280','-ResY=800','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-AuditorReview','-AuditorReviewReference=S20','-AuditorTestExit','-AuditorCapture='+str(png),'-ExecCmds=t.MaxFPS 30,DisableAllScreenMessages']
 if name=='side':continue
 with (w/'out'/('render-'+name+'.log')).open('w') as f:code=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=120).returncode
 results.append(dict(name=name,ok=code==0 and png.exists()));print(results[-1],flush=True)
(w/'out/render.json').write_text(json.dumps(results,indent=2));assert all(x['ok'] for x in results)
