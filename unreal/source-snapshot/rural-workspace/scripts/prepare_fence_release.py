"""Version the changed map and task descriptions; preserve the current live UI."""
from pathlib import Path
import subprocess,json,hashlib,shutil,re
root=Path('/home/ubuntu/unreal-auditor');work=root/'rural-workspace';service=root/'review-service';state=service/'state'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip())
stage=service/'staging/rural-fence-fix-20260912-v1';assert not stage.exists()
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','isolated-state'))
manifest=read(state/'tasks.json');runtime=read(state/'runtime.json');specs={t['id']:t for t in read(work/'dist/rural-linux-v7/tasks.json')['tasks']}
binary=work/'dist/rural-linux-v7/Linux/RuralAustralia/Binaries/Linux/RuralAustralia'
mapsha=sha(work/'project/Content/Auditor/RuralAustralia/RoadBend.umap');changed=[]
steps={'R04':('在道路两侧任选一段铁丝网，避开树干和标牌等物体，从两根立柱之间直接走过去。','Try wire spans on either side of the road. Walk between posts, clear of trees and signs.'),'R03':('靠近警示牌，观察被竖向拉长的牌面和立柱，并与对面同款标牌比较。','Approach the wildlife sign, inspect its vertically stretched panel and post, and compare it with the matching sign across the road.')}
for t in manifest['tasks']:
 if t.get('family')!='rural':continue
 runtime['launch_profiles'][t['map']]['binary']=str(binary)
 assert runtime['launch_profiles'][t['map']]['build_sha256']==sha(binary)
 if t['map'].split('?')[0]!='/Game/Auditor/RuralAustralia/RoadBend':continue
 t['revision']+=1;t['sha256']=mapsha;changed.append(t['id'])
 if t['id'] not in steps:continue
 spec=specs[t['id']];t['title']=spec['title'];rub={}
 for lang,step in zip(('zh','en'),steps[t['id']]):
  full=spec['rubrics_i18n'][lang]['criteria'];sep='。' if lang=='zh' else '. ';first,_,last=full.partition(sep)
  rub[lang]=dict(criteria=first+('。' if lang=='zh' else '.'),expected=last.strip(),steps=step)
 t['rubrics_i18n']=rub;t['rubrics']='\n'.join(rub[l]['criteria']+' '+rub[l]['expected'] for l in ('en','zh'))
assert set(changed)=={'RB01','R01','R02','R03','R04','R05','R06'}
before_specs={t['id']:t for t in read(work/'dist/rural-linux-v5/tasks.json')['tasks']};assert [id for id in specs if specs[id]!=before_specs[id]]==['R03','R04']
old=read(state/'tasks.json');assert len(manifest['tasks'])==len(old['tasks'])==246
assert [t for t in manifest['tasks'] if t['id'] not in changed]==[t for t in old['tasks'] if t['id'] not in changed]
for name in ('Roadside','Canyon'):assert sha(work/('project/Content/Auditor/RuralAustralia/'+name+'.umap'))==sha(work/('out/variety-v4/source-backup/'+name+'.umap'))
for name,data in [('tasks.json',manifest),('candidate-runtime.json',runtime)]:
 p=stage/name;p.write_text(json.dumps(data,ensure_ascii=False,indent=2));p.chmod(0o600)
proof=dict(source_release=str(source),stage=str(stage),source_files={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts},source_state_sha256={n:sha(state/n) for n in ('tasks.json','runtime.json','service-env.json')},revised=changed,changed_scenarios=list(steps),map_sha256=mapsha,build=str(binary))
(work/'out/fence-release-candidate.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps({k:proof[k] for k in ('stage','revised','changed_scenarios','map_sha256')}))
