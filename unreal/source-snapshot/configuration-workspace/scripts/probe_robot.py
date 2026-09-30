import unreal,json
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/Auditor/Industrial/AssemblyHall')
cls=unreal.load_class(None,'/Game/Blueprints/GamePlay/BP_RobotHend.BP_RobotHend_C');assert cls
obj=actors.spawn_actor_from_class(cls,unreal.Vector(1905,1670,50),unreal.Rotator(0,90,0));assert obj
out={'class':str(cls),'properties':{},'components':[]}
for name in dir(obj):
 if any(s in name.lower() for s in ['speed','time','angle','effector','target','radius','rotat']):
  try:out['properties'][name]=str(obj.get_editor_property(name))
  except Exception:pass
for c in obj.get_components_by_class(unreal.ActorComponent):
 row={'name':c.get_name(),'class':c.get_class().get_name()}
 for name in ['relative_location','relative_rotation','animation_mode','anim_class','animation_data','skeletal_mesh_asset','static_mesh']:
  try:row[name]=str(c.get_editor_property(name))
  except Exception:pass
 out['components'].append(row)
(w/'out/robot-blueprint.json').write_text(json.dumps(out,indent=2))
print('ROBOT_BLUEPRINT_PROBED')
