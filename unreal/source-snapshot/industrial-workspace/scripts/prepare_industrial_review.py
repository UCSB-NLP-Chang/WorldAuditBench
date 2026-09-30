#!/usr/bin/env python3
"""Prepare an additive industrial review release from the live A10 website."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path('/home/ubuntu/unreal-auditor')
WORK = ROOT / 'industrial-workspace'
SERVICE = ROOT / 'review-service'
STATE = SERVICE / 'state'
STAGE = SERVICE / 'staging/industrial-20260912'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    source = Path(subprocess.check_output(['systemctl', 'show', 'urban-review-pilot.service',
                                           '-p', 'WorkingDirectory', '--value'], text=True).strip())
    assert source.is_relative_to(SERVICE / 'releases')
    assert not STAGE.exists(), 'Use a fresh stage; preserve any existing candidate.'
    shutil.copytree(source, STAGE, ignore=shutil.ignore_patterns('__pycache__', 'prepared-state'))
    STAGE.chmod(0o700)
    env = WORK / 'environments/industrial-factory'
    catalog = json.loads((env / 'tasks.json').read_text())['tasks']
    regions = json.loads((env / 'regions.json').read_text())['regions']
    scenes = json.loads((env / 'scene-descriptions.json').read_text())
    binary = WORK / 'dist/industrial-linux/Linux/FactoryEnvironmentCollect/Binaries/Linux/FactoryEnvironmentCollect'
    sha = digest(binary)
    manifest = json.loads((STATE / 'tasks.json').read_text())
    config = json.loads((STATE / 'runtime.json').read_text())
    assert not any(t.get('family') == 'industrial' for t in manifest['tasks'])
    entries = []
    keys = next(p['key_filter'] for p in config['launch_profiles'].values() if p.get('family') == 'subway')
    for index, region in enumerate(regions, 1):
        map_hash = digest(WORK / 'project/Content' / (region['map'][6:] + '.umap'))
        baseline = dict(id=f'IB{index:02}', title=region['name'], case_type='baseline', rubrics_i18n={
            'en': dict(expected='The factory scene behaves normally.', steps='Walk around and inspect the equipment.', criteria='No injected anomaly is present.'),
            'zh': dict(expected='工厂场景正常运行。', steps='在场景中行走并检查设备。', criteria='没有注入的异常。'),
        })
        for task in [baseline] + [t | {'case_type': 'bug'} for t in catalog if t['region'] == region['id']]:
            task_id = task['id']
            task_map = region['map'] + ('?Task=' + task_id if task['case_type'] == 'bug' else '')
            entry = dict(id=task_id, revision=1, map=task_map, sha256=map_hash,
                         build_sha256=sha, runtime_switch=True, family='industrial',
                         environment='Industrial / ' + region['name'], case_id=task_id,
                         case_path='/?case=' + task_id, case_type=task['case_type'], title=task['title'],
                         rubrics_i18n=task['rubrics_i18n'],
                         rubrics='\n'.join(task['rubrics_i18n'][lang]['criteria'] for lang in ('en', 'zh')))
            if 'subcategory' in task:
                entry['subcategory'] = task['subcategory']
            entries.append(entry)
            config['launch_profiles'][task_map] = dict(binary=str(binary), build_sha256=sha,
                key_filter=keys, family='industrial', runtime_switch=True,
                game_args=['-vulkan', '-sm5', '-PixelStreamingWebRTCMaxFps=30',
                           '-ExecCmds=t.MaxFPS 30'])
    assert len(entries) == 21 and len(catalog) == 18
    manifest['tasks'].extend(entries)
    assert len({t['id'] for t in manifest['tasks']}) == len(manifest['tasks'])
    (STAGE / 'tasks.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    private = STAGE / 'candidate-runtime.json'
    private.write_text(json.dumps(config, indent=2)); private.chmod(0o600)
    (STAGE / 'industrial-runtime-profiles.json').write_text(json.dumps(
        {key: value for key, value in config['launch_profiles'].items() if value.get('family') == 'industrial'}, indent=2))

    server = STAGE / 'server.py'
    text = server.read_text()
    old = '|AB0[1-3]|A(?:0[1-9]|1[0-9]|20)'
    assert old in text
    text = text.replace(old, old + '|IB0[1-3]|I(?:0[1-9]|1[0-8])')
    marker = "            if t['id'] in ancient:allowed="
    assert marker in text
    text = text.replace(marker,
        "            industrial={'IB01':'AssemblyHall','IB02':'VehicleTest','IB03':'ControlRoom'}\n"
        "            if t['id'] in industrial:allowed=('/Game/Auditor/Industrial/'+industrial[t['id']],)\n"
        "            elif t['id'].startswith('I'):allowed=tuple('/Game/Auditor/Industrial/'+region+'?Task='+t['id'] for region in ('AssemblyHall','VehicleTest','ControlRoom'))\n"
        "            elif t['id'] in ancient:allowed=")
    server.write_text(text)
    app = STAGE / 'static/app.js'
    text = app.read_text()
    marker = 'let match;'
    assert marker in text
    text = text.replace(marker, "let match;if((match=/^IB(\\d+)$/.exec(id)))return 'unreal_industrial_baseline_'+match[1].padStart(2,'0');if((match=/^I(\\d+)$/.exec(id)))return 'unreal_industrial_bug_'+match[1].padStart(2,'0');", 1)
    family_order = re.search(r'(function orderedTasks\(tasks\)\{const family=t=>\(\{)([^}]+)(\}\[t.family\])', text)
    assert family_order
    index = max(map(int, re.findall(r':(\d+)', family_order[2]))) + 1
    text = text[:family_order.end(2)] + ',industrial:' + str(index) + text[family_order.end(2):]
    text = text.replace("ancient:'Ancient Chinese City'", "ancient:'Ancient Chinese City',industrial:'Industrial'")
    text = text.replace("return {Market:'Market street'", "return {AssemblyHall:'Assembly hall',VehicleTest:'Vehicle test & loading bay',ControlRoom:'Control room',Market:'Market street'")
    family_loop = re.search(r'function populateTasks\(preferred\).*?for\(const key of (\[[^\]]+\])', text)
    assert family_loop
    text = text[:family_loop.end(1) - 1] + ",'industrial'" + text[family_loop.end(1) - 1:]
    text = text.replace("if(task.family==='ancient'){", "if(task.family==='ancient'||task.family==='industrial'){")
    match = re.search(r'const sceneDescriptions=(\[.*?\]);', text)
    assert match
    descriptions = json.loads(match[1])
    descriptions.extend(scenes)
    text = text[:match.start(1)] + json.dumps(descriptions, ensure_ascii=False) + text[match.end(1):]
    app.write_text(text)
    page = STAGE / 'static/index.html'
    text = page.read_text()
    marker = '<option value="ancient">Ancient Chinese City</option>'
    assert marker in text
    text = text.replace(marker, marker + '<option value="industrial">Industrial</option>')
    families = list(dict.fromkeys(task['family'] for task in manifest['tasks']))
    family_names = {'subway': 'Subway', 'indoor': 'Indoor', 'urban': 'Urban', 'ancient': 'Ancient Chinese City', 'industrial': 'Industrial'}
    caption = ' · '.join(family_names.get(family, next(task['environment'].split(' / ')[0] for task in manifest['tasks'] if task['family'] == family)) for family in families)
    text = re.sub(r'(<strong id="stat-environments">.*?</strong><small>).*?(</small>)',
                  lambda match: match[1] + caption + match[2], text)
    page.write_text(text)
    taxonomy_test = STAGE / 'tests/test_taxonomy.py'
    test_source = taxonomy_test.read_text()
    count = re.search(r"sum\(sub\['tasks'\] for sub in subs\),(\d+)\)", test_source)
    assert count, 'Review the source catalog count assertions before extending them.'
    old_count = int(count[1])
    assert test_source.count(',' + str(old_count) + ')') == 2
    taxonomy_test.write_text(test_source.replace(',' + str(old_count) + ')', ',' + str(old_count + len(catalog)) + ')'))
    (STAGE / 'industrial-scene-descriptions.json').write_text(json.dumps(scenes, ensure_ascii=False, indent=2))
    (STAGE / 'industrial-provenance.json').write_text(json.dumps(dict(source_release=str(source),
        source_state_sha256={name: digest(STATE / name) for name in ('tasks.json', 'runtime.json', 'service-env.json', 'participants.json')},
        source_files_sha256={str(path.relative_to(source)): digest(path) for path in source.rglob('*')
                             if path.is_file() and path.suffix in ('.py', '.js', '.html', '.css', '.json')
                             and '__pycache__' not in path.parts and 'prepared-state' not in path.parts},
        industrial_binary_sha256=sha, previous_entries=len(manifest['tasks']) - 21, added_entries=21), indent=2))
    print('Prepared ' + str(STAGE) + ' with ' + str(len(manifest['tasks'])) + ' entries.')


if __name__ == '__main__':
    main()
