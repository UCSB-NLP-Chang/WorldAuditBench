from pathlib import Path
import subprocess,json,time,os
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');out=r/'out/render-performance';out.mkdir(exist_ok=True)
binary=r/'dist/ancient-stairs-lod-20260912/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
tasks=json.loads((r/'environments/ancient-chinese-city/tasks.json').read_text())['tasks'];regions=json.loads((r/'environments/ancient-chinese-city/regions.json').read_text())['regions']
jobs=[(t['id'],t['map']+'?Task='+t['id'],['-AuditorTaskTest'],True) for t in tasks]
jobs += [(reg['id']+'-baseline',reg['map'],['-AuditorReview'],False) for reg in regions]
jobs += [(t['id']+'-clean',t['map'],['-AuditorReview','-AuditorReviewReference='+t['id']],False) for t in tasks]
jobs += [('courtyard-stairs','/Game/Auditor/AncientCity/Courtyard',['-AuditorAncientStairTest'],True)]
if os.getenv('ANCIENT_RENDER_NAMES'):jobs=[j for j in jobs if j[0] in os.environ['ANCIENT_RENDER_NAMES'].split(',')]
results=[]
for name,map,flags,test in jobs:
 image=out/(name+'.png');image.unlink(missing_ok=True);start=time.time()
 if os.getenv('ANCIENT_RENDER_STATIC') and test:flags=['-AuditorReview'];test=False
 args=[str(binary),map,'-RenderOffscreen','-vulkan','-sm6','-ResX=1280','-ResY=720','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-AuditorTestExit','-ExecCmds=t.MaxFPS 30',*flags,('-AuditorCaptureOnTest=' if test else '-AuditorCapture=')+str(image)]
 args=[a for a in args if not a.startswith('-ExecCmds=')]+json.loads((r/'environments/ancient-chinese-city/streaming-settings.json').read_text())['game_args']
 with (out/(name+'.log')).open('w') as f:
  try:code=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=100).returncode
  except subprocess.TimeoutExpired:code=-1
 result=dict(name=name,ok=code==0 and image.exists(),code=code,seconds=round(time.time()-start,1));results.append(result);print(json.dumps(result),flush=True)
(out/'report.json').write_text(json.dumps(results,indent=2));raise SystemExit(0 if all(t['ok'] for t in results) else 1)

