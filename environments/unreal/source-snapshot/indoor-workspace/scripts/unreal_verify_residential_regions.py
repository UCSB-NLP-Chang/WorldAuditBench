"""Independently reload all saved maps and verify their serialized region setup."""
import json
from pathlib import Path
import unreal

spec = json.loads((Path(__file__).resolve().parents[1] / 'environments/residential-house/regions.json').read_text())
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actor_system = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reports = []
asset_sets = []


def values(v):
    return [v.x, v.y, v.z]


for scene in spec['regions']:
    assert level.load_level(scene['map'])
    actors = actor_system.get_all_level_actors()
    region = [a for a in actors if a.get_class().get_name() == 'AuditorRegion']
    starts = [a for a in actors if isinstance(a, unreal.PlayerStart)]
    meshes = [a for a in actors if isinstance(a, unreal.StaticMeshActor)]
    mode = editor.get_editor_world().get_world_settings().get_editor_property('default_game_mode')
    assert len(region) == 1 and len(starts) == 1 and len(meshes) == 1334, scene['id']
    assert mode.get_name() == 'AuditorGameMode', scene['id']
    task_actors = [a for a in actors if a.get_class().get_name() == 'AuditorTasks']
    assert len(task_actors) == 1
    catalog = json.loads(task_actors[0].get_editor_property('catalog_json'))
    expected_catalog = json.loads((Path(__file__).resolve().parents[1] / 'environments/residential-house/tasks.json').read_text())
    assert catalog == expected_catalog and len(catalog['tasks']) == 20
    assert task_actors[0].get_editor_property('error_material')
    lights = [a for a in actors if a.get_actor_label().startswith('Auditor_KitchenFill_')]
    assert len(lights) == 3
    assert all(a.point_light_component.get_editor_property('intensity') == 1800 for a in lights)
    for t in catalog['tasks']:
        for key in ['target', 'source']:
            if t.get(key): assert len([a for a in meshes if 'auditor_actor:' + t[key] in [str(tag) for tag in a.tags]]) == 1
    region = region[0]
    for property_name, spec_name in [('bounds_min', 'bounds_min'), ('bounds_max', 'bounds_max'),
                                     ('spawn_location', 'spawn'), ('boundary_test_start', 'boundary_test_start'),
                                     ('boundary_test_direction', 'boundary_test_direction')]:
        assert values(region.get_editor_property(property_name)) == scene[spec_name], (scene['id'], property_name)
    assert values(starts[0].get_actor_location()) == scene['spawn'], scene['id']
    rotation = region.get_editor_property('spawn_rotation')
    assert abs(rotation.pitch) < .1 and abs(rotation.roll) < .1 and abs(rotation.yaw - scene['yaw']) < .1, scene['id']
    assert len(region.get_editor_property('traversal_points')) == len(scene['traversal_points']), scene['id']
    asset_sets.append({a.static_mesh_component.static_mesh.get_path_name() for a in meshes if a.static_mesh_component.static_mesh})
    reports.append({'id': scene['id'], 'map': scene['map'], 'mesh_instances': len(meshes),
                    'spawn': scene['spawn'], 'yaw': rotation.yaw, 'result': 'PASS'})
assert asset_sets[0] == asset_sets[1] == asset_sets[2], 'Maps must reference shared assets'
report = {'result': 'PASS', 'shared_mesh_assets': len(asset_sets[0]), 'regions': reports}
for fix in spec.get('baseline_collision_fixes', []):
    fixed = unreal.EditorAssetLibrary.load_asset(fix['copy'])
    assert fixed.get_path_name() in asset_sets[0]
    assert fixed.get_editor_property('body_setup').get_editor_property('collision_trace_flag') == unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
report['baseline_collision_fixes'] = spec.get('baseline_collision_fixes', [])
output = Path(unreal.Paths.project_dir()) / 'Saved/residential-regions-verification.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
print('AUDITOR_ALL_MAPS_VERIFIED ' + json.dumps(report))
