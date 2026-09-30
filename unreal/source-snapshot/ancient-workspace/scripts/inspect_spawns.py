import unreal,json
from pathlib import Path
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);ed=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);results=[]
for name in ['Market','TeaHouse','Courtyard']:
 level.load_level('/Game/Auditor/AncientCity/'+name);w=ed.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w);starts=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.PlayerStart)];reg=next(a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorRegion));p=reg.get_editor_property('spawn_location')
 rays=[]
 for complex in [False,True]:
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(p.x,p.y,400),unreal.Vector(p.x,p.y,-200),'BlockAll',complex,starts,unreal.DrawDebugTrace.NONE,True);rays.append(str(h.to_tuple()))
 results.append({'map':name,'starts':[[a.get_actor_location().x,a.get_actor_location().y,a.get_actor_location().z] for a in starts],'spawn':[p.x,p.y,p.z],'hits':rays})
Path('/home/ubuntu/unreal-auditor/ancient-workspace/out/spawn-audit.json').write_text(json.dumps(results,indent=2))
