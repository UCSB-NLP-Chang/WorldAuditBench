"""Add the validated medieval family to the already-published Review v2 release."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    p.chmod(0o600)


def main():
    from stage_review import preserve_review_versions
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--production', type=Path, required=True)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--completion', type=Path, required=True)
    p.add_argument('--activate', action='store_true')
    a = p.parse_args()
    receipt = json.loads((a.base / 'release.json').read_text())
    assert receipt['status'] == 'published'
    for name, expected in receipt['protected_sha256'].items():
        assert sha(a.production / name) == expected, name
    build = json.loads((a.completion / 'compiled/compile-v2.json').read_text())
    binary = a.completion / 'compiled/MedievalVillage'
    assert sha(binary) == build['sha256'] and build['status'] == 'PASS'
    policy = a.completion / 'policy.json'
    qa = json.loads((a.completion / 'validation.json').read_text())
    assert qa['status'] == 'PASS' and len(qa['tasks']) == 154 and qa['policy_sha256'] == sha(policy)
    policy.chmod(0o600)
    files = [a.production / 'audit/tasks.json', a.production / 'audit/runtime.json',
             a.base / 'runtime/runtime.json', a.base / 'runtime/manifest.json', a.base / 'runtime/scheduler.json']
    before = [json.loads(f.read_text()) for f in files]
    catalog, audit_runtime, runtime, manifest, scheduler = copy.deepcopy(before)
    assert audit_runtime == runtime
    tasks = [t for t in catalog['tasks'] if t.get('family') == 'medieval']
    assert len(tasks) == 24 and all('exploration_revision' not in t for t in tasks)
    profiles = runtime['launch_profiles']
    packages, changed_maps = {}, set()
    for t in tasks:
        key, profile = next((k, v) for k, v in profiles.items() if v.get('runtime_map') == t['map'])
        assert profile['build_sha256'] == t['build_sha256']
        old_binary = Path(profile['binary'])
        root = old_binary.parents[4]
        if str(root) not in packages:
            dest = a.completion / ('package-' + hashlib.sha256(str(root).encode()).hexdigest()[:12])
            if dest.exists():
                raise RuntimeError('Candidate package already exists; avoid overwriting a staged release')
            assert not root.is_symlink()
            subprocess.run(['cp', '-al', str(root), str(dest)], check=True)
            assert not dest.is_symlink()
            for saved in dest.glob('Linux/*/Saved'):
                if saved.is_dir() and not saved.is_symlink():
                    shutil.rmtree(saved)
                    saved.mkdir()
            new_binary = dest / old_binary.relative_to(root)
            old_sha = sha(old_binary)
            new_binary.unlink()
            shutil.copy2(binary, new_binary)
            assert sha(old_binary) == old_sha
            packages[str(root)] = str(new_binary)
        profile.update(binary=packages[str(root)], build_sha256=build['sha256'])
        profile['extra_args'] = [x for x in profile.get('extra_args', []) if not x.startswith('-AuditorExploration')]
        profile['extra_args'] += [f'-AuditorExplorationPolicy={policy}', '-AuditorExplorationTask=' + t['id']]
        t['exploration_revision'] = {'version': 'unreal-exploration-v2-20260917', 'policy_sha256': qa['policy_sha256'], 'previous_build_sha256': t['build_sha256']}
        t['build_sha256'] = build['sha256']
        prior_task = next(old for old in before[0]['tasks'] if old['id'] == t['id'])
        preserve_review_versions(prior_task, t)
        changed_maps.add(key)
    for t in manifest['tasks']:
        if t['map'] in changed_maps:
            t['build_sha256'] = build['sha256']
    for t in scheduler['tasks']:
        if t['map'] in changed_maps:
            t['group'] = hashlib.sha256((build['sha256'] + str(policy)).encode()).hexdigest()
    changed_ids = {t['id'] for t in tasks}
    for old, new in zip(before[0]['tasks'], catalog['tasks']):
        if old['id'] not in changed_ids:
            assert old == new
    for key, old in before[2]['launch_profiles'].items():
        if key not in changed_maps:
            assert profiles[key] == old
    # A changed catalog cannot reuse the fingerprint of the old lease database.
    scheduler["database"] = str(a.base / "runtime/pool-complete.sqlite3")
    candidates = [catalog, runtime, runtime, manifest, scheduler]
    expected = {str(f): sha(f) for f in files}
    for index, value in enumerate(candidates):
        write(a.completion / f'config-{index}.json', value)
    def active():
        d = sqlite3.connect('file:' + str(a.production / 'audit/review.sqlite3') + '?mode=ro', uri=True)
        count = d.execute("select count(*) from sessions where status in ('queued','starting','ready')").fetchone()[0]
        d.close()
        return count
    write(a.completion / 'completion.json', {'status': 'staged', 'tasks': sorted(changed_ids), 'expected_live_sha256': expected, 'candidate_sha256': {str(i): sha(a.completion / f'config-{i}.json') for i in range(len(files))}})
    if not a.activate:
        print('Staged 24 medieval tasks')
        return
    subprocess.run([
        "python3.12", str(Path(__file__).with_name("activate_staged.py")),
        "--production", str(a.production), "--base", str(a.base),
        "--completion", str(a.completion),
    ], check=True)



if __name__ == '__main__':
    main()
