from pathlib import Path
import sqlite3,json,hashlib,subprocess,sys,time
p=Path('/home/ec2-user/unreal-production');c=Path('/home/ec2-user/unreal-review-releases/concourse-cleanup-20260918');base=Path('/home/ec2-user/unreal-review-releases/exploration-v2-preview-20260917')
def votes():
 with sqlite3.connect('file:'+str(p/'audit/review.sqlite3')+'?mode=ro',uri=True) as d:
  rows=d.execute('SELECT id,session_id,owner,created,payload FROM feedback ORDER BY id').fetchall()
 return hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()
with sqlite3.connect('file:'+str(p/'audit/review.sqlite3')+'?mode=ro',uri=True) as d:
 assert not d.execute("SELECT count(*) FROM sessions WHERE status IN ('queued','starting','ready','resetting','switching','closing')").fetchone()[0],'Review in use; prepared release retained'
v=votes();before=json.loads((p/'audit/tasks.json').read_text());subprocess.run([sys.executable,str(c/'activate_staged.py'),'--production',str(p),'--base',str(base),'--completion',str(c)],check=True)
after=json.loads((p/'audit/tasks.json').read_text());assert len(after['tasks'])==len(before['tasks']);assert votes()==v
old={t['id']:t for t in before['tasks']};ids={'B01','S01','S07','S09','S12','S14','S22'}
for t in after['tasks']:
 if t['id'] not in ids:assert t==old[t['id']]
 else:
  assert t['rubrics_i18n']==old[t['id']]['rubrics_i18n']
  assert {k:old[t['id']][k] for k in ['revision','sha256','build_sha256']} in t['review_compatible_versions']
report={'status':'published','feedback_unchanged':True,'other_tasks_unchanged':True,'previous_approvals_compatible':True,'total_tasks':len(after['tasks']),'unreal_tasks':sum(t.get('map','').startswith('/Game/') for t in after['tasks']),'affected':sorted(ids),'time':time.time()};(c/'publication-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
