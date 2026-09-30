import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace')
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);e=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
l.load_level('/Game/Auditor/AncientCity/Courtyard');w=e.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
report={'assets':[],'traces':[]}
for name in ['/Game/AncientChinese/Mesh/wallandStairs/SM_Stair_03','/Game/AncientChinese/Mesh/door/SM_Door_MainEntrance_01']:
 m=unreal.load_asset(name);b=m.get_editor_property('body_setup')
 report['assets'].append(dict(mesh=name,flag=str(b.get_editor_property('collision_trace_flag')),simple={k:len(b.get_editor_property('agg_geom').get_editor_property(k)) for k in ['box_elems','convex_elems']}))
for x in [435,520]:
 for y in range(6960,7481,20):
  for complex in [False,True]:
   h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,300),unreal.Vector(x,y,-50),'BlockAll',complex,[],unreal.DrawDebugTrace.NONE,True)
   d=h.to_tuple() if h else None
   report['traces'].append(dict(x=x,y=y,complex=complex,hit=bool(d and d[0]),z=d[5].z if d and d[0] else None,component=d[10].get_name() if d and d[0] and d[10] else None))
(r/'out/steps-before.json').write_text(json.dumps(report,indent=2))
print('STEP_INSPECTION_PASS')
