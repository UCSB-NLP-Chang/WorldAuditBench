import unreal,json
from pathlib import Path
out=Path('/home/ubuntu/unreal-auditor/indoor-door-workspace/out')
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);assert l.load_level('/Game/Auditor/Regions/LivingRoom')
result=[]
for x in a.get_all_level_actors():
 if not isinstance(x,unreal.StaticMeshActor) or not x.static_mesh_component.static_mesh:continue
 mesh=x.static_mesh_component.static_mesh;c,e=x.get_actor_bounds(False)
 if (-1670<c.x<-950 and -1190<c.y<-330 and c.z<430) or any(w in mesh.get_name().lower() for w in ['vase','flower']):
  result.append(dict(name=x.get_name(),mesh=mesh.get_path_name(),location=list(x.get_actor_location().to_tuple()),rotation=list(x.get_actor_rotation().to_tuple()),scale=list(x.get_actor_scale3d().to_tuple()),center=list(c.to_tuple()),extent=list(e.to_tuple())))
(out/'vases.json').write_text(json.dumps(result,indent=2))
(out/'vase-assets.json').write_text(json.dumps([x for x in unreal.EditorAssetLibrary.list_assets('/Game/GameReady3D/AtmosphericFarmhouse',recursive=True) if any(w in x.lower() for w in ['vase','flowerpot'])],indent=2))
