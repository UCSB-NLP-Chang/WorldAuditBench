"""Run with UE 5.6 Python commandlet on A10 after importing the licensed assets."""
import json
from pathlib import Path
import unreal

ROOT = Path('/home/ubuntu/unreal-auditor/rural-workspace')
registry = unreal.AssetRegistryHelpers.get_asset_registry()
registry.search_all_assets(True)
assets = registry.get_assets_by_path('/Game/RuralAustralia', recursive=True)
inventory = {'assets': [], 'maps': [], 'levels': []}
for asset in assets:
    record = {'name': str(asset.asset_name), 'package': str(asset.package_name),
              'class': str(asset.asset_class_path.asset_name)}
    inventory['assets'].append(record)
    if record['class'] == 'World':
        inventory['maps'].append(record['package'])
if not inventory['maps']:
    raise RuntimeError('Rural Australia content is missing; no scene authoring was performed.')
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for map_path in inventory['maps']:
    if not levels.load_level(map_path):
        raise RuntimeError('Could not load ' + map_path)
    items = []
    for actor in actors.get_all_level_actors():
        origin, extent = actor.get_actor_bounds(False)
        meshes = []
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if mesh:
                meshes.append({'asset': mesh.get_path_name(), 'component': component.get_name(),
                               'collision': str(component.get_collision_enabled())})
        items.append({'label': actor.get_actor_label(), 'class': actor.get_class().get_name(),
                      'location': list(actor.get_actor_location().to_tuple()),
                      'origin': list(origin.to_tuple()), 'extent': list(extent.to_tuple()), 'meshes': meshes})
    inventory['levels'].append({'map': map_path, 'actors': items})
(ROOT / 'out/asset-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2))
print('RURAL_ASSET_INSPECTION_PASS', len(assets), len(inventory['maps']))
