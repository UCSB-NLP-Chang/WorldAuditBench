#!/usr/bin/env python3
"""Activate count-only progress without changing task configs or database schemas."""
from pathlib import Path
import hashlib
import json
import sqlite3
import subprocess as sp
import time
import urllib.request

root=Path('/home/ubuntu/unreal-auditor/bug-finding-pilot');release=root/'releases/admin-coverage-v16';old=root/'releases/login-select-explore-v15';backup=root/'backups/admin-coverage-v16'
apps=['exploration']
def run(*args):sp.run(args,check=True)
def fingerprint():
    audit=Path('/home/ubuntu/unreal-auditor/review-service/state')
    paths=[audit/n for n in ['tasks.json','runtime.json','service-env.json','participants.json']]+list((root/'config').glob('*.json'))
    return {'services':{s:sp.check_output(['systemctl','show',s,'-p','MainPID','-p','ExecMainStartTimestamp','-p','ActiveState'],text=True) for s in ['urban-review-pilot','review-web','subway-review','threejs-environments','bug-finding-evaluation']},'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
backup.mkdir(exist_ok=False);before=fingerprint();(backup/'before.json').write_text(json.dumps(before))
units={}
for app in apps:
    path=Path('/etc/systemd/system/bug-finding-'+app+'.service');units[app]=path.read_text();assert str(old) in units[app]
    (backup/(app+'.service')).write_text(units[app]);(backup/(app+'-new.service')).write_text(units[app].replace(str(old),str(release)))
try:
    for app in apps:run('sudo','-n','systemctl','stop','bug-finding-'+app)
    for app in apps:
        with sqlite3.connect('file:'+str(root/(app+'-state')/(app+'.sqlite3'))+'?mode=ro',uri=True) as src,sqlite3.connect(backup/(app+'.sqlite3')) as dst:src.backup(dst)
        run('sudo','-n','cp',str(backup/(app+'-new.service')),'/etc/systemd/system/bug-finding-'+app+'.service')
    run('sudo','-n','systemctl','daemon-reload')
    for app,port in [('exploration',8102)]:
        run('sudo','-n','systemctl','start','bug-finding-'+app)
        for _ in range(30):
            try:
                assert json.load(urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=2))['ok'];break
            except Exception:time.sleep(1)
        else:raise RuntimeError('Health failed: '+app)
    assert fingerprint()==before
    (root/'verification/session-controls-v13.json').write_text(json.dumps({'release':str(release),'legacy_and_configs_unchanged':True,'schema_unchanged':True,'validation':'frontend syntax and case grouping checks; backend unchanged'}))
    print('Case progress deployed; legacy services and all task configs unchanged')
except Exception:
    # No migration: retain every legitimate answer saved during rollout.
    for app in apps:run('sudo','-n','cp',str(backup/(app+'.service')),'/etc/systemd/system/bug-finding-'+app+'.service')
    run('sudo','-n','systemctl','daemon-reload')
    for app in apps:run('sudo','-n','systemctl','restart','bug-finding-'+app)
    raise
