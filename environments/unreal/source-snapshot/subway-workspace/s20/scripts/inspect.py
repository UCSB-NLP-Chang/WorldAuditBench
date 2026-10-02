import unreal,json
from pathlib import Path
out=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20/out')
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert l.load_level('/Game/Auditor/Subway/Platform')
def v(p):return [p.x,p.y,p.z]
rows=[]
for x in a.get_all_level_actors():
 c,e=x.get_actor_bounds(False)
 if x.get_class().get_name()=='StaticMeshActor':
  rows.append(dict(name=x.get_actor_label(),tags=list(map(str,x.tags)),center=v(c),extent=v(e)))
m=unreal.load_asset('/Game/M3D_Old_Car/Meshes/SM_Old_Car');assert m
b=m.get_bounding_box()
(out/'inspection.json').write_text(json.dumps(dict(actors=rows,car=dict(min=v(b.min),max=v(b.max),materials=[str(x.material_interface) for x in m.static_materials])),indent=2))
