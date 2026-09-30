from pathlib import Path
import subprocess,json,os,time,concurrent.futures
root=Path(__file__).resolve().parents[1];packaged=os.getenv('RURAL_PACKAGED')=='1';render=os.getenv('RURAL_RENDER')=='1'
out=root/'out'/('tests-packaged' if packaged else 'tests-uncooked');out.mkdir(exist_ok=True)
tasks=json.loads((root/'environments/rural-australia/tasks.json').read_text())['tasks'];regions=json.loads((root/'environments/rural-australia/regions.json').read_text())['regions']
jobs=[(t['id'],t['map']+'?Task='+t['id'],['-AuditorTaskTest']) for t in tasks]+[(r['id']+'-walk',r['map'],['-AuditorTraversalTest']) for r in regions]+[(r['id']+'-boundary',r['map'],['-AuditorBoundaryTest']) for r in regions]
if os.getenv('RURAL_TEST_NAMES'):jobs=[j for j in jobs if j[0] in os.environ['RURAL_TEST_NAMES'].split(',')]
def run(j):
 name,m,flags=j;start=time.time();log=out/(name+('-render' if render else '')+'.log')
 cmd=[str(root/'dist/rural-linux-v3/Linux/RuralAustralia/Binaries/Linux/RuralAustralia')] if packaged else ['/opt/UnrealEngine_5.6/Engine/Binaries/Linux/UnrealEditor',str(root/'project/RuralAustralia.uproject')]
 cmd += [m,'-game','-nosound','-unattended','-AuditorRemoteInput','-AuditorTestExit','-ExecCmds=t.MaxFPS 30',*flags]
 cmd += ['-RenderOffscreen','-vulkan','-sm5','-ResX=1280','-ResY=720','-ForceRes'] if render else ['-nullrhi']
 if render and '-AuditorTaskTest' in flags:cmd += ['-AuditorCaptureOnTest='+str(out/(name+'.png'))]
 with log.open('w') as f:
  try:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=240 if render else 100).returncode
  except subprocess.TimeoutExpired:code=-1
 txt=log.read_text(errors='replace');markers=[l for l in txt.splitlines() if any(k in l for k in ['AUDITOR_TASK_TEST','AUDITOR_BOUNDARY_TEST','AUDITOR_TRAVERSAL_TEST'])];r=dict(name=name,ok=code==0 and any(' PASS ' in l for l in markers),code=code,seconds=round(time.time()-start,1),markers=markers);print(json.dumps(r),flush=True);return r
with concurrent.futures.ThreadPoolExecutor(max_workers=1 if render else 2) as pool:results=list(pool.map(run,jobs))
(out/('report-render.json' if render else 'report.json')).write_text(json.dumps(results,indent=2));raise SystemExit(0 if all(x['ok'] for x in results) else 1)
