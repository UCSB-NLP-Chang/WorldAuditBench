from pathlib import Path
import json,sqlite3,subprocess as sp,time,urllib.request,hashlib
r=Path('/home/ubuntu/unreal-auditor/bug-finding-pilot');b=r/'backups/guided-exploration-v17';b.mkdir(exist_ok=False)
versions={'exploration':('admin-coverage-v16','guided-explore-v17'),'evaluation':('login-select-evaluate-v15','guided-evaluate-v17')}
config_path=r/'config/exploration.json';original_config=config_path.read_text();(b/'exploration.json').write_text(original_config)
guidance=json.loads((r/'imports/human-guidance-v17.json').read_text());assert sum(bool(v) for v in guidance.values())==233
new_config=json.loads(original_config);new_config['human_guidance']=guidance
assert set(guidance)<=set(t['id'] for t in new_config['tasks'])
def run(*a):sp.run(a,check=True)
def fingerprint():
 paths=list((r/'config').glob('*.json'))+[Path('/home/ubuntu/unreal-auditor/review-service/state')/n for n in ('tasks.json','runtime.json','service-env.json','participants.json')]
 return {'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'services':{s:sp.check_output(['systemctl','show',s,'-p','MainPID','-p','ExecMainStartTimestamp','-p','ActiveState'],text=True) for s in ('urban-review-pilot','review-web','subway-review','threejs-environments')}}
before=fingerprint();(b/'before.json').write_text(json.dumps(before));units={}
for app,(old,new) in versions.items():
 p=Path('/etc/systemd/system/bug-finding-'+app+'.service');units[app]=p.read_text();assert str(r/'releases'/old) in units[app]
 (b/(app+'.service')).write_text(units[app]);(b/(app+'-new.service')).write_text(units[app].replace(str(r/'releases'/old),str(r/'releases'/new)))
try:
 for app in versions:
  run('sudo','-n','systemctl','stop','bug-finding-'+app)
  with sqlite3.connect('file:'+str(r/(app+'-state')/(app+'.sqlite3'))+'?mode=ro',uri=True) as src,sqlite3.connect(b/(app+'.sqlite3')) as dst:src.backup(dst)
  run('sudo','-n','cp',str(b/(app+'-new.service')),'/etc/systemd/system/bug-finding-'+app+'.service')
 config_path.write_text(json.dumps(new_config))
 run('sudo','-n','systemctl','daemon-reload')
 for app,port in [('evaluation',8103),('exploration',8102)]:
  run('sudo','-n','systemctl','start','bug-finding-'+app)
  for _ in range(30):
   try:
    assert json.load(urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=2))['ok'];break
   except Exception:time.sleep(1)
  else:raise RuntimeError('health failed')
 after=fingerprint();after['files'][str(config_path)]=before['files'][str(config_path)];assert after==before
 print('Guided exploration deployed: 233 eligible bug tasks; legacy services unchanged')
except Exception:
 config_path.write_text(original_config)
 for app in versions:run('sudo','-n','cp',str(b/(app+'.service')),'/etc/systemd/system/bug-finding-'+app+'.service')
 run('sudo','-n','systemctl','daemon-reload')
 for app in versions:run('sudo','-n','systemctl','restart','bug-finding-'+app)
 raise
