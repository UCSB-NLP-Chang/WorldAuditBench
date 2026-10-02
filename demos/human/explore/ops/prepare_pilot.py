#!/usr/bin/env python3
"""Run on unreal. Import one existing review case WITHOUT changing its deployment."""
import argparse
import hashlib
import json
import os
import pathlib
import secrets
import socket
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bf.common import canonical, digest, uid
from bf.exploration import ExplorationStore
from bf.evaluation import EvaluationStore


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, str) else value)
    path.chmod(0o600)


def fingerprint(old):
    services = {}
    for service in ('urban-review-pilot', 'review-web', 'subway-review', 'threejs-environments'):
        result = subprocess.check_output(['systemctl', 'show', service, '-p', 'MainPID', '-p', 'ActiveState', '-p', 'ExecMainStartTimestamp'], text=True)
        services[service] = dict(line.split('=', 1) for line in result.splitlines() if '=' in line)
    paths = [old / 'state' / name for name in ('runtime.json', 'service-env.json', 'tasks.json')]
    paths += [pathlib.Path('/etc/systemd/system/urban-review-pilot.service')]
    return {'services': services, 'files': {str(p): digest(p.read_bytes()) for p in paths}, 'health': json.load(urllib.request.urlopen('http://127.0.0.1:8092/health')), 'db_inode': (old / 'state/review.sqlite3').stat().st_ino}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--review-root', default='/home/ubuntu/unreal-auditor/review-service')
    parser.add_argument('--case', default='S01')
    args = parser.parse_args()
    os.umask(0o077)
    root, old = pathlib.Path(args.root), pathlib.Path(args.review_root)
    if (root / 'config/exploration.json').exists():
        raise SystemExit('Pilot is already configured; use an explicit migration instead of overwriting data.')
    root.mkdir(parents=True, exist_ok=True)
    write(root / 'verification/legacy-before.json', fingerprint(old))
    (root / 'backups').mkdir(exist_ok=True)
    ports = [8102, 8103, 19092, 18182, 18982, 19992]
    for port in ports:
        with socket.socket() as sock:
            sock.bind(('0.0.0.0', port))
    old_runtime = json.loads((old / 'state/runtime.json').read_text())
    source_manifest = json.loads((old / 'state/tasks.json').read_text())
    source = next(t for t in source_manifest['tasks'] if t['id'] == args.case)
    assert source.get('runtime_kind') != 'browser', 'Pilot adapter currently supports Unreal environments'
    profile = json.loads(json.dumps(old_runtime['launch_profiles'][source['map']]))
    assert pathlib.Path(profile['binary']).is_file()
    assert source['build_sha256'] == profile['build_sha256']
    query = '自由探索这个环境，寻找你认为不符合正常行为或外观的异常。使用 Flag 保存证据截图，并描述你发现的问题；如果没有发现异常，也请如实提交。'
    rubric = source.get('rubrics') or canonical(source['rubrics_i18n'])
    # Deterministic immutable version identifies query + exact source + rubric.
    version = digest(canonical({'case': source['id'], 'revision': source['revision'], 'map_sha256': source['sha256'], 'build_sha256': source['build_sha256'], 'rubric': rubric, 'query': query}).encode())[:32]
    task = {'id': version, 'title': source['environment'].split('/')[0].strip() + ' · 自由探索', 'query': query, 'controls': 'W / A / S / D 移动 · E 交互 · 鼠标观察 · F 截图 · Esc 释放鼠标。可从多个角度探索；截图和描述会自动保存。'}
    reference = {'id': version, 'query': query, 'case_id': source['id'], 'case_revision': source['revision'], 'map_sha256': source['sha256'], 'build_sha256': source['build_sha256'], 'rubric': rubric, 'rubric_sha256': digest(rubric.encode())}
    explore_host, evaluate_host = 'explore.150-230-45-149.sslip.io', 'evaluate.150-230-45-149.sslip.io'
    transfer_secret, supervisor_secret = (secrets.token_urlsafe(32) for _ in range(2))
    runtime_root = root / 'runtime-state'
    runtime_root.mkdir(exist_ok=True)
    # Preserve the audited launch profile, including frame rate and bitrate.
    profile['key_filter'] = profile.get('key_filter', '') + ',F'
    manifest = {'tasks': [{k: source[k] for k in ('id', 'map', 'build_sha256')} ]}
    write(root / 'config/runtime-manifest.json', manifest)
    c = {k: old_runtime[k] for k in ('signal_argv', 'signal_cwd', 'probe_argv', 'http_root')}
    c.update({'manifest': str(root / 'config/runtime-manifest.json'), 'state_dir': str(runtime_root / 'sessions'), 'supervisor_port': 19092, 'streamer_port': 18982, 'player_port': 18182, 'sfu_port': 19992, 'capacity': 1, 'secret': supervisor_secret, 'launch_profiles': {source['map']: profile}, 'game_env': {**old_runtime.get('game_env', {}), 'XDG_CACHE_HOME': str(runtime_root / 'cache')}})
    # Existing publicly reachable TURN is a transport dependency, not a database or slot owner.
    # Reusing it needs no firewall / relay configuration changes and no legacy restart.
    c['peer_options'] = old_runtime['peer_options']
    c['turn_argv'] = []
    write(root / 'config/runtime.json', c)
    exconfig = {'port': 8102, 'origin': 'https://' + explore_host, 'state_dir': str(root / 'exploration-state'), 'task_id': version, 'task': task, 'evaluation_internal': 'http://127.0.0.1:8103', 'transfer_secret': transfer_secret, 'supervisor_config': str(root / 'config/runtime.json'), 'runtime': {'supervisor_url': 'http://127.0.0.1:19092', 'supervisor_secret': supervisor_secret, 'player_port': 18182, 'legacy_player_ports': list(range(old_runtime['player_port'], old_runtime['player_port'] + old_runtime['capacity'])), 'gpu_guard': True, 'tasks': {version: {'map': source['map']}}}}
    evconfig = {'port': 8103, 'origin': 'https://' + evaluate_host, 'state_dir': str(root / 'evaluation-state'), 'exploration_internal': 'http://127.0.0.1:8102', 'transfer_secret': transfer_secret, 'references': [reference]}
    write(root / 'config/exploration.json', exconfig)
    write(root / 'config/evaluation.json', evconfig)
    ex, ev = ExplorationStore(exconfig['state_dir']), EvaluationStore(evconfig['state_dir'])
    ex.register_task(task)
    ev.register_reference(reference)
    accounts = {}
    for store, role in ((ex, 'explorer'), (ev, 'evaluator')):
        for name in (role, 'qa-' + role):
            password = secrets.token_urlsafe(15)
            store.add_user(name, password, is_test=name.startswith('qa-'))
            accounts[name] = password
    write(root / 'config/acceptance-accounts.json', accounts)
    write(root / 'verification/source-import.json', {'case': source['id'], 'revision': source['revision'], 'task_version_id': version, 'binary': profile['binary'], 'build_sha256': source['build_sha256'], 'source_manifest_sha256': digest((old / 'state/tasks.json').read_bytes()), 'source_runtime_sha256': digest((old / 'state/runtime.json').read_bytes())})
    for app in ('exploration', 'evaluation'):
        writable = [root / (app + '-state')]
        if app == 'exploration':
            writable.append(runtime_root)
        unit = f'''[Unit]
Description=Bug finding {app} single-case pilot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory={ROOT}
ExecStart=/usr/bin/python3 -m bf.main {app} {root}/config/{app}.json
Restart=on-failure
RestartSec=5
KillMode=control-group
TimeoutStopSec=25
UMask=0077
Nice=0
CPUQuota=infinity
MemoryMax=8G
TasksMax=2048
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths={' '.join(map(str,writable))}
PrivateTmp=true
Environment=PYTHONDONTWRITEBYTECODE=1

[Install]
WantedBy=multi-user.target
'''
        # Evaluation cannot read exploration state; exploration cannot read private rubric.
        inaccessible = [root / ('evaluation-state' if app == 'exploration' else 'exploration-state'), root / 'config' / ('evaluation.json' if app == 'exploration' else 'exploration.json'), root / 'config/acceptance-accounts.json', root / 'backups', root / 'verification', old / 'state', old / 'releases']
        unit = unit.replace('PrivateTmp=true', 'PrivateTmp=true\nInaccessiblePaths=' + ' '.join(map(str, inaccessible)))
        write(root / 'units' / ('bug-finding-' + app + '.service'), unit)
    print(json.dumps({'case': args.case, 'task_version': version, 'root': str(root), 'origins': [exconfig['origin'], evconfig['origin']]}))


if __name__ == '__main__':
    main()
