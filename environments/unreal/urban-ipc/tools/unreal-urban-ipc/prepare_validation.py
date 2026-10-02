"""Match the live AWS cooked content to Linux build-host packages for QA."""
import json
from pathlib import Path
import shutil
import subprocess
from build import sha

w = Path('/home/ubuntu/unreal-auditor/urban-ipc-20260918')
inventory = json.loads((w / 'aws-inventory.json').read_text())
expected = json.loads((w / 'aws-content.json').read_text())
available = {}
for package in Path('/home/ubuntu/unreal-auditor/exploration-v2-20260917/packages').glob('urban-*'):
    root = package / 'Linux/NYC_Building_Volume2/Content'
    available[package] = {str(f.relative_to(root)): sha(f) for f in root.rglob('*') if f.is_file()}
matched = {}
for binary, content in expected.items():
    matches = [p for p, digest in available.items() if digest == content]
    assert len(matches) == 1, (binary, matches)
    matched[binary] = str(matches[0])
packages = {}
for binary, source in matched.items():
    dest = w / 'packages' / Path(binary).parents[4].name
    dest.parent.mkdir(exist_ok=True)
    subprocess.run(['cp', '-al', source, str(dest)], check=True)
    target = dest / 'Linux/NYC_Building_Volume2/Binaries/Linux/NYC_Building_Volume2'
    target.unlink()
    shutil.copy2(w / 'NYC_Building_Volume2', target)
    saved = dest / 'Linux/NYC_Building_Volume2/Saved'
    if saved.exists():
        shutil.rmtree(saved)
    packages[binary] = str(target)
policies = {}
for index, (old, policy) in enumerate(inventory['policies'].items()):
    new = w / f'policy-{index}.json'
    new.write_text(json.dumps(policy, indent=2))
    policies[old] = str(new)
profiles = []
for task in inventory['tasks']:
    candidates = [v for v in inventory['profiles'].values() if v['runtime_map'] == task['map']]
    assert len(candidates) == 1
    profile = candidates[0]
    args = [('-AuditorExplorationPolicy=' + policies[a.split('=', 1)[1]])
            if a.startswith('-AuditorExplorationPolicy=') else a for a in profile['extra_args']]
    profiles.append({'task': task, 'binary': packages[profile['binary']], 'extra_args': args,
                     'aws_binary': profile['binary']})
(w / 'qa-profiles.json').write_text(json.dumps(profiles, indent=2))
(w / 'content-match.json').write_text(json.dumps({'matches': matched, 'content': expected}, indent=2))
print('Prepared', len(profiles), 'tasks with byte-identical cooked content', flush=True)
