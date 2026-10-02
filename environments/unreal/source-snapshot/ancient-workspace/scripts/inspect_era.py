"""Read-only inspection of licensed props and Ancient mounting surfaces on A10."""
import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');out=r/'out/era-v1'
paths=['/Game/GameReady3D/AtmosphericFarmhouse/StaticMesh/Props/SM_'+n for n in ['Computer','Solarpanel','Fridge']]
paths+=['/Game/Meshes/'+n for n in ['SM_VideoCamera_01','SM_VideoCamera_02','SM_AirConditioning_01','SM_AirConditioner01','SM_AirConditioner02']]
rows=[]
for p in paths:
 m=unreal.load_asset(p);assert isinstance(m,unreal.StaticMesh),p
 b=m.get_bounds();rows.append(dict(mesh=p,origin=list(b.origin.to_tuple()),extent=list(b.box_extent.to_tuple()),materials=[x.material_interface.get_path_name() if x.material_interface else None for x in m.static_materials]))
(out/'asset-inspection.json').write_text(json.dumps(rows,indent=2))
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rows=[]
for name in ['Market','TeaHouse','Courtyard']:
 assert level.load_level('/Game/Auditor/AncientCity/'+name)
 for a in actors.get_all_level_actors():
  if not isinstance(a,unreal.StaticMeshActor):continue
  c=a.static_mesh_component;m=c.static_mesh
  if not m:continue
  b=a.get_actor_bounds(False)
  rows.append(dict(map=name,name=a.get_name(),label=a.get_actor_label(),tags=[str(t) for t in a.tags],mesh=m.get_path_name(),location=list(a.get_actor_location().to_tuple()),rotation=list(a.get_actor_rotation().to_tuple()),origin=list(b[0].to_tuple()),extent=list(b[1].to_tuple())))
(out/'scene-inspection.json').write_text(json.dumps(rows,indent=2))
print('ERA_INSPECTED',len(rows),flush=True)
