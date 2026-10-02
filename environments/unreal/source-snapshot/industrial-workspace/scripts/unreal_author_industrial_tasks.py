"""Embed isolated task recipes in the existing industrial region maps on A10."""
import json
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / 'environments/industrial-factory/tasks.json').read_text())
regions = json.loads((ROOT / 'environments/industrial-factory/regions.json').read_text())['regions']
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
task_class = unreal.load_class(None, '/Script/AuditorRuntime.AuditorTasks')
assert task_class
folder = '/Game/Auditor/Industrial'
path = folder + '/M_StateChanged'
material = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_StateChanged', folder, unreal.Material, unreal.MaterialFactoryNew())
unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
color = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionConstant3Vector)
color.set_editor_property('constant', unreal.LinearColor(0.8, 0.025, 0.65, 1))
unreal.MaterialEditingLibrary.connect_material_property(color, '', unreal.MaterialProperty.MP_BASE_COLOR)
unreal.MaterialEditingLibrary.recompile_material(material)
assert unreal.EditorAssetLibrary.save_loaded_asset(material, False)
reports = []
for region in regions:
    assert levels.load_level(region['map'])
    found = {}
    for actor in list(actors.get_all_level_actors()):
        if actor.get_class() == task_class:
            actors.destroy_actor(actor)
        elif isinstance(actor, unreal.StaticMeshActor):
            name = actor.get_name()
            actor.tags = list(set(map(str, actor.tags)) | {'auditor_actor:' + name})
            found[name] = actor
            for tag in map(str, actor.tags):
                if tag.startswith('auditor_actor:'):
                    found[tag.split(':', 1)[1]] = actor
    for task in catalog['tasks']:
        if task['region'] != region['id']:
            continue
        assert task['map'] == region['map']
        if task['target']:
            assert task['target'] in found, (task['id'], task['target'])
            # The two control-room test chairs are fixed furnishings in every
            # case. Otherwise gravity defeats the floating/ghost recipes and
            # introduces unrelated movement into their clean controls.
            if region['id'] == 'control_room' and task['target'] in ('SM_OfficeChair4_12', 'SM_OfficeChair2'):
                found[task['target']].static_mesh_component.set_simulate_physics(False)
    transform = unreal.Transform(location=unreal.Vector(), rotation=unreal.Rotator(), scale=unreal.Vector(1, 1, 1))
    controller = unreal.AuditorSceneSetup.spawn_editor_actor(editor.get_editor_world(), task_class, transform)
    controller.set_actor_label('IndustrialTaskCatalog')
    controller.set_editor_property('catalog_json', json.dumps(catalog, ensure_ascii=False))
    controller.set_editor_property('error_material', material)
    assert levels.save_current_level()
    assert levels.load_level(region['map'])
    loaded = [actor for actor in actors.get_all_level_actors() if actor.get_class() == task_class]
    assert len(loaded) == 1
    assert json.loads(loaded[0].get_editor_property('catalog_json')) == catalog
    reports.append({'region': region['id'], 'task_count': sum(t['region'] == region['id'] for t in catalog['tasks']), 'catalog_reload': 'PASS'})
(ROOT / 'out/task-authoring.json').write_text(json.dumps(reports, indent=2))
unreal.log('AUDITOR_INDUSTRIAL_TASKS_AUTHORED')

import runpy
runpy.run_path(str(ROOT / 'scripts/author_operational.py'), run_name='__main__')
