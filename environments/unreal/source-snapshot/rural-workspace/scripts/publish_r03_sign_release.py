"""Publish the validated revised map only while the shared review queue is idle."""
from pathlib import Path
import json,subprocess,sqlite3,hashlib,shutil,datetime,time,urllib.request
root=Path('/home/ubuntu/unreal-auditor');work=root/'rural-workspace';service=root/'review-service';state=service/'state'
def read(p):return json.loads(p.read_text())
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def run(*a):return subprocess.run(a,check=True,capture_output=True,text=True)
def database():return sqlite3.connect('file:'+str(state/'review.sqlite3')+'?mode=ro',uri=True)
def idle(db):return db.execute('select count(*) from sessions where status in (?,?,?,?,?,?)',('queued','starting','ready','resetting','switching','closing')).fetchone()[0]==0
protected_tables=['feedback','review_history','evidence','logins','events']
def protected(db):return {n:hashlib.sha256(json.dumps(db.execute('select * from '+n+' order by rowid').fetchall(),ensure_ascii=False).encode()).hexdigest() for n in protected_tables}
proof=read(work/'out/r03-sign-release-candidate.json');stage=Path(proof['stage']);release=service/'releases'/stage.name
assert Path(run('systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value').stdout.strip())==Path(proof['source_release']),'Live release changed; rebuild candidate'
for n,h in proof['source_state_sha256'].items():assert digest(state/n)==h,(n,'changed; rebuild candidate')
for n,h in proof['source_files'].items():assert digest(Path(proof['source_release'])/n)==h,('Live source changed',n)
checks=read(work/'out/variety-v6/tests-packaged/report.json');assert len(checks)==24 and all(x['ok'] for x in checks)
reuse=read(work/'out/variety-v6/reuse/report.json');assert len(reuse)==18 and all(x['ok'] for x in reuse)
# Wire geometry is unchanged; its full-world browser walk proof remains applicable.
walk=read(work/'out/variety-v5/wire-walk-report.json');assert walk['status']=='PASS' and len(walk['runs'])==3
render=read(work/'out/variety-v6/tests-packaged/report-render.json');assert len(render)==1 and render[0]['name']=='R03' and render[0]['ok']
manifest=read(stage/'tasks.json');config=read(stage/'candidate-runtime.json');old=read(state/'tasks.json');oldconfig=read(state/'runtime.json')
assert [t for t in manifest['tasks'] if t.get('family')!='rural']==[t for t in old['tasks'] if t.get('family')!='rural']
assert len([t for t in manifest['tasks'] if t.get('family')=='rural'])==21
assert config['capacity']==oldconfig['capacity']==3
for k,v in oldconfig['launch_profiles'].items():
 assert config['launch_profiles'][k]==(v|{'binary':proof['build']} if v.get('family')=='rural' else v)
for p in config['launch_profiles'].values():
 if p.get('family')=='rural':assert digest(Path(p['binary']))==p['build_sha256']==read(work/'dist/rural-linux-v6/build-provenance.json')['binary_sha256']
log=(work/'out/r03-sign-review-tests.log').read_text();assert 'Ran 130 tests' in log and log.rstrip().endswith('OK'), 'Review service checks incomplete'
assert not release.exists()
db=database()
if not idle(db):
 db.close();raise SystemExit('WAIT_ACTIVE_REVIEWERS: candidate is ready; publish again when the shared queue is idle.')
before=protected(db);stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S');backup=service/'backups'/('rural-r03-sign-'+stamp);backup.mkdir(mode=0o700)
with sqlite3.connect(backup/'review.sqlite3') as dest:db.backup(dest)
db.close()
for n in ['tasks.json','runtime.json','service-env.json','participants.json']:shutil.copy2(state/n,backup/n)
identity_sha=digest(state/'participants.json')
shutil.copytree(stage,release,ignore=shutil.ignore_patterns('__pycache__','candidate-runtime.json','prepared-state'))
env=read(state/'service-env.json')
if 'REVIEW_RUNNER_JSON' in env:env['REVIEW_RUNNER_JSON']=json.dumps([str(release/'runtime/mac_runner.py') if str(v).endswith('/runtime/mac_runner.py') else v for v in json.loads(env['REVIEW_RUNNER_JSON'])])
drop=Path('/etc/systemd/system/urban-review-pilot.service.d/zzzzzzzzzzzz-rural-r03-sign.conf');assert not drop.exists()
unit=backup/drop.name;unit.write_text('[Service]\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/usr/bin/python3 '+str(release/'runtime/start_linux.py')+' '+str(state)+'\n')
db=database();assert idle(db),'Reviewer arrived; retry after idle';assert protected(db)==before;db.close()
run('sudo','systemctl','stop','urban-review-pilot.service')
try:
 db=database();assert idle(db),'Reviewer arrived during stop; rolling back';db.close()
 for n,data in [('tasks.json',manifest),('runtime.json',config),('service-env.json',env)]:
  temp=state/(n+'.rural-new');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(state/n)
 run('sudo','cp',str(unit),str(drop));run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service')
 for attempt in range(30):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8092/health',timeout=2) as f:health=json.load(f)
   break
  except Exception:
   if attempt==29:raise
   time.sleep(1)
 assert run('systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value').stdout.strip()==str(release)
 db=database();assert protected(db)==before,'Protected review state changed';assert db.execute('pragma integrity_check').fetchone()[0]=='ok';db.close();assert digest(state/'participants.json')==identity_sha
 report=dict(status='PASS',release=str(release),backup=str(backup),health=health,revised=proof['revised'],changed_scenarios=proof['changed_scenarios'],total_entries=len(old['tasks']),capacity=3,protected_tables=protected_tables,participants_preserved=True,build_sha256=read(work/'dist/rural-linux-v6/build-provenance.json')['binary_sha256'])
 (work/'out/r03-sign-deployment-report.json').write_text(json.dumps(report,indent=2));(release/'rural-r03-sign-deployment-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
except Exception:
 run('sudo','systemctl','stop','urban-review-pilot.service')
 for n in ['tasks.json','runtime.json','service-env.json']:shutil.copy2(backup/n,state/n)
 if drop.exists():run('sudo','rm',str(drop))
 run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service');raise
