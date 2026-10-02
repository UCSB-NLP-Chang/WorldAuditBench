#!/usr/bin/env python3
"""Publish the verified ancient addition without changing previous review data."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import sqlite3
import subprocess
import time
import urllib.request
import os

ROOT = Path('/home/ubuntu/unreal-auditor/review-service')
STATE = ROOT / 'state'
RELEASE_NAME = json.loads(Path(os.getenv('ANCIENT_ACCEPTANCE_FILE','/home/ubuntu/unreal-auditor/ancient-workspace/out/era-v1/acceptance.json')).read_text())['release_name']
STAGE = ROOT / 'staging' / RELEASE_NAME
RELEASE = ROOT / 'releases' / RELEASE_NAME
DROP_ROOT = Path('/etc/systemd/system/urban-review-pilot.service.d')
Z_COUNT = max((len(p.name)-len(p.name.lstrip('z')) for p in DROP_ROOT.glob('*.conf')),default=0)+1
DROP = DROP_ROOT / ('z'*Z_COUNT+'-ancient.conf')


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def database():
    return sqlite3.connect('file:' + str(STATE / 'review.sqlite3') + '?mode=ro', uri=True)


def idle(db):
    return db.execute("SELECT COUNT(*) FROM sessions WHERE status IN ('queued','starting','ready','resetting','switching','closing')").fetchone()[0] == 0


def protected(db):
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {name: hashlib.sha256(json.dumps(db.execute('SELECT * FROM ' + name + ' ORDER BY rowid').fetchall(), ensure_ascii=False).encode()).hexdigest()
            for name in ('feedback', 'review_history', 'evidence', 'participants') if name in tables}


def main():
    proof = json.loads((STAGE / 'ancient-provenance.json').read_text())
    acceptance = json.loads((STAGE / 'ancient-validation.json').read_text())
    assert acceptance['result'] == 'PASS'
    assert proof['acceptance']['result'] == 'PASS', 'A draft or visually unverified package cannot be published.'
    # A content-only cook can leave the executable unchanged; verify its packages too.
    from prepare_review import digest
    work = ROOT.parent / 'ancient-workspace'
    for relative, sha in proof['acceptance'].get('artifact_sha256', {}).items():
        path = work / relative
        assert path.resolve().is_relative_to(work.resolve())
        assert digest(path) == sha, (relative, 'verified artifact changed')
    source = run('systemctl', 'show', 'urban-review-pilot.service', '-p', 'WorkingDirectory', '--value').stdout.strip()
    assert source == proof['source_release'], 'Live release changed; rebase the candidate first.'
    for name, sha in proof['source_files_sha256'].items():
        assert hashlib.sha256((Path(source) / name).read_bytes()).hexdigest() == sha, (name, 'live source changed')
    for name, sha in proof['source_state_sha256'].items():
        assert hashlib.sha256((STATE / name).read_bytes()).hexdigest() == sha, (name, 'changed')
    manifest = json.loads((STAGE / 'tasks.json').read_text())
    config = json.loads((STAGE / 'candidate-runtime.json').read_text())
    previous = json.loads((STATE / 'tasks.json').read_text())
    previous_config = json.loads((STATE / 'runtime.json').read_text())
    assert [task for task in manifest['tasks'] if task.get('family') != 'ancient'] == [task for task in previous['tasks'] if task.get('family') != 'ancient']
    assert {key: value for key, value in config.items() if key != 'launch_profiles'} == {key: value for key, value in previous_config.items() if key != 'launch_profiles'}
    assert all(config['launch_profiles'][key] == value for key, value in previous_config['launch_profiles'].items() if value.get('family') != 'ancient')
    assert not RELEASE.exists() and not DROP.exists()
    with database() as db:
        if not idle(db):
            raise SystemExit('Active reviewers: candidate is ready; publish when all sessions finish.')
        fingerprints = protected(db)
        backup = ROOT / 'backups' / ('ancient-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(mode=0o700)
        with sqlite3.connect(backup / 'review.sqlite3') as destination:
            db.backup(destination)
    for name in ('tasks.json', 'runtime.json', 'service-env.json', 'participants.json'):
        shutil.copy2(STATE / name, backup / name)
    env = json.loads((STATE / 'service-env.json').read_text())
    if 'REVIEW_RUNNER_JSON' in env:
        env['REVIEW_RUNNER_JSON'] = json.dumps([str(RELEASE / 'runtime/mac_runner.py') if value.endswith('/runtime/mac_runner.py') else value
                                              for value in json.loads(env['REVIEW_RUNNER_JSON'])])
    unit = backup / DROP.name
    unit.write_text('[Service]\nWorkingDirectory=' + str(RELEASE) + '\nExecStart=\nExecStart=/usr/bin/python3 ' + str(RELEASE / 'runtime/start_linux.py') + ' ' + str(STATE) + '\n')
    with database() as db:
        assert idle(db), 'A reviewer started; leave the running service intact.'
    run('sudo', 'systemctl', 'stop', 'urban-review-pilot.service')
    try:
        shutil.copytree(STAGE, RELEASE, ignore=shutil.ignore_patterns('__pycache__', 'candidate-runtime.json'))
        for name, value in [('tasks.json', manifest), ('runtime.json', config), ('service-env.json', env)]:
            temporary = STATE / (name + '.ancient-new')
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)); temporary.chmod(0o600)
            temporary.replace(STATE / name)
        run('sudo', 'cp', str(unit), str(DROP))
        run('sudo', 'systemctl', 'daemon-reload')
        run('sudo', 'systemctl', 'start', 'urban-review-pilot.service')
        for attempt in range(30):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8092/health', timeout=2) as response:
                    health = json.load(response)
                break
            except Exception:
                if attempt == 29:
                    raise
                time.sleep(1)
        with database() as db:
            assert protected(db) == fingerprints
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        report = dict(result='PASS', release=str(RELEASE), backup=str(backup), health=health,
                      ancient_bugs=sum(t.get('family')=='ancient' and t.get('case_type')=='bug' for t in manifest['tasks']), ancient_baselines=3, previous_records_preserved=True,
                      binary_sha256=proof['binary_sha256'])
        (STAGE / 'deployment-report.json').write_text(json.dumps(report, indent=2))
        (ROOT / 'current-release.txt').write_text(str(RELEASE) + '\n')
        print(json.dumps(report))
    except Exception:
        run('sudo', 'systemctl', 'stop', 'urban-review-pilot.service')
        for name in ('tasks.json', 'runtime.json', 'service-env.json'):
            shutil.copy2(backup / name, STATE / name)
        if DROP.exists():
            run('sudo', 'unlink', str(DROP))
        run('sudo', 'systemctl', 'daemon-reload')
        run('sudo', 'systemctl', 'start', 'urban-review-pilot.service')
        raise


if __name__ == '__main__':
    main()
