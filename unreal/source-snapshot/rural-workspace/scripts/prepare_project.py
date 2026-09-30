"""Prepare the isolated A10 Rural Australia project without changing other worlds."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path('/home/ubuntu/unreal-auditor/rural-workspace')
PROJECT = ROOT / 'project'
TEMPLATE = Path('/home/ubuntu/unreal-auditor/ancient-workspace/project/Plugins/AuditorRuntime')


def main():
    descriptor = PROJECT / 'RuralAustralia.uproject'
    data = json.loads(descriptor.read_text())
    data['EngineAssociation'] = '5.6'
    plugins = {entry['Name']: entry for entry in data.get('Plugins', [])}
    for name in ['AuditorRuntime', 'PixelStreaming2']:
        plugins[name] = {'Name': name, 'Enabled': True}
    for name in ['PythonScriptPlugin', 'EditorScriptingUtilities']:
        plugins[name] = {'Name': name, 'Enabled': True, 'TargetAllowList': ['Editor']}
    data['Plugins'] = list(plugins.values())
    descriptor.write_text(json.dumps(data, indent=2) + '\n')
    destination = PROJECT / 'Plugins/AuditorRuntime'
    if not destination.exists():
        shutil.copytree(TEMPLATE, destination, ignore=shutil.ignore_patterns('Binaries', 'Intermediate'))
    provenance = {
        'template': str(TEMPLATE),
        'files': {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(destination.rglob('*')) if p.is_file()},
    }
    (ROOT / 'out/runtime-template-provenance.json').write_text(json.dumps(provenance, indent=2))
    config = PROJECT / 'Config/DefaultEngine.ini'
    original = ROOT / 'out/source-DefaultEngine.ini'
    if not original.exists():
        shutil.copy2(config, original)
    # Author-supplied rendering settings are merged after real asset inspection.
    # This bootstrap config is for compiling the editor module, not final visual acceptance.
    text = config.read_text()
    start = text.find('[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]')
    if start >= 0:
        end = text.find('\n[', start + 1)
        text = text[:start] + (text[end:] if end >= 0 else '')
    config.write_text(text)
    print(json.dumps({'project': str(descriptor), 'maps_present': len(list((PROJECT / 'Content').rglob('*.umap'))),
                      'status': 'prepared_for_editor_build'}, indent=2))


if __name__ == '__main__':
    main()
