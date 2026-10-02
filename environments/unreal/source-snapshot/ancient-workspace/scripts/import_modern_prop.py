import unreal,json,shutil
from pathlib import Path
registry=unreal.AssetRegistryHelpers.get_asset_registry();registry.search_all_assets(True)
options=unreal.AssetRegistryDependencyOptions(include_soft_package_references=True,include_hard_package_references=True,include_searchable_names=False,include_soft_management_references=False,include_hard_management_references=False)
source=Path('/home/ubuntu/unreal-auditor/projects/Subway/Content');target=Path('/home/ubuntu/unreal-auditor/ancient-workspace/project/Content');pending=['/Game/Subway_Station/Meshes/SM_Vending_Machine'];seen=set();files=[]
while pending:
 name=str(pending.pop())
 if name in seen or not name.startswith('/Game/'):continue
 seen.add(name)
 for dependency in registry.get_dependencies(name,options):pending.append(str(dependency))
 for ext in ['.uasset','.ubulk','.uexp']:
  src=source/(name[6:]+ext)
  if src.exists():
   dst=target/(name[6:]+ext);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);files.append({'path':str(dst.relative_to(target)),'bytes':src.stat().st_size})
assert any(f['path'].endswith('SM_Vending_Machine.uasset') for f in files)
Path('/home/ubuntu/unreal-auditor/ancient-workspace/out/modern-prop-import.json').write_text(json.dumps(files,indent=2))
print('MODERN_PROP_IMPORTED',len(files),sum(f['bytes'] for f in files))
