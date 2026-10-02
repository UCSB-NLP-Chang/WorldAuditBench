"""Prepare current-source review release; no live state changes."""
from pathlib import Path
import json,shutil,subprocess,hashlib,re,copy
root=Path('/home/ubuntu/unreal-auditor');work=root/'configuration-workspace';service=root/'review-service';state=service/'state';cfg=json.loads((work/'projects.json').read_text())
def read(p):return json.loads(p.read_text())
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=work/'configuration-tasks-20260913-v1';assert not stage.exists()
proof={'source_release':str(source),'stage':str(stage),'state_hashes':{n:sha(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},'source_hashes':{str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts}}
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__'));old=read(state/'tasks.json');manifest=copy.deepcopy(old);runtime=read(state/'runtime.json');oldprofiles=copy.deepcopy(runtime['launch_profiles']);byid={t['id']:t for t in old['tasks']};retired=['S17','U039'];manifest['tasks']=[t for t in manifest['tasks'] if t['id'] not in retired]
write(stage/'configuration-backup-cases.json',{'status':'backup_candidates','reason':'Ordinary temporary placement is insufficient evidence of a configuration bug.','tasks':[byid[k] for k in retired]})
changed={'subway':'S18','indoor':'H13','ancient':'A18','medieval':'MV17'};envnames={'subway':'subway','indoor':'residential-house','ancient':'ancient-chinese-city','industrial':'industrial-factory','medieval':'medieval-village'};recipes={};builds={}
for family,envname in envnames.items():
 s=cfg[family];w=Path(s['workspace']);catalog=read(w/'environments'/envname/'tasks.json');recipes[family]={t['id']:t for t in catalog['tasks']};regs={r['id']:r for r in read(w/'environments'/envname/'regions.json')['regions']};build=read(work/'out'/('build-'+family+'.json'));assert build['status']=='PASS';assert sha(Path(build['binary']))==build['binary_sha256'];builds[family]=build
 for t in manifest['tasks']:
  if t.get('family')!=family:continue
  t['revision']+=1;t['build_sha256']=build['binary_sha256']
  if t['id']==changed.get(family):
   recipe=recipes[family][t['id']];reg=regs[recipe['region']];t.update(title=recipe['title'],map=reg['map']+'?Task='+t['id'],subcategory='S2',rubrics_i18n=recipe['rubrics_i18n'],environment={'subway':'Subway','indoor':'Indoor','ancient':'Ancient Chinese City','industrial':'Industrial','medieval':'Medieval Village'}[family]+' / '+reg['name'],taxonomy_label='场景语义一致性 · 配置不合理')
   t['rubrics']=t['rubrics_i18n']['en']['criteria']+'\n'+t['rubrics_i18n']['zh']['criteria'];t.pop('taxonomy',None)
  map=t['map'].split('?')[0];t['sha256']=sha(Path(s['project']).parent/'Content'/(map[6:]+'.umap'))
  template=copy.deepcopy(oldprofiles[byid[t['id']]['map']]);template.update(binary=build['binary'],build_sha256=build['binary_sha256']);runtime['launch_profiles'][t['map']]=template
# New assembly task uses the validated family launch settings.
t=copy.deepcopy(byid['I06']);r=recipes['industrial']['I19'];map=r['map'];build=builds['industrial'];t.update(id='I19',case_id='I19',case_path='/?case=I19',revision=1,map=map+'?Task=I19',sha256=sha(Path(cfg['industrial']['project']).parent/'Content'/(map[6:]+'.umap')),build_sha256=build['binary_sha256'],title=r['title'],subcategory='S2',rubrics_i18n=r['rubrics_i18n']);t['rubrics']=r['rubrics_i18n']['en']['criteria']+'\n'+r['rubrics_i18n']['zh']['criteria'];manifest['tasks'].append(t);runtime['launch_profiles'][t['map']]=copy.deepcopy(runtime['launch_profiles'][next(x['map'] for x in manifest['tasks'] if x['id']=='I06')])
# New Urban map has neutral canonical case path; legacy Urban tasks keep their binary.
build=read(work/'out/build-urban.json');builds['urban']=build;assert build['status']=='PASS' and sha(Path(build['binary']))==build['binary_sha256'];map='/Game/Auditor/Migration/UE561/U046/R01/TaskMap_Candidate02';assert map in build['maps']
rubrics={'zh':{'criteria':'街边邮箱上下倒装，箱门和投信口的方向颠倒。','expected':'正常情况下，邮箱应保持正向安装，投信口和箱门方向正确。','steps':'走到店面街区北侧的邮箱旁，从正面和侧面查看箱门、投信口和底部。'},'en':{'criteria':'The street mailbox is installed upside down, inverting its door and posting opening.','expected':'The mailbox should be installed upright, with its door and posting opening correctly oriented.','steps':'Approach the mailbox on the north side of the shopfront and inspect its front, side and base.'}}
t=dict(id='U046',revision=1,case_id='U046',case_path='/?case=U046',case_type='bug',family='urban',environment='urban-city / Shopfront / 店面街区',scene_id='shopfront',scene_i18n={'en':'Shopfront','zh':'店面街区'},review_mode='informed_internal_review',title='街边邮箱上下倒装',subcategory='S2',map=map,sha256=sha(Path(cfg['urban']['project']).parent/'Content'/(map[6:]+'.umap')),build_sha256=build['binary_sha256'],runtime_switch=False,rubrics_i18n=rubrics,rubrics=rubrics['en']['criteria']+'\n'+rubrics['zh']['criteria']);manifest['tasks'].append(t);profile=copy.deepcopy(oldprofiles[byid['U039']['map']]);profile.update(binary=build['binary'],build_sha256=build['binary_sha256']);runtime['launch_profiles'][map]=profile
assert len(manifest['tasks'])==len(old['tasks'])==253
assert [t for t in manifest['tasks'] if t.get('family') in ['rural'] or t.get('runtime_kind')=='browser']==[t for t in old['tasks'] if t.get('family') in ['rural'] or t.get('runtime_kind')=='browser']
assert runtime['capacity']==3
runtime['launch_profiles']={t['map']:runtime['launch_profiles'][t['map']] for t in manifest['tasks'] if t.get('runtime_kind')!='browser'}
write(stage/'industrial-runtime-profiles.json',{t['map']:runtime['launch_profiles'][t['map']] for t in manifest['tasks'] if t.get('family')=='industrial'})
write(stage/'tasks.json',manifest);write(stage/'candidate-runtime.json',runtime);(stage/'candidate-runtime.json').chmod(0o600)
# Scene copy remains shared and concise; adjust memberships for moved/new cases.
app=stage/'static/app.js';text=app.read_text();match=re.search(r'^const sceneDescriptions=(.*);$',text,re.M);assert match;scenes=json.loads(match[1]);moves={'H13':'/Game/Auditor/Regions/KitchenDining','A18':'/Game/Auditor/AncientCity/Courtyard','I19':'/Game/Auditor/Industrial/AssemblyHall','U046':next(s['map'] for s in scenes if 'U039' in s['task_ids'])}
for scene in scenes:scene['task_ids']=[i for i in scene['task_ids'] if i not in set(moves)|set(retired)]
for tid,map in moves.items():
 scene=next(s for s in scenes if s['map']==map);scene['task_ids'].append(tid)
text=re.sub(r'^const sceneDescriptions=.*;$',lambda m:'const sceneDescriptions='+json.dumps(scenes,ensure_ascii=False)+';',text,count=1,flags=re.M)
match=re.search(r'const urbanTaskNumbers=Object.freeze\((.*?)\);',text);assert match;numbers=json.loads(match[1]);numbers['U046']=19;text=text[:match.start(1)]+json.dumps(numbers,separators=(',',':'))+text[match.end(1):];app.write_text(text)
for filename in ['review-scene-descriptions.json']:
 d=read(stage/filename);d['scenes']=scenes;write(stage/filename,d)
d=read(stage/'urban-public-ids.json');d['U046']='unreal_urban_bug_19';write(stage/'urban-public-ids.json',d)
p=stage/'server.py';s=p.read_text();assert s.count('I(?:0[1-9]|1[0-8])')==1;s=s.replace('I(?:0[1-9]|1[0-8])','I(?:0[1-9]|1[0-9])');p.write_text(s)
# Update assertions for the agreed catalog, retaining validation of wrong IDs/maps.
p=stage/'tests/test_industrial.py';s=p.read_text().replace('len(self.entries), 21','len(self.entries), 22').replace('range(1, 19)','range(1, 20)').replace('tasks=18, baselines=3','tasks=19, baselines=3').replace("{'id': 'I19'}","{'id': 'I20'}");p.write_text(s)
p=stage/'tests/test_taxonomy.py';s=p.read_text().replace("s.tasks['S17']","s.tasks['I19']");p.write_text(s)
p=stage/'tests/test_semantic_compatibility.py';s=p.read_text().replace("'U039', 'S18'","'U046', 'S18'").replace("'S17', 'S19'","'I19', 'S19'");# preserve the legacy override-specific test list
s=s.replace("'MV17', 'I19', 'S19', 'U039'","'MV17', 'S17', 'S19', 'U039'");p.write_text(s)
proof.update(builds=builds,retired=retired,changed=changed,new=['U046','I19']);write(work/'out/review-proof.json',proof);print(json.dumps({'stage':str(stage),'entries':len(manifest['tasks']),'changed':changed,'retired':retired,'new':['U046','I19']}))
