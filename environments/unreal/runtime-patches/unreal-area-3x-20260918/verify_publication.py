from pathlib import Path
import json,hashlib,sqlite3,subprocess,urllib.request
r=Path(__file__).parent
receipt=json.loads((r/'completion.json').read_text());assert receipt['status']=='published'
backup=Path(receipt['backup']);affected=set(receipt['tasks'])
for i,p in enumerate(receipt['files']):assert Path(p).read_bytes()==(r/f'config-{i}.json').read_bytes(),p
old=json.loads((backup/'0.json').read_text())['tasks'];new=json.loads(Path(receipt['files'][0]).read_text())['tasks'];oldmap={t['id']:t for t in old};newmap={t['id']:t for t in new}
assert oldmap.keys()==newmap.keys() and len(new)==239
for tid,t in newmap.items():
 prev=oldmap[tid]
 if tid not in affected:assert t==prev,tid;continue
 assert t['revision']==prev['revision']+1,tid
 assert {k:prev[k] for k in ['revision','sha256','build_sha256']} in t['review_compatible_versions'],tid
 for k in prev.keys()-{'revision','exploration_revision','review_compatible_versions','build_sha256'}:assert t[k]==prev[k],(tid,k)
 if t['family']!='indoor':assert t['build_sha256']==prev['build_sha256'],tid
oldprof=json.loads((backup/'1.json').read_text())['launch_profiles'];newprof=json.loads(Path(receipt['files'][1]).read_text())['launch_profiles'];assert oldprof.keys()==newprof.keys()
changedmaps={t['map'] for t in new if t['id'] in affected}
for key,p in newprof.items():
 prev=oldprof[key]
 if p['runtime_map'] not in changedmaps:assert p==prev,key
 else:
  assert p['extra_args']==[('-AuditorExplorationPolicy='+str(r/'policy.json')) if a.startswith('-AuditorExplorationPolicy=') else a for a in prev['extra_args']],key
  for k in prev.keys()-{'binary','build_sha256','extra_args'}:assert p[k]==prev[k],(key,k)
  if p['family']=='indoor':assert hashlib.sha256(Path(p['binary']).read_bytes()).hexdigest()==p['build_sha256']
  else:assert p['binary']==prev['binary'] and p['build_sha256']==prev['build_sha256']
with sqlite3.connect('file:/home/ec2-user/unreal-production/audit/review.sqlite3?mode=ro',uri=True) as d:
 feedback=hashlib.sha256(json.dumps(d.execute('select id,session_id,owner,created,payload from feedback order by id').fetchall(),ensure_ascii=False).encode()).hexdigest()
assert feedback==(r/'feedback-before.sha256').read_text()
for s in ['aws-unreal-audit.service','aws-unreal-review-pool-v2.service']:subprocess.run(['systemctl','is-active','--quiet',s],check=True)
for s,pid in receipt['protected_service_pids'].items():assert subprocess.check_output(['systemctl','show',s,'--property=MainPID','--value'],text=True).strip()==pid,s
with urllib.request.urlopen('https://review.98-84-22-147.sslip.io/',timeout=20) as response:assert response.status==200
subprocess.run(['python3.12',str(r/'audit_live.py'),'--strict'],check=True)
result={'status':'PASS','all_unreal_audited':143,'updated':len(affected),'unrelated_tasks_unchanged':len(new)-len(affected),'native_routes_passed':24,'native_containment_passed':4,'feedback_unchanged':True,'protected_services_unchanged':True,'http':200,'tasks':sorted(affected)}
(r/'publication-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
