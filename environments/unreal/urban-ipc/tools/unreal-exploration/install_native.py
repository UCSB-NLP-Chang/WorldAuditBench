"""Install opt-in exploration hooks into an Unreal AuditorRuntime source tree.

Run on the Unreal build host. This does not cook maps or replace a published build.
"""
import argparse
from pathlib import Path
import re
import shutil


def include(text):
    if '#include "AuditorExploration.h"' in text:
        return text
    # Unreal requires each translation unit's own header to remain first.
    return re.sub(r'(#include "[^"]+"\n)', r'\1#include "AuditorExploration.h"\n', text, count=1)


def install(module, backup):
    private = module / "Private"
    edits = {}
    for path in private.glob("*.cpp"):
        old = path.read_text()
        if path.name == "AuditorExploration.cpp":
            continue
        new = old
        if path.name == "AuditorPlaytest.cpp" and "AuditorExploration::Expand(this)" not in old:
            new, n = re.subn(r'(void AAuditorRegion::BeginPlay\(\)\s*\{\s*Super::BeginPlay\(\);)',
                             r'\1\n    AuditorExploration::Expand(this);', new)
            assert n == 1, "Expected one region BeginPlay"
            new, n = re.subn(r'(void AAuditorCharacter::Tick\(float (\w+)\)\s*\{\s*Super::Tick\(\2\);)',
                             r'\1\n    if (Controller && Region && !TActorIterator<AAuditorTasks>(GetWorld()) && GetWorld()->GetTimeSeconds() > 0.1f) AuditorExploration::Apply(this);', new)
            assert n == 1, "Expected one character Tick"
        elif path.name == "AuditorTasks.cpp" and "AuditorExploration::Apply" not in old:
            new, n = re.subn(r'(Initialized = Initialize\(\);)',
                             r'\1\n        if (Initialized) AuditorExploration::Apply(Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0)));', new)
            assert n == 1, "Expected one task initialization"
        elif path.name not in {"AuditorPlaytest.cpp", "AuditorTasks.cpp", "AuditorRemote.cpp", "AuditorReviewSwitch.cpp"} and "AuditorExploration::Pending" not in old:
            new = re.sub(r'(void A\w+::Tick\(float (\w+)\)\s*\{\s*Super::Tick\(\2\);)',
                         r'\1\n    if (AuditorExploration::Pending(GetWorld())) return;', new)
        if new != old:
            edits[path] = include(new)
    # Validate all hooks before touching any file. Refuse to overwrite a backup.
    for path, text in edits.items():
        saved = backup / path.relative_to(module)
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.exists():
            shutil.copy2(path, saved)
        path.write_text(text)
    native = Path(__file__).parent / "native"
    # Use current mtimes so an existing object cannot hide a newer helper's code.
    shutil.copyfile(native / "AuditorExploration.cpp", private / "AuditorExploration.cpp")
    shutil.copyfile(native / "AuditorExploration.h", module / "Public/AuditorExploration.h")
    return [str(p) for p in edits]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    for changed in install(args.module, args.backup):
        print(changed)
