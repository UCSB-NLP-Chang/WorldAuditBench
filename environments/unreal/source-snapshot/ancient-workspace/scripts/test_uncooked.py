from pathlib import Path
import subprocess,json,concurrent.futures,time,os
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');out=r/'out/tests-uncooked';out.mkdir(exist_ok=True)
tasks=json.loads((r/'environments/ancient-chinese-city/tasks.json').read_text())['tasks'];regions=json.loads((r/'environments/ancient-chinese-city/regions.json').read_text())['regions']
jobs=[(t['id'],t['map']+'?Task='+t['id'],['-AuditorTaskTest']) for t in tasks]+[(reg['id']+'-walk',reg['map'],['-AuditorTraversalTest']) for reg in regions]+[(reg['id']+'-boundary',reg['map'],['-AuditorBoundaryTest']) for reg in regions]+[(reg['id']+'-interact',reg['map'],['-AuditorAncientInteractionTest']) for reg in regions]
if os.getenv('ANCIENT_TEST_NAMES'):jobs=[j for j in jobs if j[0] in os.environ['ANCIENT_TEST_NAMES'].split(',')]
def run(job):
 name,map,flags=job;log=out/(name+'.log');start=time.time()
 cmd=['/opt/UnrealEngine_5.6/Engine/Binaries/Linux/UnrealEditor',str(r/'project/AncientChineseCity.uproject'),map,'-game','-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorTestExit',*flags]
 with log.open('w') as f:
  try:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=75).returncode
  except subprocess.TimeoutExpired:code=-1
 text=log.read_text(errors='replace');lines=[v for v in text.splitlines() if any(k in v for k in ['AUDITOR_TASK_TEST','AUDITOR_TRAVERSAL_TEST','AUDITOR_BOUNDARY_TEST'])];ok=code==0 and any(' PASS ' in v for v in lines)
 result={'name':name,'ok':ok,'code':code,'seconds':round(time.time()-start,1),'markers':lines};print(json.dumps(result),flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,jobs))
(out/'report.json').write_text(json.dumps(results,indent=2));raise SystemExit(0 if all(v['ok'] for v in results) else 1)
