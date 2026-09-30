from pathlib import Path
import json,hashlib
r=Path('/home/ubuntu/unreal-auditor');w=r/'indoor-h03-pot-workspace';i=r/'indoor-workspace';d=i/'dist/indoor-h03-pot-20260913-v1';o=w/'out'
read=lambda p:json.loads(p.read_text())
checks={}
for name,p,key,value,count in [
 ('paired_native',d/'behavior-tests/results.json','result','PASS',26),
 ('rendered_pair',d/'rendered-review/results.json','result','PASS',2),
 ('routes',d/'runtime-verification.json','result','PASS',6),
 ('restoration',i/'out/h03-pot/restoration/report.json','ok',True,13)]:
 x=read(p);assert len(x)==count and all(t[key]==value for t in x),name;checks[name]=count
proof=read(o/'proof.json');binary=d/'Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou';assert hashlib.sha256(binary.read_bytes()).hexdigest()==proof['binary_sha256']
checks.update(result='PASS',changed_cases=['H03'],visual_inspection=True)
(o/'acceptance.json').write_text(json.dumps(checks,indent=2));print(checks)

