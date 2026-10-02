from pathlib import Path
import subprocess,json,concurrent.futures,time,os
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace')
out=Path(os.getenv('ANCIENT_TEST_OUTPUT',str(r/'out/tests-streaming2')));out.mkdir(exist_ok=True)
binary=Path(os.getenv('ANCIENT_TEST_BINARY',str(r/'dist/ancient-linux-streaming2/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity')))
tasks=json.loads((r/'environments/ancient-chinese-city/tasks.json').read_text())['tasks']
regions=json.loads((r/'environments/ancient-chinese-city/regions.json').read_text())['regions']
jobs=[(t['id'],t['map']+'?Task='+t['id'],['-AuditorTaskTest']) for t in tasks]+[(reg['id']+'-walk',reg['map'],['-AuditorTraversalTest']) for reg in regions]+[(reg['id']+'-boundary',reg['map'],['-AuditorBoundaryTest']) for reg in regions]+[(reg['id']+'-interact',reg['map'],['-AuditorAncientInteractionTest']) for reg in regions]
jobs += [('courtyard-stairs','/Game/Auditor/AncientCity/Courtyard',['-AuditorAncientStairTest'])]
if os.getenv('ANCIENT_TEST_NAMES'):jobs=[j for j in jobs if j[0] in os.environ['ANCIENT_TEST_NAMES'].split(',')]
# Match the published 30 FPS simulation cadence; unbounded NullRHI is not a gameplay timing test.
def run(job):
 name,map,flags=job;log=out/(name+'.log');start=time.time()
 with log.open('w') as f:
  try:code=subprocess.run([str(binary),map,'-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorTestExit','-ExecCmds=t.MaxFPS 30',*flags],stdout=f,stderr=subprocess.STDOUT,timeout=80).returncode
  except subprocess.TimeoutExpired:code=-1
 content=log.read_text(errors='replace');lines=[v for v in content.splitlines() if any(k in v for k in ['AUDITOR_TASK_TEST','AUDITOR_TRAVERSAL_TEST','AUDITOR_BOUNDARY_TEST'])]
 result={'name':name,'ok':code==0 and any(' PASS ' in v for v in lines),'code':code,'seconds':round(time.time()-start,1),'markers':lines};print(json.dumps(result),flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,jobs))
(out/'report.json').write_text(json.dumps(results,indent=2));raise SystemExit(0 if all(v['ok'] for v in results) else 1)

