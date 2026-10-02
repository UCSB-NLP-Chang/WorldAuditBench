"""Publish prepared Review configs at idle, with rollback and protected-service checks."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import time
import urllib.request


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(source, target):
    temp = target.with_name(target.name + '.activation-tmp')
    shutil.copyfile(source, temp)
    temp.chmod(0o600)
    temp.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--completion', type=Path, required=True)
    args = parser.parse_args()
    p, r, c = args.production, args.base, args.completion
    receipt = json.loads((c / 'completion.json').read_text())
    assert receipt['status'] == 'staged'
    base = json.loads((r / 'release.json').read_text())
    files = [p / 'audit/tasks.json', p / 'audit/runtime.json', r / 'runtime/runtime.json',
             r / 'runtime/manifest.json', r / 'runtime/scheduler.json']
    if 'files' in receipt:
        files = [Path(path) for path in receipt['files']]
    lock = (p / 'audit/.release-lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def check_inputs():
        for file, digest in receipt['expected_live_sha256'].items():
            assert sha(Path(file)) == digest, 'Live configuration changed: ' + file
        for i, digest in receipt['candidate_sha256'].items():
            assert sha(c / f'config-{i}.json') == digest, 'Candidate changed'
        for name, digest in base['protected_sha256'].items():
            assert sha(p / name) == digest, 'Protected configuration changed: ' + name

    current_scheduler = json.loads(files[4].read_text())

    def active():
        count = 0
        for db, query in [
            (p / 'audit/review.sqlite3', "SELECT count(*) FROM sessions WHERE status IN ('queued','starting','ready')"),
            (Path(current_scheduler['database']), "SELECT count(*) FROM leases WHERE state != 'ended'")
        ]:
            connection = sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True)
            try:
                count += connection.execute(query).fetchone()[0]
            finally:
                connection.close()
        return count

    services = ['aws-unreal-pool.service', 'aws-unreal-explore.service',
                'aws-unreal-evaluate.service', 'aws-unreal-threejs.service']

    def pids():
        return {s: subprocess.check_output(['systemctl', 'show', s, '--property=MainPID', '--value'], text=True).strip() for s in services}

    def control(action, unit):
        subprocess.run(['sudo', '-n', 'systemctl', action, unit], check=True)

    def ready():
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                for port in [19592, 19593]:
                    with socket.create_connection(('127.0.0.1', port), timeout=1):
                        pass
                subprocess.run(['systemctl', 'is-active', '--quiet', base['pool_service']], check=True)
                return
            except (OSError, subprocess.CalledProcessError):
                time.sleep(1)
        raise RuntimeError('Review runtime did not become ready')

    check_inputs()
    if active():
        raise SystemExit('Review is in use; staged configs retained without restarting any service')
    previous_pids = pids()
    backup = c / ('activation-backup-' + str(time.time_ns()))
    backup.mkdir()
    for i, file in enumerate(files):
        shutil.copy2(file, backup / f'{i}.json')
    control('stop', 'aws-unreal-audit.service')
    changed = False
    try:
        check_inputs()
        if active():
            raise RuntimeError('A Review session began before admission closed')
        changed = True
        for i, file in enumerate(files):
            replace(c / f'config-{i}.json', file)
        control('restart', base['pool_service'])
        ready()
        control('start', 'aws-unreal-audit.service')
        deadline = time.monotonic() + 45
        while True:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8092/', timeout=2) as response:
                    assert response.status == 200
                break
            except (OSError, AssertionError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        assert pids() == previous_pids, 'Protected service restarted'
        for name, digest in base['protected_sha256'].items():
            assert sha(p / name) == digest, name
    except Exception:
        if changed:
            control('stop', 'aws-unreal-audit.service')
            for i, file in enumerate(files):
                replace(backup / f'{i}.json', file)
            control('restart', base['pool_service'])
            ready()
        raise
    finally:
        control('start', 'aws-unreal-audit.service')
    receipt.update(status='published', activated_at=time.time(), protected_service_pids=previous_pids,
                   backup=str(backup))
    (c / 'completion.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Published staged Review updates; Explore, Evaluate and Three.js unchanged')


if __name__ == '__main__':
    main()
