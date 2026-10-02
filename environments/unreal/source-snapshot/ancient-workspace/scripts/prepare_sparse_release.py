from pathlib import Path
import json,hashlib,shutil,tempfile,sys
r=Path('/home/ubuntu/unreal-auditor');w=r/'ancient-workspace';svc=r/'review-service';state=svc/'state'
stage=svc/'staging/ancient-sparse-npcs-20260912';assert not stage.exists()
shutil.copytree(svc/'releases/ancient-performance-20260912',stage,ignore=shutil.ignore_patterns('__pycache__'))
binary=w/'dist/ancient-sparse-npcs-20260912/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
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
(stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(stage/'candidate-runtime.json').write_text(json.dumps(runtime,ensure_ascii=False,indent=2));(stage/'candidate-runtime.json').chmod(0o600)
proof=dict(binary=str(binary),build_sha256=build,pak_sha256=paks,settings=settings,npc_layout=layout,source_state_sha256={n:sha(state/n) for n in ['tasks.json','runtime.json','service-env.json']},entries=len(manifest['tasks']),ancient_revision=3)
(stage/'npc-provenance.json').write_text(json.dumps(proof,indent=2))
sys.path.insert(0,str(stage));import server
with tempfile.TemporaryDirectory() as temp:s=server.Store(Path(temp)/'db',manifest);s.db.close()
source=(svc/'staging/ancient-performance-20260912/publish_performance.py').read_text()
source=source.replace('ancient-performance-20260912','ancient-sparse-npcs-20260912').replace('performance-provenance.json','npc-provenance.json').replace("'ancient-performance-'","'ancient-sparse-npcs-'").replace('99-ancient-performance.conf','zz-ancient-sparse-npcs.conf').replace('ancient_revision=2','ancient_revision=3')
(stage/'publish_npcs.py').write_text(source)
print(json.dumps(dict(status='PREPARED',stage=str(stage),build=build,entries=len(manifest['tasks']),ancient_revision=3)))
