import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rows=[]
for name in ['Market','TeaHouse','Courtyard']:
 level.load_level('/Game/Auditor/AncientCity/'+name)
 for a in actors.get_all_level_actors():
  for c in a.get_components_by_class(unreal.PrimitiveComponent):
   try:sim=c.get_editor_property('body_instance').get_editor_property('simulate_physics')
   except Exception:sim=False
   mesh=c.get_editor_property('static_mesh') if isinstance(c,unreal.StaticMeshComponent) else None
   label=a.get_actor_label();asset=mesh.get_path_name() if mesh else ''
   if sim or any(x in (label+' '+asset).lower() for x in ['lantern','lamp','chair','bench','basket']):
    loc=c.get_world_location()
    rows.append(dict(map=name,actor=label,component=c.get_name(),asset=asset,simulate=sim,collision=str(c.get_collision_enabled()),profile=str(c.get_collision_profile_name()),location=[loc.x,loc.y,loc.z]))
(r/'out/scene-context/physics-inventory.json').write_text(json.dumps(rows,indent=2))
print('SCENE_CONTEXT_INVENTORY',len(rows),'simulating',sum(x['simulate'] for x in rows))
