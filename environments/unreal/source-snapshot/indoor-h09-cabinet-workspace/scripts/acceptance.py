from pathlib import Path
import json,hashlib
from PIL import Image,ImageStat,ImageChops
w=Path('/home/ubuntu/unreal-auditor/indoor-h09-cabinet-workspace');d=w.parent/'indoor-workspace/dist/indoor-h09-cabinet-20260913-v1';o=w/'out'
read=lambda p:json.loads(p.read_text());checks={}
for name,p,key,value,count in [('native',d/'behavior-tests/results.json','result','PASS',28),('renders',d/'rendered-review/results.json','result','PASS',2),('routes',d/'runtime-verification.json','result','PASS',6),('restoration',o/'restoration/report.json','ok',True,14)]:
 rows=read(p);assert len(rows)==count and all(x[key]==value for x in rows),name;checks[name]=count
# A rendered wall patch where the original vase casts a large unmistakable shadow.
a=Image.open(d/'rendered-review/H09-control.png').convert('L');b=Image.open(d/'rendered-review/H09-bug.png').convert('L');box=(870,235,930,290)
ca=ImageStat.Stat(a.crop(box)).mean[0];cb=ImageStat.Stat(b.crop(box)).mean[0];assert cb-ca>30,(ca,cb)
checks['wall_shadow_luminance']={'control':ca,'bug':cb}
proof=read(o/'proof.json');assert hashlib.sha256((d/'Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou').read_bytes()).hexdigest()==proof['binary_sha256']
assert all(x['result']=='PASS' for x in read(o/'initial-render/results.json'))
assert all(x['result']=='PASS' for x in read(o/'walk-results.json'))
checks['h10_initial_and_walk']='PASS'
checks.update(result='PASS',changed_cases=['H09'],added_cases=[],visual_inspection=True)
(o/'acceptance.json').write_text(json.dumps(checks,indent=2));print(checks)
