from pathlib import Path
import json,hashlib,subprocess,shutil,copy,re,sqlite3,sys,importlib.util
root=Path('/home/ubuntu/unreal-auditor');w=root/'operational-workspace';out=w/'out';out.mkdir(parents=True,exist_ok=True);svc=root/'review-service';state=svc/'state'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=w/'operational-states-20260913-v1';assert not stage.exists()
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','prepared-state'));stage.chmod(0o700)
manifest=read(state/'tasks.json');before=copy.deepcopy(manifest);runtime=read(state/'runtime.json');assert len([t for t in manifest['tasks'] if t.get('family')=='industrial'])==22
keys=('revision','sha256','build_sha256')
for family,folder,project in [('ancient','ancient-chinese-city','AncientChineseCity'),('industrial','industrial-factory','FactoryEnvironmentCollect')]:
 wr=root/(family+'-workspace');env=wr/'environments'/folder;authored={t['id']:t for t in read(env/'tasks.json')['tasks']}
 binary=wr/('dist/'+family+'-operational-20260913-v1/Linux/'+project+'/Binaries/Linux/'+project);assert binary.is_file();bh=sha(binary)
 ours=[t for t in manifest['tasks'] if t.get('family')==family]
 if family=='industrial':
  template=next(t for t in ours if t['id']=='I18')
  for tid in ['I20','I21']:
   e=copy.deepcopy(template);e.pop('review_compatible_versions',None);e.update(id=tid,case_id=tid,case_path='/?case='+tid,revision=1,map=authored[tid]['map']+'?Task='+tid,subcategory='T3')
   manifest['tasks'].append(e);ours.append(e)
 for e in ours:
  tid=e['id'];changed=tid in ['A17','I20','I21']
  old={k:e[k] for k in keys}
  if changed:
   t=authored[tid]
   e.pop('review_compatible_versions',None)
   e.update(title=t['title'],rubrics_i18n=t['rubrics_i18n'],rubrics='\n'.join(' '.join(t['rubrics_i18n'][l][k] for k in ['criteria','expected']) for l in ['en','zh']))
   if tid=='A17':e['revision']+=1
  else:
   aliases=e.setdefault('review_compatible_versions',[])
   if old not in aliases:aliases.append(old)
   if tid=='IB03':
    e.pop('review_compatible_versions',None);e['revision']+=1
  e['build_sha256']=bh;e['sha256']=sha(wr/'project/Content'/(e['map'].split('?')[0][6:]+'.umap'))
  p=copy.deepcopy(runtime['launch_profiles'].get(e['map'],runtime['launch_profiles'][template['map']] if family=='industrial' else None));assert p
  p.update(binary=str(binary),build_sha256=bh);runtime['launch_profiles'][e['map']]=p
# Admit only the two newly authored Industrial task IDs.
p=stage/'server.py';s=p.read_text();needle='|I(?:0[1-9]|1[0-9])|';assert needle in s;p.write_text(s.replace(needle,'|I(?:0[1-9]|1[0-9]|2[01])|'))
p=stage/'tests/test_industrial.py';s=p.read_text();assert "{'id': 'I20'}" in s;p.write_text(s.replace("{'id': 'I20'}","{'id': 'I22'}").replace('len(self.entries), 22','len(self.entries), 24').replace('range(1, 20)','range(1, 22)').replace('tasks=19, baselines=3','tasks=21, baselines=3'))
p=stage/'tests/test_configuration_release.py';p.write_text(p.read_text().replace('len(byid),'+str(len(before['tasks'])), 'len(byid),'+str(len(manifest['tasks']))))
p=stage/'tests/test_taxonomy.py';s=p.read_text();oldbugs=sum(t.get('case_type')=='bug' for t in before['tasks']);p.write_text(s.replace('),'+str(oldbugs)+')', '),'+str(oldbugs+2)+')'))
# Keep one shared scene introduction for all control-room tasks.
for name in ['review-scene-descriptions.json','industrial-scene-descriptions.json']:
 p=stage/name;doc=read(p);scenes=doc.get('scenes',[]) if isinstance(doc,dict) else doc
 for scene in scenes:
  if scene['map']=='/Game/Auditor/Industrial/ControlRoom':
   scene['task_ids']+= [tid for tid in ['I20','I21'] if tid not in scene['task_ids']]
   scene['description']={'zh':'俯瞰工厂车间的控制室，设有照明、监控控制台、座椅和茶几。','en':'A control room overlooking the factory floor, with lighting, monitoring consoles, chairs and a coffee table.'}
 p.write_text(json.dumps(doc,ensure_ascii=False,indent=2))
scenes=read(stage/'review-scene-descriptions.json')['scenes'];p=stage/'static/app.js';s=p.read_text();s,n=re.subn(r'const sceneDescriptions=\[.*?\];',lambda m:'const sceneDescriptions='+json.dumps(scenes,ensure_ascii=False)+';',s,count=1);assert n==1;p.write_text(s)
p=stage/'concise-ancient-rubrics.json';x=read(p);x['A17']=next(t for t in manifest['tasks'] if t['id']=='A17')['rubrics_i18n'];p.write_text(json.dumps(x,ensure_ascii=False,indent=2))
(stage/'industrial-runtime-profiles.json').write_text(json.dumps({k:v for k,v in runtime['launch_profiles'].items() if v.get('family')=='industrial'},indent=2))
(stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(stage/'candidate-runtime.json').write_text(json.dumps(runtime,indent=2));(stage/'candidate-runtime.json').chmod(0o600)
proof=dict(source_release=str(source),stage=str(stage),entries=len(manifest['tasks']),changed_cases=['A17','IB03'],added_cases=['I20','I21'],state_hashes={n:sha(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},source_hashes={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css') and '__pycache__' not in p.parts})
(out/'proof.json').write_text(json.dumps(proof,indent=2))
print(stage,flush=True)

