"""Append Ancient Chinese City to the current live catalog and runtime profiles."""
from pathlib import Path
import hashlib,json,os
from ancient_entries import build_ancient_entries
r=Path(__file__).resolve().parent;root=Path('/home/ubuntu/unreal-auditor');state=root/'review-service/state'
def read(p):return json.loads(p.read_text())
original=(state/'tasks.json').read_bytes();manifest=json.loads(original)
existing=[t for t in manifest['tasks'] if t.get('family')!='ancient']
entries,profiles=build_ancient_entries(root)
manifest['tasks']=existing+entries
assert len({t['id'] for t in manifest['tasks']})==len(manifest['tasks'])
config=read(state/'runtime.json');config.setdefault('launch_profiles',{}).update(profiles)
config['manifest']=str(state/'tasks.json')
private=r/'prepared-state';private.mkdir(mode=0o700,exist_ok=True)
(r/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
for name,value in [('runtime.json',config),('service-env.json',read(state/'service-env.json'))]:
 p=private/name;p.write_text(json.dumps(value,indent=2));p.chmod(0o600)
(private/'source-catalog.sha256').write_text(hashlib.sha256(original).hexdigest())
print(json.dumps(dict(existing=len(existing),ancient=len(entries),total=len(manifest['tasks']))))

