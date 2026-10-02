"""Publish the verified ancient append while preserving the complete current review state."""
from pathlib import Path
import json,shutil,sqlite3,subprocess,hashlib,datetime,tempfile,urllib.request,time,os
root=Path('/home/ubuntu/unreal-auditor/review-service');stage=Path(__file__).resolve().parent
state=root/'state';release=root/'releases/ancient-20260912';base=root/'releases/core18-20260911'
def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True)
def fingerprint(db):
 return {name:hashlib.sha256(json.dumps(db.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall(),ensure_ascii=False).encode()).hexdigest() for name in ('feedback','review_history','evidence')}
def active(db):return db.execute("SELECT count(*) FROM sessions WHERE status IN ('queued','starting','ready','resetting','switching','closing')").fetchone()[0]
def ro():return sqlite3.connect('file:'+str(state/'review.sqlite3')+'?mode=ro',uri=True)
assert not release.exists()
expected=json.loads((stage/'source-release-hashes.json').read_text())
for name,sha in expected.items():assert hashlib.sha256((base/name).read_bytes()).hexdigest()==sha,('Current base changed',name)
current=(state/'tasks.json').read_bytes()
assert hashlib.sha256(current).hexdigest()==(stage/'prepared-state/source-catalog.sha256').read_text()
manifest=json.loads((stage/'tasks.json').read_text());old=json.loads(current)
assert [t for t in manifest['tasks'] if t.get('family')!='ancient']==old['tasks']
import server
with tempfile.TemporaryDirectory() as tmp:
 s=server.Store(Path(tmp)/'db',manifest);s.db.close()
db=ro();assert active(db)==0,'Active reviewers: wait before deployment';before=fingerprint(db)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
backup=root/'backups'/('ancient-'+stamp);backup.mkdir(mode=0o700)
with sqlite3.connect(backup/'review.sqlite3') as copy:db.backup(copy)
db.close()
for name in ('tasks.json','runtime.json','service-env.json','participants.json'):shutil.copy2(state/name,backup/name)
shutil.copytree(stage,release,ignore=shutil.ignore_patterns('prepared-state','preview','__pycache__'))
env=json.loads((stage/'prepared-state/service-env.json').read_text())
if 'REVIEW_RUNNER_JSON' in env:
 argv=json.loads(env['REVIEW_RUNNER_JSON']);env['REVIEW_RUNNER_JSON']=json.dumps([str(release/'runtime/mac_runner.py') if x.endswith('/runtime/mac_runner.py') else x for x in argv])
config=json.loads((stage/'prepared-state/runtime.json').read_text())
oldconfig=json.loads((state/'runtime.json').read_text())
assert config['capacity']==oldconfig['capacity']==3
for key,value in oldconfig['launch_profiles'].items():assert config['launch_profiles'][key]==value
drop=Path('/etc/systemd/system/urban-review-pilot.service.d/95-ancient.conf')
assert not drop.exists()
unit="[Service]\nWorkingDirectory="+str(release)+"\nExecStart=\nExecStart=/usr/bin/python3 "+str(release/'runtime/start_linux.py')+" "+str(state)+"\n"
unitfile=backup/'95-ancient.conf';unitfile.write_text(unit)
db=ro();assert active(db)==0;db.close()
run('sudo','systemctl','stop','urban-review-pilot.service')
try:
 for name,data in [('tasks.json',manifest),('runtime.json',config),('service-env.json',env)]:
  temp=state/(name+'.ancient-new');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(state/name)
 run('sudo','cp',str(unitfile),str(drop));run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service')
 for i in range(30):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8092/health',timeout=2) as response:health=json.load(response)
   break
  except Exception:
   if i==29:raise
   time.sleep(1)
 db=ro();assert fingerprint(db)==before;assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
 (backup/'report.json').write_text(json.dumps(dict(status='PASS',release=str(release),tasks=len(manifest['tasks']),protected_fingerprints=before,health=health),indent=2))
 print(json.dumps(dict(status='PASS',release=str(release),backup=str(backup),tasks=len(manifest['tasks']))))
except Exception:
 run('sudo','systemctl','stop','urban-review-pilot.service')
 for name in ('tasks.json','runtime.json','service-env.json'):shutil.copy2(backup/name,state/name)
 if drop.exists():run('sudo','rm',str(drop))
 run('sudo','systemctl','daemon-reload');run('sudo','systemctl','start','urban-review-pilot.service')
 raise

