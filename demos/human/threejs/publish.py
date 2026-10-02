#!/usr/bin/env python3
"""Publish the envs-2026-09-16c three.js release (clean review view) to the live review site.  Two phases, both guarded and reversible:

  1. static site: point threejs-environments.service at this release directory (unit file rewritten, daemon-reload,
     restart, /health check).  The Caddy route (/threejs/ -> 127.0.0.1:8094) is unchanged.  Previous release kept on disk.
  2. review manifest: copy the live coordinator release to a new release directory carrying staging/tasks.json, swap
     review-service/state/tasks.json, add the systemd drop-in and restart urban-review-pilot.service - only while no
     review session is active; SQLite backed up with the backup API first; protected tables verified unchanged after;
     full rollback on any failure.  (Same procedure as the Unreal families' publish scripts.)

usage: publish.py [--site-only | --manifest-only]
"""
import datetime, hashlib, json, pathlib, shutil, sqlite3, subprocess, sys, time, urllib.request

ROOT = pathlib.Path('/home/ubuntu/unreal-auditor')
RELEASE = pathlib.Path(__file__).resolve().parent
SERVICE = ROOT / 'review-service'
STATE = SERVICE / 'state'
STAGED = RELEASE / 'staging/tasks.json'
NEW_REVIEW_RELEASE = SERVICE / 'releases' / 'threejs-envs-20260916-v3'


def run(*args): return subprocess.run(args, check=True, capture_output=True, text=True)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dbopen(): return sqlite3.connect('file:' + str(STATE / 'review.sqlite3') + '?mode=ro', uri=True)
def idle(db): return db.execute("select count(*) from sessions where status in ('queued','starting','ready','resetting','switching','closing')").fetchone()[0] == 0
def protected(db):
    tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    return {n: hashlib.sha256(json.dumps(db.execute('select * from ' + n + ' order by rowid').fetchall(), ensure_ascii=False).encode()).hexdigest()
            for n in ['feedback', 'review_history', 'evidence', 'logins', 'events', 'participants'] if n in tables}
def live_release(): return pathlib.Path(run('systemctl', 'show', 'urban-review-pilot.service', '-p', 'WorkingDirectory', '--value').stdout.strip())
def health(url, tries=30):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=2) as f:
                f.read(); return True
        except Exception:
            time.sleep(1)
    raise SystemExit('health check failed: ' + url)


def publish_site():
    for line in (RELEASE / 'site/SHA256SUMS').read_text().splitlines():
        digest, name = line.split()
        assert sha(RELEASE / 'site' / name) == digest, name
    unit = f'''[Unit]
Description=Three.js environment files with review login
After=network.target urban-review-pilot.service
[Service]
User=ubuntu
Group=ubuntu
UMask=0077
WorkingDirectory={RELEASE}
ExecStart=/usr/bin/python3 {RELEASE}/serve.py {RELEASE}/site
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
[Install]
WantedBy=multi-user.target
'''
    (RELEASE / 'threejs-environments.service').write_text(unit)
    prev = pathlib.Path('/etc/systemd/system/threejs-environments.service').read_text()
    (RELEASE / 'threejs-environments.service.previous').write_text(prev)
    run('sudo', 'install', '-m', '644', str(RELEASE / 'threejs-environments.service'), '/etc/systemd/system/threejs-environments.service')
    run('sudo', 'systemctl', 'daemon-reload')
    run('sudo', 'systemctl', 'restart', 'threejs-environments.service')
    health('http://127.0.0.1:8094/health')
    served = run('systemctl', 'show', 'threejs-environments.service', '-p', 'ExecStart', '--value').stdout
    assert str(RELEASE / 'site') in served, served
    print('SITE_PUBLISHED', RELEASE / 'site')


def publish_manifest():
    report = json.loads((RELEASE / 'staging/manifest-report.json').read_text())
    source = live_release()
    assert str(source) == report['live_release'], f'live release changed since staging ({source} vs {report["live_release"]}); re-run prepare_manifest.py'
    assert sha(STATE / 'tasks.json') == report['live_tasks_sha256'], 'live tasks.json changed since staging; re-run prepare_manifest.py'
    manifest = json.loads(STAGED.read_text()); assert len(manifest['tasks']) == report['entries_after']
    assert not NEW_REVIEW_RELEASE.exists(), NEW_REVIEW_RELEASE
    db = dbopen()
    if not idle(db): raise SystemExit('WAIT_ACTIVE_REVIEWERS: a review session is active; publish the manifest later')
    before = protected(db)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    backup = SERVICE / 'backups' / ('threejs-envs-20260916v3-' + stamp); backup.mkdir(mode=0o700)
    with sqlite3.connect(backup / 'review.sqlite3') as dest: db.backup(dest)
    db.close()
    for n in ('tasks.json', 'runtime.json', 'service-env.json', 'participants.json'): shutil.copy2(STATE / n, backup / n)
    shutil.copytree(source, NEW_REVIEW_RELEASE, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(STAGED, NEW_REVIEW_RELEASE / 'tasks.json')
    (NEW_REVIEW_RELEASE / 'threejs-deployment.json').write_text(json.dumps({'three_js_release': str(RELEASE), 'source_release': str(source), 'backup': str(backup), 'report': report}, ensure_ascii=False, indent=2) + '\n')
    env = json.loads((STATE / 'service-env.json').read_text())
    if 'REVIEW_RUNNER_JSON' in env:
        env['REVIEW_RUNNER_JSON'] = json.dumps([str(NEW_REVIEW_RELEASE / 'runtime/mac_runner.py') if str(v).endswith('/runtime/mac_runner.py') else v for v in json.loads(env['REVIEW_RUNNER_JSON'])])
    dropdir = pathlib.Path('/etc/systemd/system/urban-review-pilot.service.d')
    maxz = max(len(x.name) - len(x.name.lstrip('z')) for x in dropdir.iterdir())
    drop = dropdir / (('z' * (maxz + 1)) + '-threejs-envs-20260916-v3.conf'); assert not drop.exists()
    unit = backup / drop.name
    unit.write_text('[Service]\nWorkingDirectory=' + str(NEW_REVIEW_RELEASE) + '\nExecStart=\nExecStart=/usr/bin/python3 ' + str(NEW_REVIEW_RELEASE / 'runtime/start_linux.py') + ' ' + str(STATE) + '\n')
    db = dbopen(); assert idle(db), 'reviewer arrived'; assert protected(db) == before; db.close()
    run('sudo', 'systemctl', 'stop', 'urban-review-pilot.service')
    try:
        db = dbopen(); assert idle(db), 'reviewer arrived during stop'; db.close()
        for n, data in [('tasks.json', manifest), ('service-env.json', env)]:
            tmp = STATE / (n + '.threejs-new'); tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n'); tmp.chmod(0o600); tmp.replace(STATE / n)
        run('sudo', 'cp', str(unit), str(drop)); run('sudo', 'systemctl', 'daemon-reload'); run('sudo', 'systemctl', 'start', 'urban-review-pilot.service')
        health('http://127.0.0.1:8092/health')
        assert live_release() == NEW_REVIEW_RELEASE
        db = dbopen(); assert protected(db) == before; assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'; db.close()
        out = {'result': 'PASS', 'release': str(NEW_REVIEW_RELEASE), 'backup': str(backup), 'entries': len(manifest['tasks']), 'protected_tables': list(before)}
        (RELEASE / 'deployment-report.json').write_text(json.dumps(out, indent=2) + '\n'); print('MANIFEST_PUBLISHED', json.dumps(out))
    except Exception:
        run('sudo', 'systemctl', 'stop', 'urban-review-pilot.service')
        for n in ('tasks.json', 'service-env.json'): shutil.copy2(backup / n, STATE / n)
        if drop.exists(): run('sudo', 'rm', str(drop))
        run('sudo', 'systemctl', 'daemon-reload'); run('sudo', 'systemctl', 'start', 'urban-review-pilot.service')
        raise


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'both'
    if mode in ('both', '--site-only'): publish_site()
    if mode in ('both', '--manifest-only'): publish_manifest()
