#!/usr/bin/env python3
"""Build the industrial candidate on A10, keeping published games intact."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path('/home/ubuntu/unreal-auditor/industrial-workspace'))
    parser.add_argument('--engine', type=Path, default=Path('/opt/UnrealEngine_5.6'))
    parser.add_argument('--author', action='store_true', help='Embed reviewed task recipes into the three restored maps')
    parser.add_argument('--output', type=Path, help='Use a new candidate directory for a later revision')
    args = parser.parse_args()
    if platform.system() != 'Linux':
        parser.error('Compile and cook on the A10 Linux host.')
    root = args.workspace.resolve()
    project = root / 'project/FactoryEnvironmentCollect.uproject'
    engine = args.engine / 'Engine'
    logs = root / 'out/build'
    logs.mkdir(parents=True, exist_ok=True)
    spec = json.loads((root / 'environments/industrial-factory/regions.json').read_text())
    output = args.output.resolve() if args.output else root / 'dist/industrial-linux'
    runtime = root.parent / 'review-service/state/runtime.json'
    if runtime.exists():
        profiles = json.loads(runtime.read_text()).get('launch_profiles', {}).values()
        if any(Path(profile['binary']).is_relative_to(output) for profile in profiles):
            parser.error('This distribution is published. Choose a fresh --output directory.')

    def run(name, command):
        print(name + ': running', flush=True)
        with (logs / (name + '.log')).open('w') as stream:
            subprocess.run(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT, check=True)
        if 'LogPython: Error:' in (logs / (name + '.log')).read_text(errors='replace'):
            raise RuntimeError(name + ': Unreal Python error; inspect the log')
        print(name + ': PASS', flush=True)

    run('editor', [engine / 'Build/BatchFiles/Linux/Build.sh', project.stem + 'Editor',
                   'Linux', 'Development', project, '-NoHotReloadFromIDE', '-MaxParallelActions=16', '-NoUBA', '-WaitMutex'])
    if args.author:
        run('author', [engine / 'Binaries/Linux/UnrealEditor-Cmd', project, '-run=pythonscript',
                       '-script=' + str(root / 'scripts/unreal_author_industrial_tasks.py'),
                       '-nullrhi', '-nosound', '-unattended'])
    report = project.parent / 'Saved/industrial-map-verification.json'
    report.unlink(missing_ok=True)
    run('maps', [engine / 'Binaries/Linux/UnrealEditor-Cmd', project, '-run=pythonscript',
                 '-script=' + str(root / 'scripts/unreal_verify_industrial_regions.py'),
                 '-nullrhi', '-nosound', '-unattended'])
    assert json.loads(report.read_text())['result'] == 'PASS'
    run('package', [engine / 'Build/BatchFiles/RunUAT.sh', 'BuildCookRun', '-project=' + str(project),
                    '-platform=Linux', '-clientconfig=Development', '-build', '-cook', '-stage',
                    '-pak', '-package', '-archive', '-archivedirectory=' + str(output),
                    '-map=' + '+'.join(region['map'] for region in spec['regions']),
                    '-nop4', '-utf8output', '-unattended', '-WaitForUATMutex',
                    '-UbtArgs=-MaxParallelActions=16 -NoUBA -WaitMutex'])
    for source, dest in [('regions.json', 'maps.json'), ('tasks.json', 'tasks.json')]:
        shutil.copy2(root / 'environments/industrial-factory' / source, output / dest)
    binary = output / 'Linux/FactoryEnvironmentCollect/Binaries/Linux/FactoryEnvironmentCollect'
    with binary.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else None
    if sha is None:
        digest = hashlib.sha256()
        with binary.open('rb') as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(chunk)
        sha = digest.hexdigest()
    (output / 'build-provenance.json').write_text(json.dumps({
        'project': str(project), 'engine': '5.6.1', 'binary_sha256': sha,
        'tasks_embedded': args.author, 'runtime_verified': False,
    }, indent=2) + '\n')
    print('Candidate packaged: ' + str(output), flush=True)


if __name__ == '__main__':
    main()
