"""Build Urban IPC in an isolated source copy on the Linux Unreal build host.

No maps are recooked. The resulting executable is staged alongside unchanged
cooked content; published source trees and packages are never overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    a = p.parse_args()
    project = a.work / 'project'
    project.mkdir(parents=True, exist_ok=False)
    for name in ('Source', 'Config', 'Plugins'):
        shutil.copytree(a.source / name, project / name,
                        ignore=shutil.ignore_patterns('Intermediate', 'Binaries'))
    name = 'NYC_Building_Volume2'
    shutil.copy2(a.source / (name + '.uproject'), project)
    module = project / 'Plugins/AuditorRuntime/Source/AuditorRuntime'
    before = {str(f.relative_to(module)): sha(f) for f in module.rglob('*') if f.is_file()}
    for part, filename in [('Private', 'AuditorRemote.cpp'), ('Public', 'AuditorRemote.h')]:
        shutil.copyfile(Path(__file__).parent / 'native' / filename, module / part / filename)
    f = module / 'Private/AuditorPlaytest.cpp'
    s = f.read_text()
    old = 'const bool bAutomatedRun = bBoundarySmokeTest'
    assert s.count(old) == 1
    f.write_text(s.replace(old, 'const bool bAutomatedRun = FParse::Param(FCommandLine::Get(), TEXT("AuditorServe")) || bBoundarySmokeTest'))
    f = module / 'Public/AuditorStateScenario.h'
    s = f.read_text()
    assert 'void RequestInteraction(AActor* RequestingPawn);' in s
    f.write_text(s.replace('void RequestInteraction(AActor* RequestingPawn);', 'bool RequestInteraction(AActor* RequestingPawn);'))
    f = module / 'Private/AuditorStateScenario.cpp'
    s = f.read_text()
    start, end = s.index('void AAuditorStateScenario::RequestInteraction'), s.index('void AAuditorStateScenario::Tick')
    interaction = s[start:end].replace('void AAuditorStateScenario::RequestInteraction', 'bool AAuditorStateScenario::RequestInteraction')
    interaction = interaction.replace('return;', 'return false;')
    interaction = interaction.replace('if (Hit.GetActor() == TargetActor) bInteractionRequested = true;',
        'if (Hit.GetActor() != TargetActor) return false;\n    bInteractionRequested = true;\n    return true;')
    f.write_text(s[:start] + interaction + s[end:])
    after = {str(f.relative_to(module)): sha(f) for f in module.rglob('*') if f.is_file()}
    cmd = ['/opt/UnrealEngine_5.6/Engine/Build/BatchFiles/Linux/Build.sh', name,
           'Linux', 'Development', str(project / (name + '.uproject')),
           '-WaitMutex', '-MaxParallelActions=16', '-NoUBA']
    with (a.work / 'compile.log').open('w') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    binary = project / 'Binaries/Linux' / name
    shutil.copy2(binary, a.work / name)
    result = {'status': 'PASS', 'source': str(a.source), 'binary': str(a.work / name),
              'binary_sha256': sha(binary), 'command': cmd, 'before': before, 'after': after,
              'cooked_content_changed': False}
    (a.work / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('before', 'after')}), flush=True)


if __name__ == '__main__':
    main()
