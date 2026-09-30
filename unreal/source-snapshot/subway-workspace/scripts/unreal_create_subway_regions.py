"""Save three independently bounded subway maps with embedded task recipes."""
import json
from pathlib import Path
import unreal
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from unreal_subway_fixtures import create as create_fixtures
ROOT=Path(__file__).resolve().parents[1]
spec=json.loads((ROOT/'environments/subway/regions.json').read_text())
catalog=json.loads((ROOT/'environments/subway/tasks.json').read_text())
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
mode=unreal.load_class(None,'/Script/AuditorRuntime.AuditorGameMode')
region_class=unreal.load_class(None,'/Script/AuditorRuntime.AuditorRegion')
task_class=unreal.load_class(None,'/Script/AuditorRuntime.AuditorTasks')
assert mode and region_class and task_class
folder='/Game/Auditor/Subway'
unreal.EditorAssetLibrary.make_directory(folder)
path=folder+'/M_BugFlat'
mat=unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_BugFlat',folder,unreal.Material,unreal.MaterialFactoryNew())
unreal.MaterialEditingLibrary.delete_all_material_expressions(mat)
color=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
color.set_editor_property('constant',unreal.LinearColor(.9,0,.6,1))
unreal.MaterialEditingLibrary.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
unreal.MaterialEditingLibrary.recompile_material(mat)
assert unreal.EditorAssetLibrary.save_loaded_asset(mat,False)
def vec(v):return unreal.Vector(x=v[0],y=v[1],z=v[2])
def xyz(v):return [v.x,v.y,v.z]
reports=[]
for scene in spec['regions']:
 assert level.load_level(spec['source_map'])
 assert unreal.EditorLoadingAndSavingUtils.save_map(editor.get_editor_world(),scene['map'])
 assert level.load_level(scene['map'])
 world=editor.get_editor_world()
 unreal.SystemLibrary.execute_console_command(world, 'Editor.AsyncStaticMeshCompilationFinishAll')
 world.get_world_settings().set_editor_property('default_game_mode',mode)
 count=0
 for a in actors.get_all_level_actors():
  if isinstance(a,(unreal.PlayerStart,unreal.CameraActor)) or a.get_class() in [region_class,task_class]:
   actors.destroy_actor(a)
  elif a.get_class().get_name()=='BP_Train_C':
   original_name=a.get_name()
   for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
    parked=actors.spawn_actor_from_class(unreal.SkeletalMeshActor,c.get_world_location(),c.get_world_rotation())
    parked.set_actor_scale3d(c.get_world_scale())
    parked.tags=['auditor_train:'+original_name]
    parked.set_actor_label('Parked_'+original_name)
    mesh=parked.get_component_by_class(unreal.SkeletalMeshComponent)
    mesh.set_skeletal_mesh_asset(c.get_editor_property('skeletal_mesh_asset'))
    mesh.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    for i in range(c.get_num_materials()):mesh.set_material(i,c.get_material(i))
    mesh.set_collision_profile_name('BlockAll')
   actors.destroy_actor(a)
  elif isinstance(a,unreal.StaticMeshActor):
   a.tags=list(a.tags)+['auditor_actor:'+a.get_name()]
   count+=1
 create_fixtures(actors,scene['id'])
 def grounded(p):
  floor=scene['bounds_min'][2]
  h=unreal.SystemLibrary.line_trace_single(world,vec([p[0],p[1],floor+180]),vec([p[0],p[1],floor-40]),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
  data=h.to_tuple() if h else None
  assert data and data[0],(scene['id'],p,'missing floor')
  ground=data[5].z
  assert abs(ground-floor)<25,(scene['id'],p,'unexpected ground',ground)
  pos=[p[0],p[1],ground+100]
  h=unreal.SystemLibrary.capsule_trace_single(world,vec(pos),vec(pos)+unreal.Vector(z=1),30,90,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
  assert not (h and h.to_tuple()[0]),(scene['id'],p,'capsule blocked')
  return pos
 spawn=grounded(scene['spawn'])
 boundary=grounded(scene['boundary_test_start'])
 route=[grounded(p) for p in scene['traversal_points']]
 for task in catalog['tasks']:
  if task['region']==scene['id']:
   for key in ['probe','far_probe']:
    if key in task:grounded(task[key])
 tagged={str(t) for a in actors.get_all_level_actors() for t in a.tags}
 for task in catalog['tasks']:
  if task['region']!=scene['id']:continue
  for key in ['target','source']:
   if task.get(key):assert 'auditor_actor:'+task[key] in tagged,(task['id'],key)
 task_actor=actors.spawn_actor_from_class(task_class,unreal.Vector())
 task_actor.set_actor_label('AuditorTaskCatalog')
 task_actor.set_editor_property('catalog_json',json.dumps(catalog))
 task_actor.set_editor_property('error_material',mat)
 region=actors.spawn_actor_from_class(region_class,unreal.Vector())
 region.set_actor_label('TaskBoundary_'+scene['id'])
 for key,value in [('region_name',scene['name']),('bounds_min',vec(scene['bounds_min'])),('bounds_max',vec(scene['bounds_max'])),('spawn_location',vec(spawn)),('boundary_test_start',vec(boundary)),('boundary_test_direction',vec(scene['boundary_test_direction'])),('traversal_points',[vec(p) for p in route]),('region_maps',[r['map'] for r in spec['regions']])]:
  region.set_editor_property(key,value)
 rot=unreal.Rotator(pitch=0,yaw=scene['yaw'],roll=0)
 region.set_editor_property('spawn_rotation',rot)
 start=actors.spawn_actor_from_class(unreal.PlayerStart,vec(spawn),rot)
 start.set_actor_label('Start_'+scene['id'])
 assert level.save_current_level()
 reports.append(dict(id=scene['id'],spawn=spawn,traversal_points=route,boundary_test_start=boundary,mesh_instances=count))
 unreal.log('AUDITOR_SUBWAY_CREATED '+scene['map'])
Path(unreal.Paths.project_dir(),'Saved/subway-ground-probes.json').write_text(json.dumps(reports,indent=2)+'\n')
