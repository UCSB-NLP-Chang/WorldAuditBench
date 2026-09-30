import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level.load_level('/Game/Auditor/AncientCity/Courtyard')
def xyz(v):return [v.x,v.y,v.z]
rows=[]
for a in actors.get_all_level_actors():
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  mesh=c.get_editor_property('static_mesh')
  if not mesh or 'door' not in mesh.get_name().lower():continue
  pos=c.get_world_location()
  if (pos-unreal.Vector(520,7240,200)).length()>700:continue
  origin,extent=a.get_actor_bounds(False)
  rows.append(dict(actor=a.get_actor_label(),path=a.get_path_name(),tags=[str(t) for t in a.tags],component=c.get_name(),mesh=mesh.get_path_name(),location=xyz(pos),rotation=str(c.get_world_rotation()),scale=xyz(c.get_world_scale()),origin=xyz(origin),extent=xyz(extent),local_bounds=str(mesh.get_bounding_box())))
(r/'out/push-doors/door-inventory.json').write_text(json.dumps(rows,indent=2))
print('DOOR_INVENTORY',json.dumps(rows))
