import json,unreal
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/industrial-workspace')
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
l.load_level('/Game/Auditor/Industrial/ControlRoom')
report=[]
for actor in a.get_all_level_actors():
 cs=actor.get_components_by_class(unreal.StaticMeshComponent)
 for c in cs:
  if c.static_mesh and any(s in c.static_mesh.get_name().lower() for s in ['deskcontrol','lampset']):
   center,extent=actor.get_actor_bounds(False)
   report.append(dict(name=actor.get_name(),pos=list(actor.get_actor_location().to_tuple()),rot=list(actor.get_actor_rotation().to_tuple()),center=list(center.to_tuple()),extent=list(extent.to_tuple()),materials=[c.get_material(i).get_path_name() for i in range(c.get_num_materials())]))
(r/'out/operational-detail.json').write_text(json.dumps(report,indent=2))
mats={}
for name in ['/Game/Materials/M_LampSet_01','/Game/Materials/MI_ControlDeskPainted01','/Game/Materials/MI_CrashTestCam']:
 m=unreal.load_asset(name)
 mats[name]=dict(type=m.get_class().get_name())
 if isinstance(m,unreal.MaterialInstanceConstant):
  mats[name]['parent']=m.parent.get_path_name()
  mats[name]['scalars']=[str(v) for v in m.scalar_parameter_values]
  mats[name]['vectors']=[str(v) for v in m.vector_parameter_values]
 else:
  mats[name]['parameters']=[str(v) for v in unreal.MaterialEditingLibrary.get_scalar_parameter_names(m)]
(r/'out/operational-materials.json').write_text(json.dumps(mats,indent=2))

