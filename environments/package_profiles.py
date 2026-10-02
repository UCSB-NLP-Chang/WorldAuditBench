"""Adapt self-contained Unreal environment packages to the interactive viewer."""
import json
from pathlib import Path


def load_profiles(root):
    root = Path(root).expanduser().resolve()
    manifests = [root / 'launch.json'] if (root / 'launch.json').is_file() else sorted(root.glob('*/launch.json'))
    profiles = {}
    for path in manifests:
        manifest = json.loads(path.read_text())
        if manifest.get('engine') != 'unreal':
            continue
        for task, entry in manifest['tasks'].items():
            if task in profiles:
                raise ValueError('Task occurs in more than one package: ' + task)
            binary = (path.parent / entry['binary']).resolve()
            if not binary.is_relative_to(path.parent.resolve()):
                raise ValueError('Executable is outside its environment package: ' + task)
            profiles[task] = {
                'binary': str(binary), 'build_sha256': entry['binary_sha256'],
                'runtime_map': entry['launch_map'], 'game_args': entry.get('args', []),
                'build_label': manifest.get('build_label', path.parent.name + ' package'),
            }
    if not profiles:
        raise ValueError('No Unreal launch.json packages found in ' + str(root))
    return profiles
