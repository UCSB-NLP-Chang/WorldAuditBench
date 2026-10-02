"""Version the changed map and task descriptions; preserve the current live UI."""
from pathlib import Path
import subprocess,json,hashlib,shutil,re
root=Path('/home/ubuntu/unreal-auditor');work=root/'rural-workspace';service=root/'review-service';state=service/'state'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip())
stage=service/'staging/rural-variety-20260912-v1';assert not stage.exists()
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','isolated-state'))
manifest=read(state/'tasks.json');runtime=read(state/'runtime.json');specs={t['id']:t for t in read(work/'dist/rural-linux-v5/tasks.json')['tasks']}
binary=work/'dist/rural-linux-v5/Linux/RuralAustralia/Binaries/Linux/RuralAustralia'
mapsha=sha(work/'project/Content/Auditor/RuralAustralia/RoadBend.umap');changed=[]
steps={
 'R02':('靠近路边倒木，从侧面观察两根木头交叉的位置。','Approach the roadside logs and inspect their intersection from the side.'),
 'R03':('比较路边两块同款岩石的尺寸，从侧面观察。','Compare the dimensions of the two matching roadside rocks from the side.'),
 'R04':('朝出生点前方的铁丝网走，在两根立柱中间尝试直接穿过去。','Walk toward the wire fence in front of the spawn point and try to pass between the two posts.'),
 'R05':('抬头将路边树冠放在视野中央，再把视角向旁边偏转。','Look up to center the roadside tree canopy, then turn the view to the side.')}
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
old=read(state/'tasks.json');assert len(manifest['tasks'])==len(old['tasks'])==246
assert [t for t in manifest['tasks'] if t['id'] not in changed]==[t for t in old['tasks'] if t['id'] not in changed]
for name in ('Roadside','Canyon'):assert sha(work/('project/Content/Auditor/RuralAustralia/'+name+'.umap'))==sha(work/('out/variety-v4/source-backup/'+name+'.umap'))
p=stage/'static/app.js';s=p.read_text();m=re.search(r'const sceneDescriptions=(\[.*?\]);',s);assert m
descriptions=json.loads(m.group(1))
description={'zh':'这是澳大利亚乡间的一段林间弯道，两侧有铁丝网围栏、树木、倒木、岩石和袋鼠警示牌。你可以步行探索，检查路边物体的外观和碰撞，并改变观察角度；此区域没有 E 键交互。','en':'An Australian bush road bend with wire fences, trees, fallen logs, rocks and wildlife signs. Explore on foot, inspect roadside objects and their collision, and change your viewpoint; this area has no E-key interactions.'}
for d in descriptions:
 if d['map']=='/Game/Auditor/RuralAustralia/RoadBend':d['description']=description
s=s[:m.start(1)]+json.dumps(descriptions,ensure_ascii=False,separators=(',',':'))+s[m.end(1):];p.write_text(s)
for name,data in [('tasks.json',manifest),('candidate-runtime.json',runtime)]:
 p=stage/name;p.write_text(json.dumps(data,ensure_ascii=False,indent=2));p.chmod(0o600)
proof=dict(source_release=str(source),stage=str(stage),source_files={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts},source_state_sha256={n:sha(state/n) for n in ('tasks.json','runtime.json','service-env.json')},revised=changed,changed_scenarios=list(steps),map_sha256=mapsha,build=str(binary),description=description)
(work/'out/variety-release-candidate.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps({k:proof[k] for k in ('stage','revised','changed_scenarios','map_sha256')}))
