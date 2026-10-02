from pathlib import Path
import json,subprocess,sys,os
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');tasks={'subway':('S18','/Game/Auditor/Subway/Platform','sm6'),'indoor':('H13','/Game/Auditor/Regions/KitchenDining','sm5'),'ancient':('A18','/Game/Auditor/AncientCity/Courtyard','sm6'),'medieval':('MV17','/Game/Auditor/MedievalVillage/Windmill','sm6'),'industrial':('I19','/Game/Auditor/Industrial/AssemblyHall','sm5')}
for f in sys.argv[1:]:
 binary=json.loads((w/'out'/('build-'+f+'.json')).read_text())['binary'];tid,map,shader=tasks[f];out=w/'out'/('render-'+f);out.mkdir(exist_ok=True);results=[]
 for control in [False,True]:
  name='clean' if control else 'bug';png=out/(name+'.png');log=out/(name+'.log');png.unlink(missing_ok=True)
  args=[binary,map+'?Task='+tid,'-vulkan','-'+shader,'-RenderOffscreen','-ResX=1280','-ResY=800','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-AuditorTaskTest','-AuditorTestExit','-ExecCmds=t.MaxFPS 30,DisableAllScreenMessages']+(['-AuditorControl'] if control else [])
  
  if f=='subway':args.remove('-AuditorTaskTest');args.append('-AuditorReview')
  if f=='indoor':args.append('-AuditorReview')
  args+=['-AuditorCapture='+str(png)] if f in ('indoor','subway') else ['-AuditorCaptureOnTest='+str(png)]
  with log.open('w') as stream:
   try:code=subprocess.run(args,stdout=stream,stderr=subprocess.STDOUT,timeout=120).returncode
   except subprocess.TimeoutExpired:code=-1
  result={'case':tid,'control':control,'ok':code==0 and png.exists(),'code':code,'path':str(png)};results.append(result);print(json.dumps(result),flush=True)
 (out/'report.json').write_text(json.dumps(results,indent=2));assert all(r['ok'] for r in results)
