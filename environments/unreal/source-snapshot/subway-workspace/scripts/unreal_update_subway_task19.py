"""Refresh task 19 and its observation area without recreating unrelated scene assets."""
from pathlib import Path
import json,runpy
import unreal
root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'environments/subway/tasks.json').read_text())
spec=json.loads((root/'environments/subway/regions.json').read_text())
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
def vec(p):return unreal.Vector(x=p[0],y=p[1],z=p[2])
for region in spec['regions']:
 assert level.load_level(region['map'])
 world=editor.get_editor_world()
 unreal.SystemLibrary.execute_console_command(world,'Editor.AsyncStaticMeshCompilationFinishAll')
 def grounded(p):
  z=region['bounds_min'][2]
  hit=unreal.SystemLibrary.line_trace_single(world,vec([p[0],p[1],z+180]),vec([p[0],p[1],z-40]),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
  h=hit.to_tuple() if hit else None
  assert h and h[0],('missing ground',region['id'],p)
  assert abs(h[5].z-z)<25,('unexpected ground',region['id'],p,h[5].z)
  position=[p[0],p[1],h[5].z+100]
  hit=unreal.SystemLibrary.capsule_trace_single(world,vec(position),vec(position)+unreal.Vector(z=1),30,90,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
  assert not(hit and hit.to_tuple()[0]),('blocked probe',region['id'],p)
  return vec(position)
 for actor in actors.get_all_level_actors():
  if actor.get_actor_label() in ['SealedServicePanel','ServiceSign']:
   actors.destroy_actor(actor)
  elif actor.get_class().get_name()=='AuditorTasks':
   actor.set_editor_property('catalog_json',json.dumps(catalog))
  elif actor.get_class().get_name()=='AuditorRegion':
   actor.set_editor_property('bounds_min',vec(region['bounds_min']))
   actor.set_editor_property('bounds_max',vec(region['bounds_max']))
   actor.set_editor_property('traversal_points',[grounded(p) for p in region['traversal_points']])
 for task in catalog['tasks']:
  if task['region']==region['id']:grounded(task['probe'])
 assert level.save_current_level()
runpy.run_path(str(root/'scripts/unreal_verify_subway_regions.py'))
