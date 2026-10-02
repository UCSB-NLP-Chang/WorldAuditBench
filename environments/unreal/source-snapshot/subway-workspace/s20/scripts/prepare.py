from pathlib import Path
import json,copy,shutil,hashlib,subprocess,re,importlib.util
r=Path('/home/ubuntu/unreal-auditor');w=r/'subway-workspace/s20';state=r/'review-service/state'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=w/'subway-s20-20260913-v2';assert not stage.exists()
proof=dict(source_release=str(source),stage=str(stage),state_hashes={n:sha(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},source_hashes={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__'));stage.chmod(0o700)
m=read(state/'tasks.json');old=copy.deepcopy(m);runtime=read(state/'runtime.json');b=read(w/'out/build.json');assert sha(Path(b['binary']))==b['binary_sha256']
recipe=next(t for t in read(r/'subway-workspace/environments/subway/tasks.json')['tasks'] if t['id']=='S20');assert not any(t['id']=='S20' for t in m['tasks'])
for t in m['tasks']:
 if t.get('family')!='subway':continue
 t['revision']+=1;t['build_sha256']=b['binary_sha256'];t['sha256']=sha(r/'projects/Subway/Content'/(t['map'].split('?')[0][6:]+'.umap'));runtime['launch_profiles'][t['map']].update(binary=b['binary'],build_sha256=b['binary_sha256'])
t=copy.deepcopy(next(x for x in m['tasks'] if x['id']=='S18'));t.update(id='S20',case_id='S20',case_path='/?case=S20',revision=1,map=recipe['map']+'?Task=S20',title=recipe['title'],subcategory='S1',taxonomy_label='场景语义一致性 · 场景不相容',rubrics_i18n=recipe['rubrics_i18n'],rubrics=recipe['rubrics_i18n']['en']['criteria']+'\n'+recipe['rubrics_i18n']['zh']['criteria']);m['tasks'].append(t);runtime['launch_profiles'][t['map']]=copy.deepcopy(runtime['launch_profiles'][recipe['map']+'?Task=S18'])
assert len(m['tasks'])==len(old['tasks'])+1
assert [t for t in m['tasks'] if t.get('family')!='subway']==[t for t in old['tasks'] if t.get('family')!='subway']
write(stage/'tasks.json',m);write(stage/'candidate-runtime.json',runtime);(stage/'candidate-runtime.json').chmod(0o600)
p=stage/'server.py';s=p.read_text();assert s.count('S(?:0[1-9]|1[0-9])')==1;p.write_text(s.replace('S(?:0[1-9]|1[0-9])','S(?:0[1-9]|1[0-9]|20)'))
p=stage/'static/app.js';s=p.read_text();match=re.search(r'^const sceneDescriptions=(.*);$',s,re.M);scenes=json.loads(match[1]);next(x for x in scenes if x['map']==recipe['map'])['task_ids'].append('S20');s=re.sub(r'^const sceneDescriptions=.*;$',lambda m:'const sceneDescriptions='+json.dumps(scenes,ensure_ascii=False)+';',s,count=1,flags=re.M);p.write_text(s);d=read(stage/'review-scene-descriptions.json');d['scenes']=scenes;write(stage/'review-scene-descriptions.json',d)
for name,a,b in [('test_semantic_compatibility.py',"'S1': set()","'S1': {'S20'}"),('test_configuration_release.py','len(byid),253','len(byid),254'),('test_taxonomy.py',',221)',',222)'),('test_taxonomy.py','[0, 10, 9]','[1, 10, 9]'),('test_unified.py',"('S20','/Game/Auditor/Subway/Platform?Task=S20')","('S21','/Game/Auditor/Subway/Platform?Task=S21')")]:
 p=stage/'tests'/name;s=p.read_text();assert a in s,(name,a);p.write_text(s.replace(a,b))
spec=importlib.util.spec_from_file_location('candidate_supervisor',stage/'runtime/mac_supervisor.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);c=copy.deepcopy(runtime);c.update(manifest=str(stage/'tasks.json'),state_dir=str(w/'out/runtime-validation'));sup=module.Supervisor(c);assert sup.capacity==3
write(w/'out/runtime-validation.json',dict(status='PASS',profiles=len(sup.allowed),capacity=sup.capacity));proof['entries']=len(m['tasks']);write(w/'out/review-proof.json',proof)
with (w/'out/service-tests.log').open('w') as f:subprocess.run(['python3','-m','unittest','discover','-s','tests','-q'],cwd=stage,stdout=f,stderr=subprocess.STDOUT,check=True)
print('CANDIDATE_PASS',len(m['tasks']),flush=True)
