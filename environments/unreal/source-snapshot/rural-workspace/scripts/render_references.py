from pathlib import Path
import subprocess,json
root=Path(__file__).resolve().parents[1];out=root/'out/references';out.mkdir(exist_ok=True);binary=root/'dist/rural-linux-v3/Linux/RuralAustralia/Binaries/Linux/RuralAustralia'
tasks=json.loads((root/'environments/rural-australia/tasks.json').read_text())['tasks'];regions=json.loads((root/'environments/rural-australia/regions.json').read_text())['regions']
jobs=[(t['id'],t['map'],['-AuditorReviewReference='+t['id']]) for t in tasks]+[(r['id'],r['map'],[]) for r in regions]
for name,m,extra in jobs:
 dest=out/(name+'.png')
 with (out/(name+'.log')).open('w') as f:
  p=subprocess.run([str(binary),m,'-RenderOffscreen','-vulkan','-sm5','-ResX=1280','-ResY=720','-ForceRes','-nosound','-unattended','-AuditorRemoteInput','-AuditorReview','-AuditorTestExit','-ExecCmds=t.MaxFPS 30','-AuditorCapture='+str(dest),*extra],stdout=f,stderr=subprocess.STDOUT,timeout=90)
 assert p.returncode==0 and dest.exists(),name
 print('RURAL_REFERENCE_PASS',name,flush=True)
