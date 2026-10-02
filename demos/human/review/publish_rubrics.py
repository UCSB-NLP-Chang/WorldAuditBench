from pathlib import Path
import json,subprocess,sqlite3,shutil,hashlib,datetime,time,urllib.request
root=Path('/home/ubuntu/unreal-auditor/review-service');state=root/'state';stage=root/'staging/ancient-concise-rubrics-20260912';release=root/'releases/ancient-concise-rubrics-20260912'
def run(*a):return subprocess.run(a,check=True,capture_output=True,text=True)
def ro():return sqlite3.connect('file:'+str(state/'review.sqlite3')+'?mode=ro',uri=True)
def protected(db):return {n:hashlib.sha256(json.dumps(db.execute('select * from '+n+' order by rowid').fetchall(),ensure_ascii=False).encode()).hexdigest() for n in ['feedback','review_history','evidence']}
def idle(db):return db.execute("select count(*) from sessions where status in ('queued','starting','ready','resetting','switching','closing')").fetchone()[0]==0
proof=json.loads((stage/'rubric-provenance.json').read_text())
for n,h in proof['source_state_sha256'].items():assert hashlib.sha256((state/n).read_bytes()).hexdigest()==h,(n,'changed')
manifest=json.loads((stage/'tasks.json').read_text());config=json.loads((stage/'candidate-runtime.json').read_text())
old=json.loads((state/'tasks.json').read_text());oldconfig=json.loads((state/'runtime.json').read_text())
def stable_task(t):return {k:v for k,v in t.items() if k not in ('rubrics','rubrics_i18n')}
assert [stable_task(t) for t in manifest['tasks'] ]==[stable_task(t) for t in old['tasks'] ]
for k,p in oldconfig['launch_profiles'].items():
 assert p==config['launch_profiles'][k]
assert config['capacity']==oldconfig['capacity']==3
assert [t for t in manifest['tasks'] if t.get('family')!='ancient' or t.get('case_type')=='baseline']==[t for t in old['tasks'] if t.get('family')!='ancient' or t.get('case_type')=='baseline']
db=ro();assert idle(db),'Active reviewers';before=protected(db)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S');backup=root/'backups'/('ancient-concise-rubrics-'+stamp);backup.mkdir(mode=0o700)
with sqlite3.connect(backup/'review.sqlite3') as dst:db.backup(dst)
db.close()
for n in ['tasks.json','runtime.json','service-env.json','participants.json']:shutil.copy2(state/n,backup/n)
assert not release.exists()
shutil.copytree(stage,release,ignore=shutil.ignore_patterns('__pycache__','candidate-runtime.json'))
env=json.loads((state/'service-env.json').read_text())
if 'REVIEW_RUNNER_JSON' in env:
 argv=json.loads(env['REVIEW_RUNNER_JSON']);env['REVIEW_RUNNER_JSON']=json.dumps([str(release/'runtime/mac_runner.py') if v.endswith('/runtime/mac_runner.py') else v for v in argv])
drop=Path('/etc/systemd/system/urban-review-pilot.service.d/zzzzzz-ancient-concise-rubrics.conf');assert not drop.exists()
unit=backup/'zzzzzz-ancient-concise-rubrics.conf';unit.write_text('[Service]\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/usr/bin/python3 '+str(release/'runtime/start_linux.py')+' '+str(state)+'\n')
db=ro();assert idle(db);db.close()
run('sudo','systemctl','stop','urban-review-pilot.service')
try:
 for n,data in [('tasks.json',manifest),('runtime.json',config),('service-env.json',env)]:
  tmp=state/(n+'.performance-new');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(state/n)
 run('sudo','cp',str(unit),str(drop));run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service')
 for i in range(30):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8092/health',timeout=2) as f:health=json.load(f)
   break
  except Exception:
   if i==29:raise
   time.sleep(1)
 db=ro();assert protected(db)==before;assert db.execute('pragma integrity_check').fetchone()[0]=='ok';db.close()
 report=dict(taxonomy_version='user-2026-09-12-scene-semantics',status='PASS',release=str(release),backup=str(backup),protected_fingerprints=before,health=health,ancient_revision=5)
 (backup/'report.json').write_text(json.dumps(report,indent=2));(stage/'deployment-report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='protected_fingerprints'}))
except Exception:
 run('sudo','systemctl','stop','urban-review-pilot.service')
 for n in ['tasks.json','runtime.json','service-env.json']:shutil.copy2(backup/n,state/n)
 if drop.exists():run('sudo','rm',str(drop))
 run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service');raise
