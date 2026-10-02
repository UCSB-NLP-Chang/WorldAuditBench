"""Read the licensed industrial truck assembly without saving its source project."""
import json
import hashlib
import shutil
from pathlib import Path
import unreal

out = Path('/home/ubuntu/unreal-auditor/medieval-workspace/out/vehicle-v2')
out.mkdir(exist_ok=True)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert level.load_level('/Temp/VehicleInspection') if unreal.EditorAssetLibrary.does_asset_exist('/Temp/VehicleInspection') else level.new_level('/Temp/VehicleInspection')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
cls = unreal.load_class(None, '/Game/Meshes/Truck/BP_Truck.BP_Truck_C')
assert cls
actor = actors.spawn_actor_from_class(cls, unreal.Vector())
rows = []
for c in actor.get_components_by_class(unreal.SceneComponent):
    row = dict(name=c.get_name(), type=c.get_class().get_name(), transform=str(c.get_world_transform()))
    if isinstance(c, unreal.StaticMeshComponent):
        row.update(mesh=c.static_mesh.get_path_name() if c.static_mesh else None,
                   visible=c.get_editor_property('visible'), hidden=c.get_editor_property('hidden_in_game'),
                   materials=[m.get_path_name() if m else None for m in c.get_materials()])
    if isinstance(c, unreal.SkeletalMeshComponent):
        row.update(mesh=c.get_editor_property('skeletal_mesh_asset').get_path_name(),
                   visible=c.get_editor_property('visible'), hidden=c.get_editor_property('hidden_in_game'),
                   materials=[m.get_path_name() if m else None for m in c.get_materials()])
    rows.append(row)
(out/'truck-components.json').write_text(json.dumps(rows, indent=2))
(out/'merge-api.txt').write_text(str(unreal.StaticMeshEditorSubsystem.merge_static_mesh_actors.__doc__)+'\n'+str(unreal.MergeStaticMeshActorsOptions.__doc__))
print('TRUCK_INSPECTION_PASS', json.dumps(rows), flush=True)
registry = unreal.AssetRegistryHelpers.get_asset_registry()
registry.search_all_assets(True)
options = unreal.AssetRegistryDependencyOptions(include_soft_package_references=True, include_hard_package_references=True)
pending = [p.split('.')[0] for row in rows for p in [row.get('mesh'), *row.get('materials', [])] if p]
packages = set()
while pending:
    package = pending.pop()
    if package in packages or not package.startswith('/Game/'):
        continue
    packages.add(package)
    pending.extend(str(p) for p in registry.get_dependencies(package, options))
src = Path('/home/ubuntu/unreal-auditor/industrial-workspace/project/Content')
dst = out.parent.parent/'project/Content'
copied = []
for package in sorted(packages):
    files = list((src / package[6:]).parent.glob(Path(package).name+'.u*'))
    assert files, package
    for file in files:
        target = dst / file.relative_to(src)
        sha = hashlib.sha256(file.read_bytes()).hexdigest()
        if target.exists():
            assert hashlib.sha256(target.read_bytes()).hexdigest() == sha, ('asset collision', str(target))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
        copied.append(dict(source=str(file), target=str(target), sha256=sha))
(out/'vehicle-import.json').write_text(json.dumps(copied, indent=2))
print('VEHICLE_IMPORT_PASS', len(copied), flush=True)
