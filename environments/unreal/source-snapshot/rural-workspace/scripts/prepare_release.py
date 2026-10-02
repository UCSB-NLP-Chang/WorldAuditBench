"""Stage an additive review-service candidate from the current live release."""
from pathlib import Path
import subprocess,json,hashlib,shutil,datetime,re
root=Path('/home/ubuntu/unreal-auditor');work=root/'rural-workspace';service=root/'review-service';state=service/'state';env=work/'environments/rural-australia'
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_text())
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=service/'staging'/('rural-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S'));shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__'))
binary=work/'dist/rural-linux-v3/Linux/RuralAustralia/Binaries/Linux/RuralAustralia';sha=digest(binary);regions=read(env/'regions.json')['regions'];tasks=read(env/'tasks.json')['tasks'];manifest=read(state/'tasks.json');config=read(state/'runtime.json');old_ids={t['id'] for t in manifest['tasks']};assert not any(t.get('family')=='rural' for t in manifest['tasks'])
keys='M,N,P,F1,F2,F3,F4,Zero,One,Two,Three,Four,Five,Six,Seven,Eight,Nine,NumPadZero,NumPadOne,NumPadTwo,NumPadThree,NumPadFour,NumPadFive,NumPadSix,NumPadSeven,NumPadEight,NumPadNine,Tilde,Escape'
descriptions=[];entries=[]
texts={
 'road_bend':{'zh':'这是澳大利亚乡间的一段林间弯道，两侧有围栏、植被和袋鼠警示牌。你可以步行探索，靠近标牌并改变观察角度；此区域没有 E 键交互。','en':'An Australian bush road bend with fences, vegetation and wildlife signs. Explore on foot, approach the signs and change your viewpoint; this area has no E-key interactions.'},
 'roadside':{'zh':'这是一段澳大利亚乡间直路，路侧有标牌、树木、倒木和围栏。你可以沿路行走、接近路边物体或离开后返回观察；此区域没有 E 键交互。','en':'A straight Australian country road with signs, trees, fallen logs and fences. Walk along the road, approach roadside objects, or leave and return to inspect them; there are no E-key interactions.'},
 'canyon':{'zh':'这是一处澳大利亚溪谷林地，包含岩石、倒木、树木和溪水。你可以在小范围内步行探索，从不同距离和角度观察物体；此区域没有 E 键交互。','en':'An Australian creek canyon with rocks, fallen logs, trees and water. Explore the small area on foot and inspect objects from different distances and angles; there are no E-key interactions.'}}
for i,r in enumerate(regions,1):
 baseline=dict(id=f'RB{i:02}',case_type='baseline',title=r['name'],rubrics_i18n={'zh':{'criteria':'没有注入的异常。','expected':'场景应保持正常的外观、碰撞和状态。','steps':'步行探索并观察场景中的物体。'},'en':{'criteria':'No injected anomaly is present.','expected':'Appearance, collision and object state should behave normally.','steps':'Explore on foot and inspect the scene objects.'}})
 group=[baseline]+[t|{'case_type':'bug'} for t in tasks if t['region']==r['id']]
 descriptions.append(dict(map=r['map'],task_ids=[t['id'] for t in group],description=texts[r['id']]))
 for t in group:
  rub=json.loads(json.dumps(t['rubrics_i18n']))
  for lang in ['zh','en']:
   full=rub[lang]['criteria'];sep='。' if lang=='zh' else '. ';first,found,last=full.partition(sep)
   rub[lang].setdefault('expected',last.strip() if last.strip() else ('场景中的物体应正常呈现和响应。' if lang=='zh' else 'Objects should look and behave normally.'))
   if t['case_type']=='bug' and found and last.strip():rub[lang]['criteria']=first+('。' if lang=='zh' else '.')
   rub[lang].setdefault('steps',('步行接近目标，改变视角和距离；涉及返回的任务需背向目标走远再回来。' if lang=='zh' else 'Approach the target and vary viewpoint and distance; for revisit tasks, face away while leaving and then return.'))
  id=t['id'];assert id not in old_ids;m=r['map']+('?Task='+id if t['case_type']=='bug' else '')
  e=dict(id=id,revision=1,map=m,sha256=digest(work/'project/Content'/(r['map'][6:]+'.umap')),build_sha256=sha,runtime_switch=True,family='rural',environment='Rural Australia / '+r['name'],case_id=id,case_path='/?case='+id,case_type=t['case_type'],title=t['title'],rubrics_i18n=rub,rubrics='\n'.join(rub[l]['criteria']+' '+rub[l]['expected'] for l in ['en','zh']))
  if t.get('subcategory'):e['subcategory']=t['subcategory']
  entries.append(e);config['launch_profiles'][m]=dict(binary=str(binary),build_sha256=sha,key_filter=keys,family='rural',runtime_switch=True,game_args=['-vulkan','-sm5','-PixelStreamingWebRTCMaxFps=30','-ExecCmds=t.MaxFPS 30'])
assert len(entries)==21;manifest['tasks']+=entries
p=stage/'server.py';s=p.read_text();assert '|AB0[1-3]|' in s;s=s.replace('|AB0[1-3]|','|AB0[1-3]|RB0[1-3]|R(?:0[1-9]|1[0-8])|')
s=s.replace("            ancient=", "            rural={'RB01':'RoadBend','RB02':'Roadside','RB03':'Canyon'}\n            ancient=")
m=re.search(r"            (if|elif) t\['id'\] in ancient:allowed=",s);assert m
replacement="            "+m.group(1)+" t['id'] in rural:allowed=('/Game/Auditor/RuralAustralia/'+rural[t['id']],)\n            elif t['id'].startswith('R'):allowed=tuple('/Game/Auditor/RuralAustralia/'+region+'?Task='+t['id'] for region in ('RoadBend','Roadside','Canyon'))\n            elif t['id'] in ancient:allowed="
s=s[:m.start()]+replacement+s[m.end():];p.write_text(s)
p=stage/'static/app.js';s=p.read_text();s=s.replace("['ancient','industrial'].includes(task.family)","['ancient','industrial','rural'].includes(task.family)");s=s.replace("task.family==='ancient'","['ancient','rural'].includes(task.family)")
s=s.replace("ancient:'Ancient Chinese City'","ancient:'Ancient Chinese City',rural:'Rural Australia'")
s=re.sub(r"for\(const key of (\['subway',[^\]]+\])\)",lambda m:"for(const key of "+m.group(1)[:-1]+",'rural'])",s).replace('urban:2,ancient:3','urban:2,ancient:3,rural:5')
s=s.replace("let match;", "let match;if((match=/^RB(\\d+)$/.exec(id)))return 'unreal_rural_baseline_'+match[1].padStart(2,'0');if((match=/^R(\\d+)$/.exec(id)))return 'unreal_rural_bug_'+match[1].padStart(2,'0');")

m=re.search(r'const sceneDescriptions=(\[.*?\]);',s);assert m;combined=json.loads(m.group(1))+descriptions;s=s[:m.start(1)]+json.dumps(combined,ensure_ascii=False,separators=(',',':'))+s[m.end(1):];p.write_text(s)
p=stage/'static/index.html';s=p.read_text();anchor='<option value="ancient">Ancient Chinese City</option>';assert anchor in s;s=s.replace(anchor,anchor+'<option value="rural">Rural Australia</option>');p.write_text(s)
p=stage/'tests/test_taxonomy.py';test=p.read_text()
taxonomy=read(stage/'taxonomy.json');codes={key for c in taxonomy['categories'] for sub in c['subcategories'] for key in [sub['code'],sub['id']]}
normalise={key:sub['code'] for c in taxonomy['categories'] for sub in c['subcategories'] for key in [sub['code'],sub['id']]}
lookup=lambda t:normalise.get(taxonomy.get('task_overrides',{}).get(t['id'],t.get('subcategory')))
bugs=sum(t.get('case_type')!='baseline' and lookup(t) in codes for t in manifest['tasks'])
test=re.sub(r"(self\.assertEqual\(sum\(sub\['tasks'\] for sub in subs\),)\d+",lambda m:m.group(1)+str(bugs),test)
test=re.sub(r"(self\.assertEqual\(sum\(c\['tasks'\] for c in d\['taxonomy'\]\['categories'\]\),)\d+",lambda m:m.group(1)+str(bugs),test);test=re.sub(r"(self\.assertEqual\(\[sub\['tasks'\] for sub in subs\[-3:\]\],)\[[^\]]+\]",lambda m:m.group(1)+str([sum(t.get('case_type')!='baseline' and lookup(t)==code for t in manifest['tasks']) for code in ['S1','S2','S3']]),test);p.write_text(test)
(stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));p=stage/'candidate-runtime.json';p.write_text(json.dumps(config,indent=2));p.chmod(0o600)
(stage/'rural-scene-descriptions.json').write_text(json.dumps(descriptions,ensure_ascii=False,indent=2))
proof=dict(source_release=str(source),source_state_sha256={n:digest(state/n) for n in ['tasks.json','runtime.json','service-env.json']},build_sha256=sha,new_entries=21,preserved_entries=len(old_ids),stage=str(stage));(stage/'rural-provenance.json').write_text(json.dumps(proof,indent=2));(work/'out/release-candidate.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof))
