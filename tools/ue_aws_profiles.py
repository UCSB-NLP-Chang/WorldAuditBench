"""Mirror the AWS Unreal review release onto this machine for the VLA arm.

Reads the AWS release snapshot that the Codex workspace `unreal-auditor/unreal-area-3x-20260918` recorded (live-profiles.json: catalog
entry + launch profile + exploration policy per task) and writes reports/ue-aws-profiles-<date>.json with, per task, the LOCAL copy of
the same build (binary sha256-verified against the AWS catalog; Indoor = the build recompiled on 2026-09-18 for `excluded_bounds`),
the runtime map, the game args and the exploration-policy args (`-AuditorExplorationTask`, `-AuditorExplorationPolicy`) that the
review site passes to the game, plus the policy entry itself (frozen spawn/yaw, 3x bounds, focus/target).  harness/vla_ue.py
consumes it with --profiles.

  python3 tools/ue_aws_profiles.py [--out reports/ue-aws-profiles-20260918.json]
"""
import argparse, json, hashlib, pathlib, datetime, collections

UA = pathlib.Path('/home/ubuntu/unreal-auditor')
PK = UA / 'exploration-v2-20260917/packages'
POLDIR = pathlib.Path('reports/ue-policies-20260918')
LOCAL = {  # AWS package dir -> local copy of the same build (binary sha256 verified below)
    'concourse-cleanup-20260918/package-v2': UA / 'subway-workspace/dist/concourse-cleanup-20260918-v2',
    'exploration-v2-preview-20260917/packages/subway-b63b15524674': PK / 'subway-046e1f597821',
    'exploration-v2-preview-20260917/packages/indoor-6984d3ba1e0b': UA / 'unreal-area-3x-20260918/package',   # superseded 2026-09-18 by the recompiled Indoor build
    'exploration-v2-preview-20260917/packages/urban-c6f314070433': PK / 'urban-fd7f09655022',
    'exploration-v2-preview-20260917/packages/urban-ec94cce5d64b': PK / 'urban-7762792c18ec',
    'exploration-v2-preview-20260917/packages/urban-e63d0c3c26bd': PK / 'urban-f80d9bc8ede8',
    'exploration-v2-preview-20260917/packages/urban-0bcf6af8a87a': PK / 'urban-0b86769895f2',
    'exploration-v2-preview-20260917/packages/ancient-74e7762ddff9': PK / 'ancient-2fb2b968f273',
    'exploration-v2-preview-20260917/packages/industrial-90f7e645b0df': PK / 'industrial-6cc7a2375531',
    'exploration-v2-preview-20260917/packages/rural-f8c406483da2': PK / 'rural-3ccbb05ba3ef',
    'exploration-v2-medieval-20260917/package-092c5babf747': PK / 'medieval-b1afad4e4489'}
NEW_INDOOR_SHA = '09fa7b331005394cd71d087bf4c8374781c1c067ddea5ed4de052d11077dbf9b'   # unreal-area-3x-20260918/build.json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='reports/ue-aws-profiles-20260918.json')
    a = ap.parse_args()
    live = json.load(open(UA / 'unreal-area-3x-20260918/live-profiles.json'))
    a3 = json.load(open(POLDIR / 'unreal-area-3x-20260918.json'))
    v3 = json.load(open(POLDIR / 'exploration-v3-20260917.json'))
    assert v3['version'] == 'unreal-exploration-v3-20260917' and a3['version'] == 'unreal-area-3x-20260918'
    pol_path = {'v3': str((POLDIR / 'exploration-v3-20260917.json').resolve()), 'a3': str((POLDIR / 'unreal-area-3x-20260918.json').resolve())}
    cache = {}

    def sha(p):
        if p not in cache:
            cache[p] = hashlib.sha256(open(p, 'rb').read()).hexdigest()
        return cache[p]

    tasks, problems = {}, []
    for tid, v in live.items():
        prof, pol = v['profile'], v['policy']
        aws_bin = prof['binary']
        key = next((k for k in LOCAL if f'/{k}/' in aws_bin), None)
        if key is None:
            problems.append((tid, 'no local package for ' + aws_bin)); continue
        binary = LOCAL[key] / aws_bin.split(f'/{key}/', 1)[1]
        if not binary.exists():
            problems.append((tid, f'missing {binary}')); continue
        h = sha(str(binary))
        expect = NEW_INDOOR_SHA if 'indoor' in key else prof['build_sha256']
        if h != expect:
            problems.append((tid, f'sha mismatch {binary}: {h[:12]} != {expect[:12]}')); continue
        if tid in a3['tasks']:
            entry, ppath, pver = a3['tasks'][tid], pol_path['a3'], a3['version']
        else:
            entry, ppath, pver = v3['tasks'].get(tid), pol_path['v3'], v3['version']
            if entry is None:
                problems.append((tid, 'no v3 policy entry')); continue
            if entry != pol:
                problems.append((tid, 'v3 policy entry differs from the live snapshot'))
        runtime_map = prof['runtime_map']
        if '?Task=' in runtime_map and runtime_map.split('?Task=', 1)[1] != tid:
            problems.append((tid, 'runtime_map task differs ' + runtime_map))
        tasks[tid] = {'task': v['task'], 'family': pol['family'], 'case_type': pol['case_type'],
                      'binary': str(binary), 'build_sha256': h, 'aws_binary': aws_bin, 'aws_build_sha256': prof['build_sha256'],
                      'runtime_map': runtime_map, 'game_args': prof['game_args'],
                      'extra_args': [f'-AuditorExplorationTask={tid}', f'-AuditorExplorationPolicy={ppath}'],
                      'policy_version': pver, 'policy_path': ppath, 'policy': entry}
    out = {'generated': datetime.datetime.utcnow().isoformat() + 'Z',
           'source': 'AWS review release unreal-area-3x-20260918 (live-profiles snapshot + area-3x policy/QA profiles under '
                     '/home/ubuntu/unreal-auditor/unreal-area-3x-20260918); binaries are this machine\'s copies of the same builds, '
                     'sha256-verified against the AWS catalog (Indoor: the recompiled build of 2026-09-18)',
           'policies': {v3['version']: {'path': pol_path['v3'], 'sha256': sha(pol_path['v3']), 'tasks': sorted(t for t in tasks if tasks[t]['policy_version'] == v3['version'])},
                        a3['version']: {'path': pol_path['a3'], 'sha256': sha(pol_path['a3']), 'tasks': sorted(t for t in tasks if tasks[t]['policy_version'] == a3['version'])}},
           'tasks': tasks}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print('tasks written', len(tasks), '| problems', len(problems)); [print('  ', p) for p in problems[:20]]
    print('by family/case', dict(collections.Counter((t['family'], t['case_type']) for t in tasks.values())))
    print('binaries', dict(collections.Counter(t['binary'].split('/unreal-auditor/')[1].split('/Linux/')[0] for t in tasks.values())))
    print('focus_source (bug tasks)', dict(collections.Counter(t['policy'].get('focus_source') for t in tasks.values() if t['case_type'] == 'bug')))
    print('bug tasks with target', sum(1 for t in tasks.values() if t['case_type'] == 'bug' and t['policy'].get('target')), '/', sum(1 for t in tasks.values() if t['case_type'] == 'bug'))


if __name__ == '__main__':
    main()
