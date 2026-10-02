#!/usr/bin/env python3
"""Apply standalone-release defaults to an isolated Unreal project copy."""
import argparse
from pathlib import Path


def replace_body(text, signature, replacement):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[:opening] + '{\n' + replacement + '\n}' + text[end:]


def prepare(project):
    source = project / 'Plugins/AuditorRuntime/Source/AuditorRuntime/Private'
    hud = source / 'AuditorPlaytest.cpp'
    text = hud.read_text()
    text = replace_body(text, 'void AAuditorHUD::DrawHUD()',
                        '    // Release builds have no HUD overlay or minimap background.')
    hud.write_text(text)

    exploration = source / 'AuditorExploration.cpp'
    text = exploration.read_text()
    if '#include "Misc/Paths.h"' not in text:
        text = '#include "Misc/Paths.h"\n' + text
    text = replace_body(text, 'bool Enabled()', ''' if (!Loaded) {
  Loaded = true;
  if (!FParse::Value(FCommandLine::Get(), TEXT("AuditorExplorationPolicy="), Path)) {
   Path = FPaths::Combine(FPaths::ProjectDir(), TEXT("WorldAuditBench/policy.json"));
  }
  FString Text;
  if (!FFileHelper::LoadFileToString(Text, *Path) ||
      !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Policy) ||
      !Policy.IsValid()) {
   Fail(TEXT("Missing or invalid bundled WorldAuditBench exploration policy"));
  }
 }
 return !Path.IsEmpty();''')
    exploration.write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path, help='Isolated build project, never the archival source snapshot')
    args = parser.parse_args()
    prepare(args.project)
