from pathlib import Path
import subprocess,json
r=Path('/home/ubuntu/unreal-auditor/industrial-workspace');o=r/'out/operational';b=r/'dist/industrial-operational-20260913-v1/Linux/FactoryEnvironmentCollect/Binaries/Linux/FactoryEnvironmentCollect'
results=[]
for tid in ['I20','I21']:
 for control in [False,True]:
  name=tid+('-control' if control else '-bug')
  with (o/(name+'.log')).open('w') as f:
   args=[str(b),'/Game/Auditor/Industrial/ControlRoom?Task='+tid,'-RenderOffscreen','-vulkan','-sm5','-ResX=1280','-ResY=720','-ForceRes','-nosound','-unattended','-stdout','-AuditorRemoteInput','-AuditorTaskTest','-AuditorTestExit','-ExecCmds=t.MaxFPS 30','-AuditorOperationalCapturePrefix='+str(o/name)]
   if control:args+=['-AuditorControl']
   try:code=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=90).returncode
   except subprocess.TimeoutExpired:code=-1
  result=dict(name=name,ok=code==0 and (o/(name+'-before.png')).exists() and (o/(name+'-after.png')).exists());results.append(result);print(result,flush=True)
(o/'render-report.json').write_text(json.dumps(results,indent=2));assert all(x['ok'] for x in results)

