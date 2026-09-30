import unreal,json,hashlib,shutil
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');src=Path('/home/ubuntu/unreal-auditor/indoor-workspace/project/Content');dst=Path('/home/ubuntu/unreal-auditor/ancient-workspace/project/Content');mesh='/Game/GameReady3D/AtmosphericFarmhouse/StaticMesh/Props/SM_SM_Can_V3';reg=unreal.AssetRegistryHelpers.get_asset_registry();reg.search_all_assets(True);opt=unreal.AssetRegistryDependencyOptions(include_soft_package_references=True,include_hard_package_references=True);pending=[mesh];seen=set();files=[]
while pending:
 p=str(pending.pop())
 if p in seen or not p.startswith('/Game/'):continue
 seen.add(p);pending.extend(reg.get_dependencies(p,opt));rel=p[6:];assert (src/(rel+'.uasset')).is_file(),p
 for ext in ['.uasset','.uexp','.ubulk']:
  a=src/(rel+ext);b=dst/(rel+ext)
  if not a.is_file():continue
  h=hashlib.sha256(a.read_bytes()).hexdigest()
  if b.exists():assert hashlib.sha256(b.read_bytes()).hexdigest()==h
  else:b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)
  files.append(dict(path=rel+ext,sha256=h))
(w/'out/import-a21-can.json').write_text(json.dumps(dict(mesh=mesh,files=files),indent=2))
