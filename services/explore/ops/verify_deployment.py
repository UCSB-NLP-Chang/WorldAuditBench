#!/usr/bin/env python3
"""Read-only postflight, apart from normal login sessions and a verification report."""
import hashlib
import http.cookiejar
import json
import pathlib
import subprocess
import sys
import urllib.request

from prepare_pilot import fingerprint, write

root = pathlib.Path(sys.argv[1])
old = pathlib.Path('/home/ubuntu/unreal-auditor/review-service')
before = json.loads((root / 'verification/legacy-before.json').read_text())
after = fingerprint(old)
assert before == after, 'Legacy fingerprint differs; inspect before claiming no impact'
accounts = json.loads((root / 'config/acceptance-accounts.json').read_text())


def session(app, name):
    config = json.loads((root / 'config' / (app + '.json')).read_text())
    base = 'http://127.0.0.1:' + str(config['port'])
    opener = urllib.request.build_opener()
    request = urllib.request.Request(base + '/api/login', data=json.dumps({'name': name, 'password': accounts[name]}).encode(), headers={'Origin': config['origin'], 'Content-Type': 'application/json'})
    with opener.open(request) as response:
        cookie = response.headers['Set-Cookie'].split(';', 1)[0]
    def get(path):
        return json.load(opener.open(urllib.request.Request(base + path, headers={'Cookie': cookie})))
    return get


explore = session('exploration', 'testuser')
evaluate = session('evaluation', 'testuser')
qa_evaluate = session('evaluation', 'qa-evaluator')
workspace = explore('/api/workspace')
normal_queue = evaluate('/api/queue')['items']
qa_queue = qa_evaluate('/api/queue')['items']
assert workspace['attempt'] is None, 'Acceptance explorer already has an attempt'
assert normal_queue == [], 'Acceptance queue must not contain QA answers'
assert any(item['state'] == 'complete' for item in qa_queue), 'No completed QA judgment'
assert 'rubric' not in json.dumps(workspace).lower()
dbs = [root / app / name for app, name in [('exploration-state', 'exploration.sqlite3'), ('evaluation-state', 'evaluation.sqlite3')]]
assert dbs[0].stat().st_ino != dbs[1].stat().st_ino
isolation = {}
for app in ('exploration', 'evaluation'):
    pid = subprocess.check_output(['systemctl', 'show', 'bug-finding-' + app, '-p', 'MainPID', '--value'], text=True).strip()
    other = 'evaluation' if app == 'exploration' else 'exploration'
    paths = [str(root / (other + '-state') / (other + '.sqlite3')), str(root / 'config' / (other + '.json')), str(old / 'state/tasks.json'), str(root / 'backups'), str(root / 'verification')]
    code = 'import os,json,sys; print(json.dumps({p:os.access(p,os.R_OK) for p in json.loads(sys.argv[1])}))'
    result = subprocess.check_output(['sudo', '-n', 'nsenter', '--target', pid, '--mount', '--', 'runuser', '-u', 'ubuntu', '--', 'python3', '-c', code, json.dumps(paths)], text=True)
    access = json.loads(result)
    assert not any(access.values()), (app, access)
    isolation[app] = {'other_database_readable': False, 'private_config_readable': False, 'old_review_manifest_readable': False, 'backups_readable': False}
health = {app: json.load(urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/health')) for app, port in [('exploration', 8102), ('evaluation', 8103)]}
report = {'legacy_unchanged': True, 'legacy': after, 'separate_databases': True, 'filesystem_isolation': isolation, 'acceptance_workspace_empty': True, 'acceptance_queue_empty': True, 'qa_completed_answers': sum(i['state'] == 'complete' for i in qa_queue), 'health': health}
write(root / 'verification/final.json', report)
print(json.dumps(report, ensure_ascii=False))
