import unreal,json,collections
from pathlib import Path
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/Auditor/AncientCity/Playtest')
def vec(v):return [round(v.x,3),round(v.y,3),round(v.z,3)]
entries=[]
for a in actors.get_all_level_actors():
 parts=[]
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  mesh=c.get_editor_property('static_mesh')
  if not mesh:continue
  tr=c.get_world_transform();lo,hi=c.get_local_bounds();center=tr.transform_location((lo+hi)*.5)
  parts.append({'name':c.get_name(),'mesh':mesh.get_path_name(),'location':vec(tr.translation),'rotation':str(c.get_world_rotation()),'scale':vec(tr.scale3d),'center':vec(center),'extent_local':vec((hi-lo)*.5),'collision':str(c.get_collision_enabled()),'materials':[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())]})
 entries.append({'name':a.get_name(),'label':a.get_actor_label(),'class':a.get_class().get_name(),'location':vec(a.get_actor_location()),'parts':parts})
root=Path('/home/ubuntu/unreal-auditor/ancient-workspace/out');(root/'actor-inventory.json').write_text(json.dumps(entries,indent=2))
print('ANCIENT_INSPECTION_PASS',len(entries),sum(len(a['parts']) for a in entries))
