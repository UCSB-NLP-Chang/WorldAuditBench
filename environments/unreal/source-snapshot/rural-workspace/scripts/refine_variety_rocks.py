"""Seat the comparison rocks at a readable size before the final private cook."""
from pathlib import Path
import json,unreal
root=Path('/home/ubuntu/unreal-auditor/rural-workspace')
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert levels.load_level('/Game/Auditor/RuralAustralia/RoadBend')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
unreal.AuditorSceneSetup.prepare_editor_collision(world)
allactors=actors.get_all_level_actors()
ignore=[a for a in allactors if 'Landscape' not in a.get_class().get_name()]
for tag in ('BendRock','BendReferenceRock'):
 a=next(a for a in allactors if unreal.Name('auditor_actor:'+tag) in a.tags)
 a.set_actor_scale3d(unreal.Vector(.45,.45,.45));p=a.get_actor_location()
 hit=unreal.SystemLibrary.line_trace_single_by_profile(world,unreal.Vector(p.x,p.y,1800),unreal.Vector(p.x,p.y,-500),'BlockAll',True,ignore,unreal.DrawDebugTrace.NONE,True)
 assert hit and hit.to_tuple()[0]
 c,e=a.get_actor_bounds(False);p.z+=hit.to_tuple()[5].z-(c.z-e.z);a.set_actor_location(p,False,True)
 if tag=='BendRock':rock=a
path=root/'environments/rural-australia/tasks.json';catalog=json.loads(path.read_text())
t=next(t for t in catalog['tasks'] if t['id']=='R03');c,e=rock.get_actor_bounds(False)
t['review_aim']=[c.x,c.y+100,c.z+e.z*1.8]
controller=next(a for a in allactors if isinstance(a,unreal.AuditorTasks))
controller.set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False))
assert levels.save_current_level();path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
print('RURAL_ROCK_REFINEMENT_PASS',t['probe'],t['review_aim'])
