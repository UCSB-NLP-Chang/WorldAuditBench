import unreal,json
from pathlib import Path
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);meshes=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem);ed=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/Auditor/AncientCity/TeaHouse');w=ed.get_editor_world();report=[]
seen=set()
for a in actors.get_all_level_actors():
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  mesh=c.get_editor_property('static_mesh')
  if not mesh or mesh.get_path_name() in seen:continue
  seen.add(mesh.get_path_name())
  if any(s in mesh.get_name().lower() for s in ['floor','stair','door','chair','table','lion','basket']):
   report.append({'mesh':mesh.get_path_name(),'simple':sum(len(mesh.get_editor_property('body_setup').get_editor_property('agg_geom').get_editor_property(k)) for k in ['box_elems','sphere_elems','sphyl_elems','convex_elems']),'flag':str(mesh.get_editor_property('body_setup').get_editor_property('collision_trace_flag')),'component':str(c.get_collision_enabled()),'profile':str(c.get_collision_profile_name()),'pawn':str(c.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN))})
for x,y in [(-1664,5650),(-1430,5520),(520,7070),(435,7220)]:
 for complex in [False,True]:
  h=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(x,y,400),unreal.Vector(x,y,-200),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,complex,[],unreal.DrawDebugTrace.NONE,True)
  data=h.to_tuple();print('FLOOR',x,y,complex,str(data))
Path('/home/ubuntu/unreal-auditor/ancient-workspace/out/collision-audit.json').write_text(json.dumps(report,indent=2));print('COLLISION_AUDIT',json.dumps(report))
