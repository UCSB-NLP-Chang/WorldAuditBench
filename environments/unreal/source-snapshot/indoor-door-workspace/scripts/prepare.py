from pathlib import Path
import json,hashlib,subprocess,shutil,copy
root=Path('/home/ubuntu/unreal-auditor');w=root/'indoor-door-workspace';out=w/'out';out.mkdir(parents=True,exist_ok=True);svc=root/'review-service';state=svc/'state';indoor=root/'indoor-workspace'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=w/'indoor-door-vase-20260913-v3';assert not stage.exists()
source_hashes={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css') and '__pycache__' not in p.parts}
state_hashes={n:sha(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']}
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','prepared-state'));stage.chmod(0o700)
manifest=read(state/'tasks.json');before=copy.deepcopy(manifest);runtime=read(state/'runtime.json')
authored=read(indoor/'environments/residential-house/tasks.json');original=read(w/'backup/environments/residential-house/tasks.json')
assert [t for t in authored['tasks'] if t['id'] not in ('H09','H15')]==[t for t in original['tasks'] if t['id']!='H09']
t=next(t for t in authored['tasks'] if t['id']=='H15')
binary=indoor/'dist/indoor-door-vase-20260913-v3/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou';bh=sha(binary)
ours=[e for e in manifest['tasks'] if e.get('family')=='indoor'];assert len(ours)==16
for e in ours:
 if e['id']=='H09':
  vase=next(x for x in authored['tasks'] if x['id']=='H09')
  e.update(revision=e['revision']+1,title=vase['title'],rubrics_i18n=vase['rubrics_i18n'],rubrics='\n'.join(' '.join(vase['rubrics_i18n'][l][k] for k in ['criteria','expected']) for l in ['en','zh']))
  e.pop('review_compatible_versions',None)
 else:
  old={k:e[k] for k in ['revision','sha256','build_sha256']};aliases=e.setdefault('review_compatible_versions',[])
  if old not in aliases:aliases.append(old)
 e['build_sha256']=bh;e['sha256']=sha(indoor/'project/Content'/(e['map'].split('?')[0][6:]+'.umap'))
 profile=runtime['launch_profiles'][e['map']];profile.update(binary=str(binary),build_sha256=bh)
 assert '-sm5' in profile['game_args'] and '-sm6' not in profile['game_args']
e=copy.deepcopy(next(e for e in ours if e['id']=='H12'))
e.update(id='H15',revision=1,map='/Game/Auditor/Regions/BedroomSuite?Task=H15',case_id='H15',case_path='/?case=H15',title=t['title'],subcategory='collision.missing',taxonomy_label='碰撞与物理 · 应阻挡而发生穿透',rubrics_i18n=t['rubrics_i18n'],rubrics='\n'.join(' '.join(t['rubrics_i18n'][l][k] for k in ['criteria','expected']) for l in ['en','zh']))
e.pop('review_compatible_versions',None);manifest['tasks'].append(e)
runtime['launch_profiles'][e['map']]=copy.deepcopy(runtime['launch_profiles']['/Game/Auditor/Regions/BedroomSuite?Task=H12'])
# The new scene description states the available interaction without giving away the bug.
import re
p=stage/'static/app.js';js=p.read_text();match=re.search(r'const sceneDescriptions=(.*?);\n',js);descs=json.loads(match.group(1))
desc=dict(map='/Game/Auditor/Regions/BedroomSuite',task_ids=['H15'],description=dict(en='A bedroom with an adjoining bathroom and a storage box near the entrance. Interactive object: bedroom door.',zh='连通浴室的卧室，门边放着收纳箱。可交互物体：卧室门。'))
descs.insert(0,desc)
js=js[:match.start(1)]+json.dumps(descs,ensure_ascii=False)+js[match.end(1):];p.write_text(js)
p=stage/'static/index.html';html=p.read_text();html=re.sub(r'src="/app.js(?:\?[^" ]*)?"','src="/app.js?v=door-task-20260913"',html);p.write_text(html)
from pathlib import Path
import json
p=stage/'server.py';s=p.read_text();assert 'H(?:0[1-9]|1[0-3])' in s;s=s.replace('H(?:0[1-9]|1[0-3])','H(?:0[1-9]|1[0-3]|15)');p.write_text(s)
p=stage/'tests/test_taxonomy.py';text=p.read_text().replace(",224)",",225)");p.write_text(text)
p=stage/'tests/test_configuration_release.py';s=p.read_text().replace('self.assertEqual(len(byid),256)','self.assertEqual(len(byid),257)');p.write_text(s)
p=stage/'tests/test_semantic_compatibility.py';s=p.read_text().replace("self.assertEqual(TAXONOMY['version'], 'user-2026-09-12-semantic-compatibility')","self.assertEqual(TAXONOMY['version'], 'user-2026-09-13-visibility')");p.write_text(s)
p=stage/'review-scene-descriptions.json';data=json.loads(p.read_text());data['scenes'].insert(0,desc);p.write_text(json.dumps(data,ensure_ascii=False,indent=2))

shutil.copy2(w/'scripts/test_indoor_door.py',stage/'tests/test_indoor_door.py')
# Keep canonical bilingual metadata consistent with the public manifest.
p=stage/'rubrics.bilingual.json';rub=read(p)
rub['H15']=t['rubrics_i18n'];rub['H09']=vase['rubrics_i18n']
p.write_text(json.dumps(rub,ensure_ascii=False,indent=2))
(stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(stage/'candidate-runtime.json').write_text(json.dumps(runtime,indent=2));(stage/'candidate-runtime.json').chmod(0o600)
for n,h in source_hashes.items():assert sha(source/n)==h,n
for n,h in state_hashes.items():assert sha(state/n)==h,n
proof=dict(source_release=str(source),stage=str(stage),entries=len(manifest['tasks']),changed_cases=['H09'],added_cases=['H15'],state_hashes=state_hashes,source_hashes=source_hashes,binary_sha256=bh)
(out/'proof.json').write_text(json.dumps(proof,indent=2));print(stage,flush=True)

