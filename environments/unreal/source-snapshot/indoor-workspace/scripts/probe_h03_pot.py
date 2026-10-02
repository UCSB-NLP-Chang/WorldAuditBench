import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/indoor-workspace');o=r/'out/h03-pot';o.mkdir(exist_ok=True)
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);assert l.load_level('/Game/Auditor/Regions/KitchenDining')
result=[]
for x in a.get_all_level_actors():
 if not isinstance(x,unreal.StaticMeshActor) or not x.static_mesh_component.static_mesh:continue
 mesh=x.static_mesh_component.static_mesh
 if any(w in mesh.get_name().lower() for w in ['pot','pan_','stove','cooker','oven','burner','k_cupboard_lower']):
  c,e=x.get_actor_bounds(False)
  result.append(dict(name=x.get_name(),tags=list(map(str,x.tags)),mesh=mesh.get_path_name(),location=list(x.get_actor_location().to_tuple()),rotation=list(x.get_actor_rotation().to_tuple()),scale=list(x.get_actor_scale3d().to_tuple()),center=list(c.to_tuple()),extent=list(e.to_tuple()),local_bounds=str(mesh.get_bounds())))
(o/'survey.json').write_text(json.dumps(result,indent=2))

