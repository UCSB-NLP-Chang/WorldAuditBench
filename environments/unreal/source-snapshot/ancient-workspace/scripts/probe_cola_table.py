import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);e=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);l.load_level('/Game/Auditor/AncientCity/TeaHouse');w=e.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
rows=[]
for x in range(-1710,-1600,2):
 for y in range(5660,5750,2):
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,120),unreal.Vector(x,y,90),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if h and h.to_tuple()[0]:v=h.to_tuple();rows.append(dict(x=x,y=y,z=v[5].z,actor=v[9].get_name()))
(r/'out/indoor-cola-v3/table.json').write_text(json.dumps(rows))
