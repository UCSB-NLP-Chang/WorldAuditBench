import unreal,json
from pathlib import Path
root=Path('/home/ubuntu/unreal-auditor/rural-workspace');levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels.load_level('/Game/Auditor/RuralAustralia/Roadside');w=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
target=next(a for a in actors.get_all_level_actors() if unreal.Name('auditor_actor:RoadTree') in a.tags);c=target.static_mesh_component;p=target.get_actor_location();ignore=[a for a in actors.get_all_level_actors() if a!=target]
out={'location':str(p),'collision_enabled':str(c.get_collision_enabled()),'response_pawn':str(c.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)),'trace_flag':str(c.get_editor_property('static_mesh').get_editor_property('body_setup').get_editor_property('collision_trace_flag')),'hits':[]}
for z in [107,200,350]:
 for dy in [-200,-100,-50,0,50,100,200]:
  start=unreal.Vector(p.x-800,p.y+dy,z);end=unreal.Vector(p.x+800,p.y+dy,z)
  hit=unreal.SystemLibrary.capsule_trace_single_by_profile(w,start,end,30,90,'Pawn',False,ignore,unreal.DrawDebugTrace.NONE,True)
  out['hits'].append({'z':z,'dy':dy,'hit':bool(hit and hit.to_tuple()[0]),'point':str(hit.to_tuple()[5]) if hit else None})
(root/'out/tree-collision.json').write_text(json.dumps(out,indent=2));print(out)
