import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');lev=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);ed=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);lev.load_level('/Game/Auditor/AncientCity/TeaHouse');w=ed.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w);c=json.loads((r/'out/ac-v2/route-nodes.json').read_text())['connected'];rows=[]
for x,y,z in c:
 if x%50 or y%50:continue
 h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,z+30),unreal.Vector(x,y,1800),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
 if h and h.to_tuple()[0]:continue
 walls=[]
 for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,z-40),unreal.Vector(x+dx*120,y+dy*120,z-40),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if h and h.to_tuple()[0]:walls.append(dict(p=list(h.to_tuple()[5].to_tuple()),n=list(h.to_tuple()[6].to_tuple()),actor=h.to_tuple()[9].get_name()))
 rows.append(dict(p=[x,y,z],walls=walls))
(r/'out/ac-v2/open-courtyard.json').write_text(json.dumps(rows,indent=2))
