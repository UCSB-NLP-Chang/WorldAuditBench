"""Validate the downloaded complete static vehicle and configure its parked case."""
import json
from pathlib import Path
import unreal

root = Path('/home/ubuntu/unreal-auditor/medieval-workspace')
out = root / 'out/props-v2'
path = '/Game/M3D_Old_Car/Meshes/SM_Old_Car'
mesh = unreal.load_asset(path)
assert isinstance(mesh, unreal.StaticMesh), path
registry = unreal.AssetRegistryHelpers.get_asset_registry()
registry.search_all_assets(True)
options = unreal.AssetRegistryDependencyOptions(include_soft_package_references=True, include_hard_package_references=True)
pending = [path]
packages = set()
while pending:
    package = pending.pop()
    if package in packages or not package.startswith('/Game/'):
        continue
    packages.add(package)
    assert unreal.EditorAssetLibrary.does_asset_exist(package), package
    pending.extend(str(p) for p in registry.get_dependencies(package, options))
materials = [m.material_interface.get_path_name() if m.material_interface else None for m in mesh.static_materials]
assert materials and all(materials)
bounds = mesh.get_bounds()
body = mesh.get_editor_property('body_setup')
body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
assert unreal.EditorAssetLibrary.save_loaded_asset(mesh)
report = dict(mesh=path, materials=materials, dependencies=sorted(packages),
              bounds_origin=list(bounds.origin.to_tuple()), bounds_extent=list(bounds.box_extent.to_tuple()))
(out / 'car-inspection.json').write_text(json.dumps(report, indent=2))
car = dict(mesh=path, position=[41400,30550], yaw=90, scale=1)
(out / 'car-asset.json').write_text(json.dumps(car, indent=2))
settings_path = root / 'environments/medieval-village/modern-props.json'
settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
settings['car'] = car
settings_path.write_text(json.dumps(settings, indent=2))
print('OLD_CAR_INSPECTED', json.dumps(report), flush=True)
