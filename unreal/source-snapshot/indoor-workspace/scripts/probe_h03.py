import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/indoor-workspace');o=r/'out/h03-width';o.mkdir(exist_ok=True)
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);assert l.load_level('/Game/Auditor/Regions/KitchenDining')
target=next(x for x in a.get_all_level_actors() if 'auditor_actor:StaticMeshActor_954' in map(str,x.tags));mesh=target.static_mesh_component.static_mesh
result=[]
for x in a.get_all_level_actors():
 if isinstance(x,unreal.StaticMeshActor) and x.static_mesh_component.static_mesh==mesh:
  center,extent=x.get_actor_bounds(False)
  result.append(dict(name=x.get_name(),tags=list(map(str,x.tags)),location=list(x.get_actor_location().to_tuple()),rotation=list(x.get_actor_rotation().to_tuple()),scale=list(x.get_actor_scale3d().to_tuple()),center=list(center.to_tuple()),extent=list(extent.to_tuple())))
(o/'survey.json').write_text(json.dumps(dict(mesh=mesh.get_path_name(),local_bounds=str(mesh.get_bounds()),chairs=result),indent=2))

