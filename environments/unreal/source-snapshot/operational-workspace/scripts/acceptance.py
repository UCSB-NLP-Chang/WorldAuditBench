from pathlib import Path
import json,hashlib
r=Path('/home/ubuntu/unreal-auditor');o=r/'operational-workspace/out';a=r/'ancient-workspace';i=r/'industrial-workspace'
read=lambda p:json.loads(p.read_text())
checks={}
for name,p,key,value,count in [
 ('ancient_native',a/'out/operational-v1/native/report.json','ok',True,34),
 ('ancient_restore',a/'out/operational-v1/restoration/report.json','ok',True,24),
 ('ancient_render',a/'out/operational-v1/renders.json','ok',True,2),
 ('industrial_native',i/'dist/industrial-operational-20260913-v1/behavior-tests/results.json','result','PASS',21),
 ('industrial_routes',i/'dist/industrial-operational-20260913-v1/runtime-verification.json','result','PASS',6),
 ('industrial_pairs',i/'out/operational/render-report.json','ok',True,4),
 ('industrial_render_restore',i/'out/operational/full-render/results.json','result','PASS',21)]:
 x=read(p);assert len(x)==count and all(t[key]==value for t in x),name;checks[name]=count
proof=read(o/'proof.json');stage=Path(proof['stage']);m=read(stage/'tasks.json')
for family,project in [('industrial','FactoryEnvironmentCollect'),('ancient','AncientChineseCity')]:
 w=r/(family+'-workspace');b=w/('dist/'+family+'-operational-20260913-v1/Linux/'+project+'/Binaries/Linux/'+project)
 h=hashlib.sha256()
 with b.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 assert all(t['build_sha256']==h.hexdigest() for t in m['tasks'] if t.get('family')==family)
checks.update(result='PASS',changed_cases=['A17','IB03'],added_cases=['I20','I21'],visual_inspection=True)
(o/'acceptance.json').write_text(json.dumps(checks,indent=2));print(checks)

