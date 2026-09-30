import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');lev=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);ed=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
lev.load_level('/Game/Auditor/AncientCity/TeaHouse');w=ed.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w);rows=[]
for x in range(-2250,-1299,50):
 for y in range(5100,6201,50):
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,200),unreal.Vector(x,y,-100),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if not h or not h.to_tuple()[0]:continue
  z=h.to_tuple()[5].z
  if z>5:continue
  walls=[]
  for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
   h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,80),unreal.Vector(x+dx*150,y+dy*150,80),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
   if h and h.to_tuple()[0]:walls.append(dict(p=list(h.to_tuple()[5].to_tuple()),n=list(h.to_tuple()[6].to_tuple()),actor=h.to_tuple()[9].get_name()))
  if walls:rows.append(dict(p=[x,y,z],walls=walls))
(r/'out/ac-v2/exterior.json').write_text(json.dumps(rows,indent=2))
(r/'out/ac-v2/merge-help.txt').write_text(str(unreal.StaticMeshEditorSubsystem.merge_static_mesh_actors.__doc__)+str(unreal.MergeStaticMeshActorsOptions.__doc__))
