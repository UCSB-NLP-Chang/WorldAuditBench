from pathlib import Path
import json,subprocess,sys,concurrent.futures
w=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20-car-replacement');cfg=json.loads(Path('/home/ubuntu/unreal-auditor/configuration-workspace/projects.json').read_text());jobs=[]
for family in sys.argv[1:]:
 s=cfg[family];root=Path(s['workspace']);env={'subway':'subway','indoor':'residential-house','ancient':'ancient-chinese-city','industrial':'industrial-factory','medieval':'medieval-village'}[family];tasks=json.loads((root/'environments'/env/'tasks.json').read_text())['tasks'];regions=json.loads((root/'environments'/env/'regions.json').read_text())['regions'];maps={r['id']:r['map'] for r in regions};binary=json.loads((w/'out/build.json').read_text())['binary']
 for t in tasks:
  for control in ([False,True] if family=='indoor' else [False]):jobs.append((family,t['id']+('-clean' if control else ''),binary,maps[t['region']]+'?Task='+t['id'],['-AuditorTaskTest']+(['-AuditorControl'] if control else [])))
 for r in regions:
  for kind in ['Traversal','Boundary']:jobs.append((family,r['id']+'-'+kind,binary,r['map'],['-Auditor'+kind+'Test']))
 if family=='ancient':
  for r in regions:jobs.append((family,r['id']+'-interact',binary,r['map'],['-AuditorAncientInteractionTest']))
 if family=='medieval':
  for r in regions:jobs.append((family,r['id']+'-interact',binary,r['map'],['-AuditorMedievalInteractionTest']))
def run(job):
 family,name,binary,map,flags=job;out=w/'out'/('regression-'+family);out.mkdir(exist_ok=True);log=out/(name+'.log')
 with log.open('w') as stream:
  try:code=subprocess.run([binary,map,'-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorTestExit','-ExecCmds=t.MaxFPS 30',*flags],stdout=stream,stderr=subprocess.STDOUT,timeout=100).returncode
  except subprocess.TimeoutExpired:code=-1
 text=log.read_text(errors='replace');markers=[x for x in text.splitlines() if any(k in x for k in ['AUDITOR_TASK_TEST','AUDITOR_TRAVERSAL_TEST','AUDITOR_BOUNDARY_TEST'])];ok=code==0 and any(' PASS ' in x for x in markers);result={'family':family,'name':name,'ok':ok,'code':code,'markers':markers};print(json.dumps(result),flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,jobs))
for family in sys.argv[1:]:
 rows=[r for r in results if r['family']==family];(w/'out'/('regression-'+family)/'report.json').write_text(json.dumps(rows,indent=2))
raise SystemExit(0 if all(x['ok'] for x in results) else 1)
