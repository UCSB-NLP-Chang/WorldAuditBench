"""Rebase the four Ancient era additions on the current live review release."""
import ast,copy,json,re,shutil,subprocess
from pathlib import Path
import hashlib
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 w=Path('/home/ubuntu/unreal-auditor/ancient-workspace');svc=w.parent/'review-service';state=svc/'state';env=w/'environments/ancient-chinese-city'
 proof=json.loads((w/'out/era-v1/acceptance.json').read_text());assert proof['result']=='PASS';binary=Path(proof['binary']);assert digest(binary)==proof['binary_sha256']
 source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=svc/'staging'/proof['release_name'];assert not stage.exists()
 shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','prepared-state'));stage.chmod(0o700)
 manifest=json.loads((state/'tasks.json').read_text());config=json.loads((state/'runtime.json').read_text());before=copy.deepcopy(manifest)
 ours={t['id']:t for t in manifest['tasks'] if t.get('family')=='ancient'};assert len(ours)==23 and 'A21' not in ours
 authored={t['id']:t for t in json.loads((env/'tasks.json').read_text())['tasks']};assert len(authored)==24
 regs={g['id']:g for g in json.loads((env/'regions.json').read_text())['regions']};template=copy.deepcopy(ours['A20']);profile_template=copy.deepcopy(config['launch_profiles'][template['map']])
 for id in ['A21','A22','A23','A24']:
  t=authored[id];e=copy.deepcopy(template);e.update(id=id,case_id=id,case_path='/?case='+id,revision=1,map=t['map']+'?Task='+id,title=t['title'],subcategory='S3',rubrics_i18n=t['rubrics_i18n'],rubrics='\n'.join(' '.join(t['rubrics_i18n'][l][k] for k in ['criteria','expected']) for l in ['en','zh']),environment='Ancient Chinese City / '+regs[t['region']]['name']);manifest['tasks'].append(e);ours[id]=e
 for e in ours.values():
  e['build_sha256']=proof['binary_sha256'];e['sha256']=digest(w/'project/Content'/(e['map'].split('?')[0][6:]+'.umap'))
  p=copy.deepcopy(config['launch_profiles'].get(e['map'],profile_template));p.update(binary=str(binary),build_sha256=proof['binary_sha256'],game_args=proof['game_args']);config['launch_profiles'][e['map']]=p
 (stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));(stage/'candidate-runtime.json').write_text(json.dumps(config,indent=2));(stage/'candidate-runtime.json').chmod(0o600)
 p=stage/'server.py';s=p.read_text();old=r'A(?:0[1-9]|1[0-9]|20)';assert s.count(old)==1;s=s.replace(old,r'A(?:0[1-9]|1[0-9]|2[0-4])');ast.parse(s);p.write_text(s)
 p=stage/'ancient_entries.py';s=p.read_text().replace('==23','==27').replace('ancient-linux-streaming2','ancient-era-20260913-v1');p.write_text(s)
 p=stage/'tests/test_ancient.py';s=p.read_text().replace('len(s.tasks),23','len(s.tasks),27').replace('tasks=20','tasks=24').replace("{'id':'A21'}","{'id':'A25'}").replace('ancient-linux-streaming2','ancient-era-20260913-v1');p.write_text(s)
 p=stage/'tests/test_taxonomy.py';s=p.read_text();assert s.count(',217)')==2;match=re.search(r"(subs\[-3:\]\],)(\[\d+, \d+, \d+\])",s);assert match;counts=ast.literal_eval(match[2]);assert counts[-1]==5;counts[-1]+=4;s=s[:match.start(2)]+str(counts)+s[match.end(2):];p.write_text(s.replace(',217)',',221)'))
 p=stage/'tests/test_semantic_compatibility.py'
 if p.exists():
  s=p.read_text();m=re.search(r"'S3': (\{[^}]+\})",s);assert m;members=ast.literal_eval(m[1]);members.update(['A21','A22','A23','A24']);p.write_text(s[:m.start(1)]+'{'+', '.join(repr(x) for x in sorted(members))+'}'+s[m.end(1):])
 scenes=json.loads((env/'scene-descriptions.json').read_text());new={s['map']:s for s in scenes['scenes']};allscenes=json.loads((stage/'review-scene-descriptions.json').read_text());effective=json.loads(re.search(r'const sceneDescriptions=(\[.*?\]);',(source/'static/app.js').read_text())[1]);allscenes['scenes']=[new.get(s['map'],s) for s in effective]
 (stage/'review-scene-descriptions.json').write_text(json.dumps(allscenes,ensure_ascii=False,indent=2));(stage/'ancient-scene-descriptions.json').write_text(json.dumps(scenes,ensure_ascii=False,indent=2))
 p=stage/'static/app.js';s=p.read_text();match=re.search(r'const sceneDescriptions=(\[.*?\]);',s);assert match;p.write_text(s[:match.start(1)]+json.dumps(allscenes['scenes'],ensure_ascii=False)+s[match.end(1):])
 provenance=dict(source_release=str(source),source_files_sha256={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css') and '__pycache__' not in p.parts},source_state_sha256={n:digest(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},binary_sha256=proof['binary_sha256'],previous_entries=len(before['tasks']),added_entries=4,changed_cases=[],acceptance=proof)
 (stage/'ancient-provenance.json').write_text(json.dumps(provenance,indent=2));print(stage,flush=True)
if __name__=='__main__':main()
