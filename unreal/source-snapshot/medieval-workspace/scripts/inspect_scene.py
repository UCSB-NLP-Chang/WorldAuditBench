import unreal,json,collections
from pathlib import Path
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/Medieval_Village/Demo/Maps/Medieval_Village')
unreal.AuditorSceneSetup.prepare_editor_collision(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world())
def vec(v):return [round(v.x,3),round(v.y,3),round(v.z,3)]
def prop(obj,key):
 try:return obj.get_editor_property(key)
 except Exception:return None
entries=[]
assets=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
for a in actors.get_all_level_actors():
 parts=[]
 comps=[]
 for c in a.get_components_by_class(unreal.ActorComponent):
  row={'name':c.get_name(),'class':c.get_class().get_name()}
  if isinstance(c,unreal.RotatingMovementComponent): row['rotation_rate']=str(c.get_editor_property('rotation_rate'))
  comps.append(row)
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  mesh=c.get_editor_property('static_mesh')
  if not mesh:continue
  tr=c.get_world_transform();lo,hi=c.get_local_bounds();center=tr.transform_location((lo+hi)*.5)
  parts.append({'name':c.get_name(),'mesh':mesh.get_path_name(),'location':vec(tr.translation),'rotation':str(c.get_world_rotation()),'scale':vec(tr.scale3d),'center':vec(center),'extent_local':vec((hi-lo)*.5),'collision':str(c.get_collision_enabled()),'visible':prop(c,'visible'),'hidden_in_game':prop(c,'hidden_in_game'),'materials':[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())]})
 entries.append({'name':a.get_name(),'label':a.get_actor_label(),'hidden':prop(a,'hidden'),'editor_only':prop(a,'is_editor_only_actor'),'class':a.get_class().get_name(),'location':vec(a.get_actor_location()),'rotation':str(a.get_actor_rotation()),'bounds_center':vec(a.get_actor_bounds(False)[0]),'bounds_extent':vec(a.get_actor_bounds(False)[1]),'parts':parts,'components':comps})
root=Path('/home/ubuntu/unreal-auditor/medieval-workspace/out');(root/'actor-inventory.json').write_text(json.dumps(entries,indent=2))
print('MEDIEVAL_INSPECTION_PASS',len(entries),sum(len(a['parts']) for a in entries))
