import unreal,json,math
from pathlib import Path
r=Path(__file__).resolve().parents[1];tasks=json.loads((r/'environments/industrial-factory/tasks.json').read_text())['tasks'];rows=[]
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
def vec(v):return unreal.Vector(*v)
for mp in sorted({t['map'] for t in tasks}):
 assert levels.load_level(mp)
 lookup={a.get_name():a for a in actors.get_all_level_actors()}
 for t in [t for t in tasks if t['map']==mp]:
  a=lookup.get(t['target']);p=t['probe'];eye=[p[0],p[1],p[2]+70];target=a.get_actor_bounds(False)[0] if a else vec(t['position'])
  h=unreal.SystemLibrary.line_trace_single(editor.get_editor_world(),vec(eye),target,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,True,[],unreal.DrawDebugTrace.NONE,True);d=h.to_tuple() if h else ()
  hit=d[9] if len(d)>9 else None
  row=dict(simulate_physics=bool(a.static_mesh_component.get_editor_property('body_instance').get_editor_property('simulate_physics')) if a else None, id=t['id'],target=t['target'],trace=str(d),collision=str(a.static_mesh_component.get_collision_enabled()) if a else None,pawn_response=str(a.static_mesh_component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)) if a else None)
  rows.append(row)
(r/'out/target-verification.json').write_text(json.dumps(rows,indent=2))
