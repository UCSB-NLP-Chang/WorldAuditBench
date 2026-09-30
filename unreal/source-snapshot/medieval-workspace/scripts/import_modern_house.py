"""Copy only the licensed small apartment building's dependencies into this project."""
import unreal,json,hashlib,shutil
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');dst=r/'project/Content';link=dst/'NYCBuildingVolume2';assert link.is_symlink()
src=link.resolve().parent;o=r/'out/house-v3'
reg=unreal.AssetRegistryHelpers.get_asset_registry();reg.search_all_assets(True)
options=unreal.AssetRegistryDependencyOptions(include_soft_package_references=True,include_hard_package_references=True)
mesh='/Game/NYCBuildingVolume2/Static_Meshes/Buildings/SM_Building_G_V1';pending=[mesh];packages=set()
while pending:
 p=pending.pop()
 if p in packages or not p.startswith('/Game/'):continue
 packages.add(p);pending.extend(str(n) for n in reg.get_dependencies(p,options))
files=[]
for p in sorted(packages):
 f=src/(p[6:]+'.uasset');assert f.is_file(),p
 files.append((f,str(f.relative_to(src)),hashlib.sha256(f.read_bytes()).hexdigest()))
link.unlink()
backup=r/'source-additions/modern-house-20260912/Content'
for f,n,h in files:
 for root in (dst,backup):
  to=root/n;assert not to.exists();to.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,to);assert hashlib.sha256(to.read_bytes()).hexdigest()==h
(o/'house-import.json').write_text(json.dumps(dict(mesh=mesh,source=str(src),files=[dict(path=n,sha256=h) for f,n,h in files]),indent=2))
print('HOUSE_IMPORTED',len(files),flush=True)
