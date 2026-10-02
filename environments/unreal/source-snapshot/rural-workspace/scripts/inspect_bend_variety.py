import unreal,json
from pathlib import Path
root=Path('/home/ubuntu/unreal-auditor/rural-workspace');level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/Auditor/RuralAustralia/RoadBend')
output=[]
for a in actors.get_all_level_actors():
 components=[]
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  mesh=c.get_editor_property('static_mesh')
  if not mesh:continue
  row=dict(name=c.get_name(),cls=c.get_class().get_name(),mesh=mesh.get_path_name(),location=list(c.get_world_location().to_tuple()),scale=list(c.get_world_scale().to_tuple()),collision=str(c.get_collision_enabled()))
  if isinstance(c,unreal.InstancedStaticMeshComponent):
   row['count']=c.get_instance_count(); row['nearby']=[]
   for i in range(c.get_instance_count()):
    t=c.get_instance_transform(i,True);p=t.translation
    if 8900<p.x<12100 and 8800<p.y<11600:row['nearby'].append(dict(index=i,position=list(p.to_tuple()),scale=list(t.scale3d.to_tuple())))
  components.append(row)
 o,e=a.get_actor_bounds(False)
 output.append(dict(label=a.get_actor_label(),cls=a.get_class().get_name(),location=list(a.get_actor_location().to_tuple()),center=list(o.to_tuple()),extent=list(e.to_tuple()),components=components))
(root/'out/bend-variety-inspection.json').write_text(json.dumps(output,indent=2));print('BEND_VARIETY_INSPECTED',len(output))
