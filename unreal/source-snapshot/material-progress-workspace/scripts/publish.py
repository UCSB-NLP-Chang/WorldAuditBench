"""Publish the verified material/progress release, preserving live review state."""
from pathlib import Path
import json,subprocess,sqlite3,hashlib,shutil,datetime,time,urllib.request
from revise import manifest,VERSION
root=Path('/home/ubuntu/unreal-auditor');work=root/'material-progress-workspace';service=root/'review-service';state=service/'state'
def read(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True)
def database():return sqlite3.connect('file:'+str(state/'review.sqlite3')+'?mode=ro',uri=True)
def idle(db):return not db.execute("SELECT count(*) FROM sessions WHERE status IN ('queued','starting','ready','resetting','switching','closing')").fetchone()[0]
def protected(db):
 tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 return {n:hashlib.sha256(json.dumps(db.execute('SELECT * FROM '+n+' ORDER BY rowid').fetchall(),ensure_ascii=False).encode()).hexdigest() for n in ['feedback','review_history','evidence','logins','events','participants'] if n in tables}
proof=read(work/'proof.json');stage=Path(proof['stage']);source=Path(proof['source_release']);release=service/'releases'/stage.name
assert Path(run('systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value').stdout.strip())==source,'Live release changed: rebase first'
for n,h in proof['source_state_sha256'].items():assert digest(state/n)==h,(n,'changed: rebase first')
for n,h in proof['source_files'].items():assert digest(source/n)==h,(n,'changed: rebase first')
validation=read(work/'validation.json');assert validation['result']=='PASS'
for n,h in validation['candidate_hashes'].items():assert digest(stage/n)==h,('Candidate changed',n)
assert (work/'tests.log').read_text().rstrip().endswith('OK')
assert read(work/'browser-report.json')['result']=='PASS'
catalog=read(stage/'tasks.json');assert catalog==manifest(read(state/'tasks.json'))
assert not release.exists()
db=database();assert idle(db),'WAIT_ACTIVE_REVIEWERS';before=protected(db)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S');backup=service/'backups'/('material-progress-'+stamp);backup.mkdir(mode=0o700)
with sqlite3.connect(backup/'review.sqlite3') as dst:db.backup(dst)
db.close()
for n in ['tasks.json','runtime.json','service-env.json','participants.json']:shutil.copy2(state/n,backup/n)
shutil.copytree(stage,release,ignore=shutil.ignore_patterns('__pycache__','candidate-runtime.json'))
env=read(state/'service-env.json')
if 'REVIEW_RUNNER_JSON' in env:env['REVIEW_RUNNER_JSON']=json.dumps([str(release/'runtime/mac_runner.py') if str(v).endswith('/runtime/mac_runner.py') else v for v in json.loads(env['REVIEW_RUNNER_JSON'])])
dropdir=Path('/etc/systemd/system/urban-review-pilot.service.d')
zcount=max(len(p.name)-len(p.name.lstrip('z')) for p in dropdir.glob('*.conf'))+1
drop=dropdir/('z'*zcount+'-material-progress.conf');assert not drop.exists()
unit=backup/drop.name;unit.write_text('[Service]\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/usr/bin/python3 '+str(release/'runtime/start_linux.py')+' '+str(state)+'\n')
db=database();assert idle(db),'WAIT_ACTIVE_REVIEWERS';assert protected(db)==before;db.close()
run('sudo','systemctl','stop','urban-review-pilot.service')
try:
 db=database();assert idle(db),'Reviewer arrived during stop';assert protected(db)==before;db.close()
 for n,data in [('tasks.json',catalog),('service-env.json',env)]:
  tmp=state/(n+'.material-new');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');tmp.chmod(0o600);tmp.replace(state/n)
 run('sudo','cp',str(unit),str(drop));run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service')
 for attempt in range(30):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8092/health',timeout=2) as response:assert json.load(response)['ok']
   break
  except Exception:
   if attempt==29:raise
   time.sleep(1)
 assert run('systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value').stdout.strip()==str(release)
 db=database();assert protected(db)==before;assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
 for n in ['runtime.json','participants.json']:assert digest(state/n)==proof['source_state_sha256'][n]
 report={'result':'PASS','release':str(release),'backup':str(backup),'entries':len(catalog['tasks']),'taxonomy_version':VERSION,'protected_tables':list(before),'runtime_preserved':True,'participants_preserved':True}
 (work/'deployment-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
except Exception:
 run('sudo','systemctl','stop','urban-review-pilot.service')
 for n in ['tasks.json','service-env.json']:shutil.copy2(backup/n,state/n)
 if drop.exists():run('sudo','rm',str(drop))
 run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service');raise
