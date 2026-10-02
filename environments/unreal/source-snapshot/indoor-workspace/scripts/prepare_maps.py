from pathlib import Path
import json,unreal
r=Path(__file__).resolve().parents[1];spec=json.loads((r/'environments/residential-house/regions.json').read_text());catalog=json.loads((r/'environments/residential-house/tasks.json').read_text());assert {t['id'] for t in catalog['tasks']} == {f'H{i:02d}' for i in range(1,14)} | {'H15'}
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def v(p):return unreal.Vector(x=p[0],y=p[1],z=p[2])
reports=[]
for region in spec['regions']:
 assert level.load_level(region['map']);all_actors=actors.get_all_level_actors()
 unreal.SystemLibrary.execute_console_command(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(),'Editor.AsyncStaticMeshCompilationFinishAll')
 # A hidden cooked mesh reference for H15; the actual box exists only in that scenario.
 if region['id']=='bedroom_suite' and not any(a.actor_has_tag('auditor_actor:H15_BoxTemplate') for a in all_actors):
  box=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(0,0,-10000))
  box.set_actor_label('H15_BoxTemplate');box.tags=['auditor_actor:H15_BoxTemplate']
  box.static_mesh_component.set_static_mesh(unreal.load_asset('/Game/GameReady3D/AtmosphericFarmhouse/StaticMesh/Props/SM_Storage_Box'))
  box.set_actor_hidden_in_game(True);box.set_actor_enable_collision(False)
 # Remove the superseded custom floor-vase template; H09 uses an existing prop.
 for actor in all_actors:
  if actor.actor_has_tag('auditor_actor:H09_VaseTemplate'):actors.destroy_actor(actor)
 all_actors=actors.get_all_level_actors()
 tasks=[a for a in all_actors if a.get_class().get_name()=='AuditorTasks'];bounds=[a for a in all_actors if a.get_class().get_name()=='AuditorRegion'];assert len(tasks)==len(bounds)==1
 tasks[0].set_editor_property('catalog_json',json.dumps(catalog))
 for prop,key in [('bounds_min','bounds_min'),('bounds_max','bounds_max'),('spawn_location','spawn'),('boundary_test_start','boundary_test_start'),('boundary_test_direction','boundary_test_direction')]:bounds[0].set_editor_property(prop,v(region[key]))
 bounds[0].set_editor_property('spawn_rotation',unreal.Rotator(yaw=region['yaw']))
 bounds[0].set_editor_property('traversal_points',[v(x) for x in region['traversal_points']])
 bounds[0].set_editor_property('region_maps',[x['map'] for x in spec['regions']])
 tags={str(t) for a in all_actors for t in a.tags}
 for task in catalog['tasks']:
  if task['region']==region['id'] and task.get('target'):assert 'auditor_actor:'+task['target'] in tags,task['id']
 assert level.save_current_level();assert level.load_level(region['map'])
 reloaded=[a for a in actors.get_all_level_actors() if a.get_class().get_name()=='AuditorTasks'][0];assert json.loads(reloaded.get_editor_property('catalog_json'))==catalog
 reports.append({'region':region['id'],'result':'PASS'})
(r/'out/map-verification.json').write_text(json.dumps(reports,indent=2))
