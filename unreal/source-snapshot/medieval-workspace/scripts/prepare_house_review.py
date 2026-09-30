"""Rebase the house and copy revision and global type ordering on the live release."""
import ast,copy,json,re,shutil,subprocess,sys
from pathlib import Path
from prepare_review import digest
from patch_bug_type_order import patch

WORK=Path('/home/ubuntu/unreal-auditor/medieval-workspace')
SERVICE=WORK.parent/'review-service';STATE=SERVICE/'state'
proof=json.loads((WORK/'out/house-v3/acceptance.json').read_text())
assert proof['result']=='PASS'
binary=Path(proof['binary']);assert digest(binary)==proof['binary_sha256']
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip())
stage=SERVICE/'staging'/proof['release_name'];assert not stage.exists()
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','prepared-state'));stage.chmod(0o700)
manifest=json.loads((STATE/'tasks.json').read_text());config=json.loads((STATE/'runtime.json').read_text())
previous=copy.deepcopy(manifest)
env=WORK/'environments/medieval-village'
tasks=json.loads((env/'tasks.json').read_text())['tasks']
assert len(tasks)==21 and {t['subcategory'] for t in tasks if t['id'] in ('MV18','MV19','MV20')}=={'S3'}
assert next(t for t in tasks if t['id']=='MV18')['target']=='ModernCar'
ours={t['id']:t for t in manifest['tasks'] if t.get('family')=='medieval'}
assert len(ours)==22 and 'MV21' not in ours
template=copy.deepcopy(ours['MV18'])
for t in tasks:
    if t['id'] not in ours:
        entry=copy.deepcopy(template);entry.update(id=t['id'],revision=1,case_id=t['id'],case_path='/?case='+t['id'])
        manifest['tasks'].append(entry);ours[t['id']]=entry
    entry=ours[t['id']]
    if t['id']=='MV19':entry['revision']+=1
    entry.update(map=t['map']+'?Task='+t['id'],title=t['title'],rubrics_i18n=t['rubrics_i18n'],
                 rubrics='\n'.join(t['rubrics_i18n'][lang]['criteria'] for lang in ('en','zh')),subcategory=t['subcategory'],
                 environment='Medieval Village / '+('Market street' if t['region']=='market' else 'Windmill courtyard'))
profile_template=copy.deepcopy(config['launch_profiles'][template['map']])
for entry in ours.values():
    entry['build_sha256']=proof['binary_sha256']
    entry['sha256']=digest(WORK/'project/Content'/(entry['map'].split('?')[0][6:]+'.umap'))
    profile=copy.deepcopy(config['launch_profiles'].get(entry['map'],profile_template))
    profile.update(binary=str(binary),build_sha256=proof['binary_sha256'],game_args=proof['game_args'])
    config['launch_profiles'][entry['map']]=profile
(stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(stage/'candidate-runtime.json').write_text(json.dumps(config,indent=2));(stage/'candidate-runtime.json').chmod(0o600)
server=stage/'server.py';text=server.read_text();old=r'MV(?:0[1-9]|1[0-9]|20)';assert text.count(old)==2
text=text.replace(old,r'MV(?:0[1-9]|1[0-9]|2[01])')
ast.parse(text);server.write_text(text)
patch(stage)
app=stage/'static/app.js';text=app.read_text();match=re.search(r'const sceneDescriptions=(\[.*?\]);',text);assert match
scenes=json.loads(match[1]);new_scenes={s['map']:s for s in json.loads((env/'scene-descriptions.json').read_text())}
scenes=[new_scenes.get(s['map'],s) for s in scenes]
app.write_text(text[:match.start(1)]+json.dumps(scenes,ensure_ascii=False)+text[match.end(1):])
# Update existing finite catalog fixtures, preserving the rest of the service suite.
test=stage/'tests/test_medieval.py';text=test.read_text().replace('range(1,21)','range(1,22)').replace("'S1','S3','S3','S3']","'S1','S3','S3','S3','S3']").replace('i<=10 or i>=19','i<=10 or i in (19,20)');test.write_text(text)
test=stage/'tests/test_taxonomy.py';text=test.read_text();assert text.count(',216)')==2 and '[7, 3, 4]' in text
test.write_text(text.replace(',216)',',217)').replace('[7, 3, 4]','[7, 3, 5]'))
provenance=dict(source_release=str(source),source_files_sha256={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css') and '__pycache__' not in p.parts},
    source_state_sha256={n:digest(STATE/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},binary_sha256=proof['binary_sha256'],previous_entries=len(previous['tasks']),added_entries=1,changed_cases=['MV19'],ordering='environment, baseline, G1-G3, C1-C3, V1-V3, T1-T3, S1-S3, unclassified, stable ID',acceptance=proof)
(stage/'medieval-provenance.json').write_text(json.dumps(provenance,indent=2))
print(stage,flush=True)
