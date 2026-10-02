"""Vendor four existing licensed meshes with their verified dependency closures."""
import unreal,json,hashlib,shutil
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');dst=r/'project/Content';out=r/'out/era-v1'
roots={n:(dst/n).resolve().parent for n in ['GameReady3D','Meshes','Materials','Textures']}
assert all((dst/n).is_symlink() for n in roots)
meshes=['/Game/GameReady3D/AtmosphericFarmhouse/StaticMesh/Props/SM_Computer','/Game/GameReady3D/AtmosphericFarmhouse/StaticMesh/Props/SM_Solarpanel','/Game/Meshes/SM_VideoCamera_01','/Game/Meshes/SM_AirConditioner01']
reg=unreal.AssetRegistryHelpers.get_asset_registry();reg.search_all_assets(True)
options=unreal.AssetRegistryDependencyOptions(include_soft_package_references=True,include_hard_package_references=True)
pending=list(meshes);seen=set();files=[]
while pending:
 p=str(pending.pop())
 if p in seen or not p.startswith('/Game/'):continue
 seen.add(p);pending.extend(reg.get_dependencies(p,options))
 rel=p[6:];root=roots[rel.split('/')[0]]
 assert (root/(rel+'.uasset')).is_file(),p
 for ext in ['.uasset','.uexp','.ubulk']:
  src=root/(rel+ext)
  if src.is_file():files.append((src,rel+ext,hashlib.sha256(src.read_bytes()).hexdigest()))
for n in roots:(dst/n).unlink()
for src,rel,h in files:
 for target in [dst,r/'source-additions/era-v1/Content']:
  to=target/rel;assert not to.exists();to.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,to);assert hashlib.sha256(to.read_bytes()).hexdigest()==h
(out/'import.json').write_text(json.dumps(dict(meshes=meshes,files=[dict(source=str(p),path=n,sha256=h,bytes=p.stat().st_size) for p,n,h in files]),indent=2))
print('ERA_IMPORTED',len(files),sum(p.stat().st_size for p,n,h in files),flush=True)
