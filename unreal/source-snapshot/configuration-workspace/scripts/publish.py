from pathlib import Path
import json,subprocess,sqlite3,hashlib,shutil,datetime,time,urllib.request
root=Path('/home/ubuntu/unreal-auditor');work=root/'configuration-workspace';service=root/'review-service';state=service/'state'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True)
def dbopen():return sqlite3.connect('file:'+str(state/'review.sqlite3')+'?mode=ro',uri=True)
def idle(db):return db.execute("select count(*) from sessions where status in ('queued','starting','ready','resetting','switching','closing')").fetchone()[0]==0
def protected(db):
 tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
 return {n:hashlib.sha256(json.dumps(db.execute('select * from '+n+' order by rowid').fetchall(),ensure_ascii=False).encode()).hexdigest() for n in ['feedback','review_history','evidence','logins','events','participants'] if n in tables}
proof=read(work/'out/review-proof.json');source=Path(proof['source_release']);stage=Path(proof['stage']);release=service/'releases'/stage.name
assert run('systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value').stdout.strip()==str(source),'Live release changed'
for n,h in proof['state_hashes'].items():assert sha(state/n)==h,('Live state changed',n)
for n,h in proof['source_hashes'].items():assert sha(source/n)==h,('Live source changed',n)
log=(work/'out/service-tests.log').read_text();assert 'Ran 133 tests' in log and log.rstrip().endswith('OK')
assert read(work/'out/runtime-validation.json')['status']=='PASS'
assert all(r['ok'] for r in read(work/'out/render-a21/report.json'))
assert all(r['ok'] for r in read(work/'out/reuse-a21/report.json'))
assert read(root/'ancient-workspace/out/ac-v2/configuration-v3-verification.json')
checks=0
for family in ['subway','indoor','ancient','industrial','medieval']:
 for prefix in ['tests-','regression-','reuse-']:
  rows=read(work/'out'/(prefix+family)/'report.json');assert rows and all(r['ok'] for r in rows),(prefix,family);checks+=len(rows)
for r in read(work/'out/render-urban/report.json'):assert r['ok']
for family in ['subway','indoor','ancient','industrial','medieval','urban']:
 b=read(work/'out'/('build-'+family+'.json'));assert sha(Path(b['binary']))==b['binary_sha256']
manifest=read(stage/'tasks.json');runtime=read(stage/'candidate-runtime.json');assert len(manifest['tasks'])==253 and runtime['capacity']==3
for t in manifest['tasks']:
 if t.get('family') in ['subway','indoor','ancient','industrial','medieval'] or t['id']=='U046':assert runtime['launch_profiles'][t['map']]['build_sha256']==t['build_sha256']
assert not release.exists();db=dbopen();assert idle(db),'WAIT_ACTIVE_REVIEWERS';before=protected(db)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S');backup=service/'backups'/('configuration-'+stamp);backup.mkdir(mode=0o700)
with sqlite3.connect(backup/'review.sqlite3') as dest:db.backup(dest)
db.close()
for n in proof['state_hashes']:shutil.copy2(state/n,backup/n)
shutil.copytree(stage,release,ignore=shutil.ignore_patterns('__pycache__','candidate-runtime.json'))
env=read(state/'service-env.json')
if 'REVIEW_RUNNER_JSON' in env:env['REVIEW_RUNNER_JSON']=json.dumps([str(release/'runtime/mac_runner.py') if str(v).endswith('/runtime/mac_runner.py') else v for v in json.loads(env['REVIEW_RUNNER_JSON'])])
drop=Path('/etc/systemd/system/urban-review-pilot.service.d/'+('z'*18)+'-configuration.conf');assert not drop.exists();unit=backup/drop.name;unit.write_text('[Service]\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/usr/bin/python3 '+str(release/'runtime/start_linux.py')+' '+str(state)+'\n')
db=dbopen();assert idle(db),'Reviewer arrived';assert protected(db)==before;db.close();run('sudo','systemctl','stop','urban-review-pilot.service')
try:
 db=dbopen();assert idle(db),'Reviewer arrived during stop';db.close()
 for n,data in [('tasks.json',manifest),('runtime.json',runtime),('service-env.json',env)]:
  temp=state/(n+'.configuration-new');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.chmod(0o600);temp.replace(state/n)
 run('sudo','cp',str(unit),str(drop));run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service')
 for attempt in range(30):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8092/health',timeout=2) as f:json.load(f)
   break
  except Exception:
   if attempt==29:raise
   time.sleep(1)
 assert run('systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value').stdout.strip()==str(release)
 db=dbopen();assert protected(db)==before;assert db.execute('pragma integrity_check').fetchone()[0]=='ok';db.close();assert sha(state/'participants.json')==proof['state_hashes']['participants.json']
 report=dict(status='PASS',release=str(release),backup=str(backup),native_checks=checks,service_checks=133,entries=253,protected_tables=list(before),participants_preserved=True,capacity=3)
 (work/'out/deployment-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
except Exception:
 run('sudo','systemctl','stop','urban-review-pilot.service')
 for n in ['tasks.json','runtime.json','service-env.json']:shutil.copy2(backup/n,state/n)
 if drop.exists():run('sudo','rm',str(drop))
 run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service');raise
