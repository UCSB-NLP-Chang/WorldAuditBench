#!/usr/bin/env python3
"""Compile the restored residential project without regenerating its authored maps."""
import argparse
import json
import platform
from pathlib import Path
import shutil
import subprocess
import os

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--engine', type=Path, default=Path('/opt/UnrealEngine_5.6'))
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/residential-regions-linux')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('Run this builder on the Linux x86_64 host.')
    project = args.project.resolve()
    engine = args.engine.resolve()
    output = args.output.resolve()
    if not project.is_file() or project.stem != 'AtmosphericResidentialHou':
        parser.error('Expected the restored AtmosphericResidentialHou.uproject.')
    version_file = engine / 'Engine/Build/Build.version'
    if not version_file.is_file():
        parser.error('Install Linux Unreal Engine 5.6.1 first, or set --engine.')
    version = json.loads(version_file.read_text())
    if tuple(version.get(k) for k in ('MajorVersion', 'MinorVersion', 'PatchVersion')) != (5, 6, 1):
        parser.error('This archived project is being deployed with matching UE 5.6.1.')
    spec = json.loads((ROOT / 'environments/residential-house/regions.json').read_text())
    for region in spec['regions']:
        asset = project.parent / 'Content' / (region['map'].removeprefix('/Game/') + '.umap')
        if not asset.is_file():
            parser.error(f'Archived region is missing: {asset}; restore the complete source archive.')
    plugin = project.parent / 'Plugins/AuditorRuntime/Source/AuditorRuntime'
    if not plugin.is_dir():
        parser.error('The restored project must include its AuditorRuntime C++ source.')
    logs = ROOT / 'out/remote-linux/build-logs'
    logs.mkdir(parents=True, exist_ok=True)

    def run(label, command, env=None):
        print(f'{label}: running; log: {logs / (label + ".log")}', flush=True)
        with (logs / (label + '.log')).open('w') as log:
            subprocess.run([str(v) for v in command], env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        print(f'{label}: PASS', flush=True)

    # Cooking loads the project in the editor, so its Linux editor module must exist.
    run('editor-build', [engine / 'Engine/Build/BatchFiles/Linux/Build.sh',
                         project.stem + 'Editor', 'Linux', 'Development', project,
                         '-NoHotReloadFromIDE'])
    env = dict(os.environ, UE_ROOT=str(engine), OUTPUT_DIR=str(output),
               MAPS='+'.join(r['map'] for r in spec['regions']))
    run('package', ['bash', ROOT / 'scripts/build_linux.sh', project, '5.6', 'Development'], env)
    launcher = output / 'Linux/AtmosphericResidentialHou.sh'
    if not launcher.is_file():
        raise SystemExit(f'Expected Linux launcher was not produced: {launcher}')
    shutil.copy2(ROOT / 'scripts/launch_residential.sh', output / 'launch.sh')
    (output / 'launch.sh').chmod(0o755)
    shutil.copy2(ROOT / 'environments/residential-house/regions.json', output / 'maps.json')
    (output / 'build-provenance.json').write_text(json.dumps({
        'engine_version': version, 'platform': 'Linux', 'project': str(project),
        'maps': [r['map'] for r in spec['regions']],
        'maps_regenerated': False, 'runtime_smoke_tests_passed': False,
        'observation_service_ready': False,
    }, indent=2) + '\n')
    print(f'Linux package created: {output}. Runtime and observation tests are still required.')


if __name__ == '__main__':
    main()
