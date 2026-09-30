from pathlib import Path
import json,hashlib
r=Path('/home/ubuntu/unreal-auditor');w=r/'indoor-door-workspace';d=r/'indoor-workspace/dist/indoor-door-vase-20260913-v3';o=w/'out'
read=lambda p:json.loads(p.read_text())
checks={}
for name,p,key,value,count in [
 ('paired_native',d/'behavior-tests/results.json','result','PASS',28),
 ('rendered_pairs',d/'rendered-review/results.json','result','PASS',4),
 ('routes',d/'runtime-verification.json','result','PASS',6),
 ('restoration',o/'restoration-v3/report.json','ok',True,14)]:
 x=read(p);assert len(x)==count and all(t[key]==value for t in x),name;checks[name]=count
for name,path in [('door_player',o/'play-v3/report.json'),('vase_player',o/'vase-play/report.json'),('shadow_pixels',o/'shadow-pixels.json')]:
 assert read(path)['result']=='PASS',name;checks[name]='PASS'
proof=read(o/'proof.json');binary=d/'Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou';assert hashlib.sha256(binary.read_bytes()).hexdigest()==proof['binary_sha256']
checks.update(result='PASS',changed_cases=['H09'],added_cases=['H15'],visual_inspection=True)
(o/'acceptance.json').write_text(json.dumps(checks,indent=2));print(checks)
