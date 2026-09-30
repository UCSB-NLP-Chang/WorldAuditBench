#!/usr/bin/env python3
"""Activate a staged all-task import; rollback new apps only on any failure."""
import hashlib
import json
import pathlib
import shutil
import sqlite3
import subprocess as sp
import time
import urllib.request

root=pathlib.Path('/home/ubuntu/unreal-auditor/bug-finding-pilot')
release=root/'releases/all-tasks-v9';stage=root/'imports/all-tasks-v9';backup=root/'backups/all-tasks-v9'
audit=pathlib.Path('/home/ubuntu/unreal-auditor/review-service/state')
apps=['exploration','evaluation']
def run(*args):sp.run(args,check=True)
def fingerprints():
    return {'services':{s:sp.check_output(['systemctl','show',s,'-p','MainPID','-p','ActiveState','-p','ExecMainStartTimestamp'],text=True) for s in ['urban-review-pilot','review-web','subway-review','threejs-environments']},'files':{n:hashlib.sha256((audit/n).read_bytes()).hexdigest() for n in ['tasks.json','runtime.json','service-env.json','participants.json']}}
cat=json.loads((stage/'catalog.json').read_text());before=fingerprints()
assert before['files']['tasks.json']==cat['source_sha256']
sp.run(['python3','-m','unittest','discover','-s','tests','-q'],cwd=release,check=True)
# Verify each distinct binary against the imported launch profile before touching services.
runtime=json.loads((stage/'config/runtime.json').read_text());verified={}
for profile in runtime['launch_profiles'].values():
    binary=profile['binary']
    if binary not in verified:
        h=hashlib.sha256()
        with open(binary,'rb') as f:
            for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
        verified[binary]=h.hexdigest()
    assert verified[binary]==profile['build_sha256']
backup.mkdir(exist_ok=False);shutil.copytree(root/'config',backup/'config')
(backup/'legacy-before.json').write_text(json.dumps(before))
units={}
for app in apps:
    p=pathlib.Path('/etc/systemd/system/bug-finding-'+app+'.service');units[app]=p.read_text()
    (backup/(app+'.service')).write_text(units[app])
    old=str(root/'releases/audit-ui-v8');assert old in units[app]
    new=units[app].replace(old,str(release))
    # Preparation artifacts include private references; only browser-assets is exposed.
    new=new.replace('InaccessiblePaths=', 'InaccessiblePaths='+str(stage/'config')+' '+str(stage/'catalog.json')+' ')
    (backup/(app+'-new.service')).write_text(new)
ready=False
try:
    for app in apps:run('sudo','-n','systemctl','stop','bug-finding-'+app)
    for app in apps:
        with sqlite3.connect('file:'+str(root/(app+'-state')/(app+'.sqlite3'))+'?mode=ro',uri=True) as source,sqlite3.connect(backup/(app+'.sqlite3')) as dest:source.backup(dest)
    ready=True
    run('python3',str(release/'ops/import_audit_tasks.py'),'apply','--root',str(root),'--stage',str(stage))
    for p in (stage/'config').glob('*.json'):shutil.copy2(p,root/'config'/p.name)
    for app in apps:run('sudo','-n','cp',str(backup/(app+'-new.service')),'/etc/systemd/system/bug-finding-'+app+'.service')
    run('sudo','-n','systemctl','daemon-reload')
    for app,port in [('evaluation',8103),('exploration',8102)]:
        run('sudo','-n','systemctl','start','bug-finding-'+app)
        for _ in range(30):
            try:
                assert json.load(urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=2))['ok'];break
            except Exception:time.sleep(1)
        else:raise RuntimeError('Health check failed: '+app)
    for app in apps:
        db=sqlite3.connect(root/(app+'-state')/(app+'.sqlite3'))
        prior=sqlite3.connect(backup/(app+'.sqlite3'))
        assert db.execute('SELECT id,payload FROM submissions ORDER BY id').fetchall()==prior.execute('SELECT id,payload FROM submissions ORDER BY id').fetchall()
        counts=db.execute('SELECT lower(u.name),a.role,count(*) FROM task_access a JOIN users u ON u.id=a.user_id GROUP BY 1,2').fetchall()
        assert len(counts)==15 and all(n==cat['total'] for _,_,n in counts),counts
        prior.close();db.close()
    assert fingerprints()==before
    report={'tasks':cat['total'],'unreal':cat['unreal'],'browser':cat['browser'],'verified_binaries':len(verified),'legacy_unchanged':True,'submissions_preserved':True,'accounts_assigned':15,'tests':43}
    (root/'verification/all-tasks-v9.json').write_text(json.dumps(report));print(json.dumps(report))
except Exception:
    for app in apps:sp.run(['sudo','-n','systemctl','stop','bug-finding-'+app])
    if ready:
        for app in apps:
            with sqlite3.connect(backup/(app+'.sqlite3')) as src,sqlite3.connect(root/(app+'-state')/(app+'.sqlite3')) as dst:src.backup(dst)
    for p in (backup/'config').glob('*.json'):shutil.copy2(p,root/'config'/p.name)
    for app in apps:run('sudo','-n','cp',str(backup/(app+'.service')),'/etc/systemd/system/bug-finding-'+app+'.service')
    run('sudo','-n','systemctl','daemon-reload')
    for app in apps:run('sudo','-n','systemctl','start','bug-finding-'+app)
    raise
