from pathlib import Path
import json,hashlib,shutil,tempfile,sys
r=Path('/home/ubuntu/unreal-auditor');w=r/'ancient-workspace';svc=r/'review-service';state=svc/'state'
stage=svc/'staging/ancient-push-independent-doors-20260912';assert not stage.exists()
shutil.copytree(svc/'releases/scene-semantics-context-20260912',stage,ignore=shutil.ignore_patterns('__pycache__'))
binary=w/'dist/ancient-push-independent-doors-20260912/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
build=sha(binary);paks={p.name:sha(p) for p in (binary.parents[2]/'Content/Paks').iterdir() if p.is_file()}
settings=json.loads((w/'environments/ancient-chinese-city/streaming-settings.json').read_text());layout=json.loads((w/'environments/ancient-chinese-city/npc-layout.json').read_text())
manifest=json.loads((state/'tasks.json').read_text());runtime=json.loads((state/'runtime.json').read_text())
for t in manifest['tasks']:
 if t.get('family')!='ancient':continue
 t['revision']+=1;t['build_sha256']=build
 t['sha256']=hashlib.sha256(json.dumps(dict(previous=t['sha256'],revision=t['revision'],build=build,paks=paks,settings=settings,npc_layout=layout),sort_keys=True).encode()).hexdigest()
 p=runtime['launch_profiles'][t['map']];assert p['game_args']==settings['game_args'];p['binary']=str(binary);p['build_sha256']=build

# Project current interaction rubrics and concise shared scene descriptions.
catalog={t['id']:t for t in json.loads((w/'environments/ancient-chinese-city/tasks.json').read_text())['tasks']}
for t in manifest['tasks']:
 if t.get('family')=='ancient' and t['id'] in ('A09','A17','A19'):
  authored=catalog[t['id']];t['title']=authored['title'];t['rubrics_i18n']=authored['rubrics_i18n'];t['rubrics']=authored['rubrics_i18n']['en']['criteria']+'\n'+authored['rubrics_i18n']['zh']['criteria']
scenes=json.loads((w/'environments/ancient-chinese-city/scene-descriptions.json').read_text())
(stage/'ancient-scene-descriptions.json').write_text(json.dumps(scenes,ensure_ascii=False,indent=2))
allscenes=json.loads((stage/'review-scene-descriptions.json').read_text());by_map={s['map']:s for s in scenes['scenes']}
allscenes['scenes']=[by_map.get(s['map'],s) for s in allscenes['scenes']]
(stage/'review-scene-descriptions.json').write_text(json.dumps(allscenes,ensure_ascii=False,indent=2))
import re
p=stage/'static/app.js';text=p.read_text();text,n=re.subn(r'^const sceneDescriptions=.*?;$','const sceneDescriptions='+json.dumps(allscenes['scenes'],ensure_ascii=False,separators=(',',':'))+';',text,count=1,flags=re.M);assert n==1;p.write_text(text)
(stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(stage/'candidate-runtime.json').write_text(json.dumps(runtime,ensure_ascii=False,indent=2));(stage/'candidate-runtime.json').chmod(0o600)
proof=dict(binary=str(binary),build_sha256=build,pak_sha256=paks,settings=settings,npc_layout=layout,source_state_sha256={n:sha(state/n) for n in ['tasks.json','runtime.json','service-env.json']},entries=len(manifest['tasks']),ancient_revision=5)
(stage/'basket-provenance.json').write_text(json.dumps(proof,indent=2))
sys.path.insert(0,str(stage));import server
with tempfile.TemporaryDirectory() as temp:s=server.Store(Path(temp)/'db',manifest);s.db.close()


source=(svc/'staging/ancient-sparse-npcs-20260912/publish_npcs.py').read_text()
source=source.replace('ancient-sparse-npcs-20260912','ancient-push-independent-doors-20260912').replace('npc-provenance.json','basket-provenance.json').replace("'ancient-sparse-npcs-'","'ancient-push-independent-doors-'").replace('zz-ancient-sparse-npcs.conf','zzzzz-ancient-push-independent-doors.conf').replace('ancient_revision=3','ancient_revision=5')
(stage/'publish_interactions.py').write_text(source)
print(json.dumps(dict(status='PREPARED',stage=str(stage),build=build,entries=len(manifest['tasks']),ancient_revision=5)))
