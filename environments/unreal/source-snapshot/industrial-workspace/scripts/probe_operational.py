import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/industrial-workspace')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem); actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/Auditor/Industrial/ControlRoom')
report=[]
for a in actors.get_all_level_actors():
 p=a.get_actor_location()
 if not(-2800<p.x<-1800 and 700<p.y<1850 and 1050<p.z<1700):continue
 cs=[]
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  cs.append(dict(component=c.get_name(),mesh=c.static_mesh.get_path_name() if c.static_mesh else '',materials=[c.get_material(i).get_path_name() if c.get_material(i) else '' for i in range(c.get_num_materials())]))
 ls=[dict(component=c.get_name(),intensity=c.intensity) for c in a.get_components_by_class(unreal.LightComponent)]
 report.append(dict(name=a.get_name(),label=a.get_actor_label(),position=list(p.to_tuple()),meshes=cs,lights=ls))
(r/'out/operational-survey.json').write_text(json.dumps(report,indent=2))

