import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert level.load_level('/Game/Auditor/AncientCity/Market');w=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w);rows=[]
for x,y in [(-480,5470),(-280,5470),(-280,5570),(-280,5700),(-280,5800),(-280,5870)]:
 for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,160),unreal.Vector(x+dx*700,y+dy*700,160),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if not h or not h.to_tuple()[0]:continue
  v=h.to_tuple();rows.append(dict(probe=[x,y,88],point=list(v[5].to_tuple()),normal=list(v[6].to_tuple()),actor=v[9].get_name(),component=v[10].get_name(),distance=v[3]))
(r/'out/era-v1/newspaper-wall-candidates.json').write_text(json.dumps(rows,indent=2));print('NEWSPAPER_WALL_CANDIDATES',rows)

valid=[];raw=[]
for y in range(4900,6021,20):
 heights=[]
 for dy in [-26,0,26]:
  for dz in [-37,0,37]:
   h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(380,y+dy,145+dz),unreal.Vector(430,y+dy,145+dz),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
   heights.append(h.to_tuple()[5].x if h and h.to_tuple()[0] else None)
 raw.append(dict(y=y,x=heights))
 if not all(x is not None for x in heights) or max(heights)-min(heights)>.3:continue
 print('PLANAR',y,heights,flush=True)
 h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,unreal.Vector(200,y,88),unreal.Vector(200,y,88.1),30,90,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
 if h and h.to_tuple()[0]:
  print('CAPSULE_BLOCKED',y,h.to_tuple()[9].get_name(),flush=True);continue
 h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,unreal.Vector(-280,5470,88),unreal.Vector(200,y,88),30,88,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
 if h and h.to_tuple()[0]:
  print('PATH_BLOCKED',y,h.to_tuple()[9].get_name(),flush=True);continue
 valid.append(dict(center=[heights[4],y],probe=[200,y,88],corner_x=heights))
(r/'out/era-v1/newspaper-wall-samples.json').write_text(json.dumps(raw,indent=2))
(r/'out/era-v1/newspaper-valid-walls.json').write_text(json.dumps(valid,indent=2));print('VALID_WALLS',valid)

checks=[]
for y in [5800,5880,5900,5920]:
 for x in [-280,-100,0,100,200,300]:
  p=unreal.Vector(x,y,88)
  h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,p,p+unreal.Vector(0,0,.1),30,90,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
  blocked=h.to_tuple()[9].get_name() if h and h.to_tuple()[0] else None
  h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,unreal.Vector(-280,5870,88),p,30,88,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
  path=h.to_tuple()[9].get_name() if h and h.to_tuple()[0] else None
  checks.append(dict(probe=[x,y,88],blocked=blocked,path=path))
(r/'out/era-v1/newspaper-probe-audit.json').write_text(json.dumps(checks,indent=2))
