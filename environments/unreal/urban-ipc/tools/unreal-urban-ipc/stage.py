"""Stage the verified IPC executable for Review/model use on AWS only.

Run after uploading the executable, build.json, qa.json, aws-inventory.json and
aws-content.json into the release directory. Use the existing idle-only release
transaction to publish completion.json; this script never restarts a service.
"""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import subprocess
import sys

P = Path('/home/ec2-user/unreal-production')
BASE = Path('/home/ec2-user/unreal-review-releases/exploration-v2-preview-20260917')
RELEASE = Path('/home/ec2-user/unreal-review-releases/urban-ipc-20260918')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8388608), b''):
            h.update(block)
    return h.hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')
    path.chmod(0o600)


def main():
    build = json.loads((RELEASE / 'build.json').read_text())
    qa = json.loads((RELEASE / 'qa.json').read_text())
    inventory = json.loads((RELEASE / 'aws-inventory.json').read_text())
    expected_content = json.loads((RELEASE / 'aws-content.json').read_text())
    assert sha(RELEASE / 'NYC_Building_Volume2') == build['binary_sha256']
    ids = {t['id'] for t in inventory['tasks']}
    assert qa['status'] == 'PASS' and qa['binary_sha256'] == build['binary_sha256']
    assert {r['task'] for r in qa['results'] if r['status'] == 'PASS'} == ids
    files = [P/'audit/tasks.json', P/'audit/runtime.json', BASE/'runtime/runtime.json',
             BASE/'runtime/manifest.json', BASE/'runtime/scheduler.json',
             P/'shared/production-links/review-v2/review.json']
    original = [json.loads(f.read_text()) for f in files]
    cat, runtime, pool_runtime, manifest, scheduler, link = copy.deepcopy(original)
    assert runtime == pool_runtime
    snapshot = {t['id']: t for t in inventory['tasks']}
    assert {t['id'] for t in cat['tasks'] if t.get('family') == 'urban'} == ids
    for t in cat['tasks']:
        if t['id'] in ids:
            assert t == snapshot[t['id']], 'Urban catalog changed during build; refresh and revalidate'
    packages = {}
    for old_binary, hashes in expected_content.items():
        old_binary = Path(old_binary)
        content = old_binary.parents[2] / 'Content'
        assert {str(f.relative_to(content)): sha(f) for f in content.rglob('*') if f.is_file()} == hashes
        dest = RELEASE / 'packages' / old_binary.parents[4].name
        dest.parent.mkdir(exist_ok=True)
        subprocess.run(['cp', '-al', str(old_binary.parents[4]), str(dest)], check=True)
        binary = dest / old_binary.relative_to(old_binary.parents[4])
        binary.unlink()  # Never overwrite a hard link into a published package.
        shutil.copy2(RELEASE / 'NYC_Building_Volume2', binary)
        binary.chmod(0o755)
        saved = binary.parents[2] / 'Saved'
        if saved.exists():
            shutil.rmtree(saved)
        packages[str(old_binary)] = str(binary)
    changed = {}
    for t in cat['tasks']:
        if t['id'] not in ids:
            continue
        previous = {k: t[k] for k in ('revision', 'sha256', 'build_sha256')}
        aliases = t.setdefault('review_compatible_versions', [])
        if previous not in aliases:
            aliases.append(previous)
        # Urban revisions are embedded in map paths. Content/targets are identical.
        t['build_sha256'] = build['binary_sha256']
        t['agent_interface'] = {'release': RELEASE.name, 'native_ipc': True}
        key = next(k for k, v in runtime['launch_profiles'].items() if v.get('runtime_map') == t['map'])
        profile = runtime['launch_profiles'][key]
        assert profile == inventory['profiles'][key]
        profile['binary'] = packages[profile['binary']]
        profile['build_sha256'] = build['binary_sha256']
        changed[key] = t['id']
    for t in manifest['tasks']:
        if t['map'] in changed:
            t['build_sha256'] = build['binary_sha256']
    for t in scheduler['tasks']:
        if t['map'] in changed:
            profile = runtime['launch_profiles'][t['map']]
            policy = next(a for a in profile['extra_args'] if a.startswith('-AuditorExplorationPolicy='))
            t['group'] = hashlib.sha256((profile['binary'] + policy).encode()).hexdigest()
    scheduler['database'] = str(BASE/'runtime/pool-urban-ipc-20260918.sqlite3')
    old_tasks = {t['id']: t for t in original[0]['tasks']}
    for t in cat['tasks']:
        old = old_tasks[t['id']]
        if t['id'] not in ids:
            assert t == old
        else:
            for field in ('map', 'revision', 'sha256', 'rubrics_i18n'):
                assert t[field] == old[field]
    for key, profile in runtime['launch_profiles'].items():
        old = original[1]['launch_profiles'][key]
        if key not in changed:
            assert profile == old
        else:
            assert profile['extra_args'] == old['extra_args']
    for i, obj in enumerate([cat, runtime, runtime, manifest, scheduler, link]):
        save(RELEASE/f'config-{i}.json', obj)
    sys.path.insert(0, str(P/'code/explore'))
    from bf.cost_scheduler import Scheduler
    Scheduler(scheduler['database'], scheduler['tasks'], **scheduler['limits'])
    save(RELEASE/'completion.json', {'status': 'staged', 'files': list(map(str, files)),
        'tasks': sorted(ids), 'expected_live_sha256': {str(f): sha(f) for f in files},
        'candidate_sha256': {str(i): sha(RELEASE/f'config-{i}.json') for i in range(len(files))},
        'cooked_content_unchanged': True, 'starts_and_bounds_unchanged': True,
        'description': 'Enable opt-in Urban agent IPC; preserve human controls and existing approvals'})
    print('Staged', len(ids), 'Urban tasks; no service restarted')


if __name__ == '__main__':
    main()
