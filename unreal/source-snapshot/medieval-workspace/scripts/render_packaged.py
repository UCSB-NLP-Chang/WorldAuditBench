from pathlib import Path
import subprocess,json,time,os
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');out=Path(os.getenv('MEDIEVAL_RENDER_OUTPUT',str(r/'out/render-streaming2')));out.mkdir(exist_ok=True)
binary=Path(os.getenv('MEDIEVAL_RENDER_BINARY',str(r/'dist/medieval-linux-v1/Linux/MedievalVillage/Binaries/Linux/MedievalVillage')))
tasks=json.loads((r/'environments/medieval-village/tasks.json').read_text())['tasks'];regions=json.loads((r/'environments/medieval-village/regions.json').read_text())['regions']
jobs=[(t['id'],t['map']+'?Task='+t['id'],(['-AuditorReview'] if t['kind']=='view_cull' else ['-AuditorTaskTest']),t['kind']!='view_cull') for t in tasks]
jobs += [(reg['id']+'-baseline',reg['map'],['-AuditorReview'],False) for reg in regions]
jobs += [(t['id']+'-clean',t['map'],['-AuditorReview','-AuditorReviewReference='+t['id']],False) for t in tasks]
jobs += [(t['id']+'-far-clean',t['map'],['-AuditorReview','-AuditorReviewReference='+t['id'],'-AuditorReviewFarReference'],False) for t in tasks if t['kind'] in ['distance_cull','distance_scale']]
if os.getenv('MEDIEVAL_RENDER_NAMES'):jobs=[j for j in jobs if j[0] in os.environ['MEDIEVAL_RENDER_NAMES'].split(',')]
results=[]
for name,map,flags,test in jobs:
 image=out/(name+'.png');image.unlink(missing_ok=True);start=time.time()
 if os.getenv('MEDIEVAL_RENDER_STATIC') and test:flags=['-AuditorReview'];test=False
 args=([str(binary),map] if not os.getenv('MEDIEVAL_EDITOR') else ['/opt/UnrealEngine_5.6/Engine/Binaries/Linux/UnrealEditor',str(r/'project/MedievalVillage.uproject'),map,'-game'])+['-RenderOffscreen','-vulkan','-sm6','-ResX=1280','-ResY=720','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-AuditorTestExit','-ExecCmds=t.MaxFPS 30',*flags,('-AuditorCaptureOnTest=' if test else '-AuditorCapture=')+str(image)]
 with (out/(name+'.log')).open('w') as f:
  try:code=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=420).returncode
  except subprocess.TimeoutExpired:code=-1
 result=dict(name=name,ok=code==0 and image.exists(),code=code,seconds=round(time.time()-start,1));results.append(result);print(json.dumps(result),flush=True)
(out/'report.json').write_text(json.dumps(results,indent=2));raise SystemExit(0 if all(t['ok'] for t in results) else 1)
