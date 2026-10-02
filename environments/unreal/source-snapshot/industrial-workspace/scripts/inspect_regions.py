import unreal,json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
spec=json.loads((r/'environments/industrial-factory/regions.json').read_text())
def xyz(v): return [round(v.x,2),round(v.y,2),round(v.z,2)]
rows=[]
for reg in spec['regions']:
 assert level.load_level(reg['map'])
 for a in actors.get_all_level_actors():
  c,e=a.get_actor_bounds(False)
  if all(reg['bounds_min'][i]-100 <= xyz(c)[i] <= reg['bounds_max'][i]+100 for i in range(3)):
   comps=[]
   for comp in a.get_components_by_class(unreal.StaticMeshComponent):
    mesh=comp.get_editor_property('static_mesh')
    if mesh:comps.append(mesh.get_path_name())
   rows.append(dict(region=reg['id'],name=a.get_name(),label=a.get_actor_label(),cls=a.get_class().get_name(),location=xyz(a.get_actor_location()),center=xyz(c),extent=xyz(e),meshes=comps))
(r/'out/region-layout.json').write_text(json.dumps(rows,indent=2))
