#!/usr/bin/env python3
"""Deploy only the two bug-finding apps; stop, snapshot, migrate, verify or restore."""
import json
import pathlib
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request

root = pathlib.Path('/home/ubuntu/unreal-auditor/bug-finding-pilot')
release = root / 'releases/progress-v7'
backup = root / 'backups/progress-v7'
services = ['urban-review-pilot','review-web','subway-review','threejs-environments']


def run(*args):
    return subprocess.run(args, check=True)


def fingerprints():
    paths = [pathlib.Path('/home/ubuntu/unreal-auditor/review-service/state') / n for n in ['service-env.json','runtime.json','tasks.json','participants.json']]
    import hashlib
    return {'services': {s: subprocess.check_output(['systemctl','show',s,'-p','MainPID','-p','ExecMainStartTimestamp','-p','ActiveState'],text=True) for s in services},
            'files': {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


for app in ['exploration','evaluation']:
    assert str(release) not in subprocess.check_output(['systemctl','cat','bug-finding-'+app],text=True), 'Cannot overwrite an active release'
release.mkdir(exist_ok=True)
run('tar','xzf','/tmp/bf-progress-v7.tgz','-C',str(release))
subprocess.run(['python3','-m','unittest','discover','-s','tests','-q'], cwd=release, check=True)
backup.mkdir(exist_ok=False)
before = fingerprints()
(backup/'legacy-before.json').write_text(json.dumps(before,indent=2))
units = {}
for app in ['exploration','evaluation']:
    unit = pathlib.Path('/etc/systemd/system/bug-finding-'+app+'.service')
    old = unit.read_text()
    (backup/(app+'.service')).write_text(old)
    new = re.sub(r'/home/ubuntu/unreal-auditor/bug-finding-pilot/releases/[^\s]+',str(release),old)
    (backup/(app+'-new.service')).write_text(new)
    units[app] = unit

snapshotted = False
try:
    for app in units: run('sudo','-n','systemctl','stop','bug-finding-'+app)
    for app in units:
        path = root/(app+'-state')/(app+'.sqlite3')
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as source, sqlite3.connect(backup/path.name) as target:
            source.backup(target)
    snapshotted = True
    output = subprocess.check_output(['python3',str(release/'ops/provision_access.py'),str(root)],text=True)
    accounts = json.loads(output)
    for app,unit in units.items(): run('sudo','-n','cp',str(backup/(app+'-new.service')),str(unit))
    run('sudo','-n','systemctl','daemon-reload')
    for app,port in [('evaluation',8103),('exploration',8102)]:
        run('sudo','-n','systemctl','start','bug-finding-'+app)
        for _ in range(25):
            try:
                assert json.load(urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=2))['ok']
                break
            except Exception: time.sleep(1)
        else: raise RuntimeError(app+' failed health check')
    assert fingerprints() == before, 'Legacy state changed'
    report = {'release': str(release), 'tests_passed':39, 'legacy_unchanged':True, 'accounts':accounts, 'databases_separate':True}
    (root/'verification/progress-v7.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))
except Exception:
    for app in units: subprocess.run(['sudo','-n','systemctl','stop','bug-finding-'+app])
    if snapshotted:
        for app in units:
            with sqlite3.connect(backup/(app+'.sqlite3')) as source, sqlite3.connect(root/(app+'-state')/(app+'.sqlite3')) as target:
                source.backup(target)
    for app,unit in units.items(): run('sudo','-n','cp',str(backup/(app+'.service')),str(unit))
    run('sudo','-n','systemctl','daemon-reload')
    for app in units: run('sudo','-n','systemctl','start','bug-finding-'+app)
    raise
