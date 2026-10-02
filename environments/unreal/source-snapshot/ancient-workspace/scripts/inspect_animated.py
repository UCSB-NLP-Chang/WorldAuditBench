import unreal,json
from pathlib import Path
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
l.load_level('/Game/Auditor/AncientCity/Courtyard')
report=[]
def v(p):return [round(p.x,1),round(p.y,1),round(p.z,1)]
for x in a.get_all_level_actors():
 comps=[]
 for c in x.get_components_by_class(unreal.PrimitiveComponent):
  if isinstance(c,unreal.SkinnedMeshComponent) or 'GeometryCache' in c.get_class().get_name():
   parts={'class':c.get_class().get_name(),'name':c.get_name(),'location':v(c.get_world_location())}
   if isinstance(c,unreal.SkinnedMeshComponent):
    m=c.get_editor_property('skeletal_mesh_asset');parts['mesh']=m.get_path_name() if m else None;parts['lods']=unreal.EditorSkeletalMeshLibrary.get_lod_count(m) if m else 0
   comps.append(parts)
 if comps:report.append(dict(actor=x.get_actor_label(),class_name=x.get_class().get_name(),location=v(x.get_actor_location()),components=comps))
Path('/home/ubuntu/unreal-auditor/ancient-workspace/out/animated-inventory.json').write_text(json.dumps(report,indent=2))
print('ANIMATED_INSPECTION_PASS')
