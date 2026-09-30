import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert level.load_level('/Game/Auditor/AncientCity/Market');w=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w);rows=[]
for x in [-150,0,150,250]:
 for y in [5000,5100,5200,5800,5900,6000]:
  samples=[]
  for dx,dy in [(0,0),(-48,-104),(-48,104),(48,-104),(48,104)]:
   h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x+dx,y+dy,250),unreal.Vector(x+dx,y+dy,-100),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
   samples.append(round(h.to_tuple()[5].z,1) if h and h.to_tuple()[0] else None)
  if all(z is not None and -14<z<-10 for z in samples):rows.append(dict(center=[x,y],support_z=samples))
(r/'out/era-v1/solar-floor-candidates.json').write_text(json.dumps(rows,indent=2));print('SOLAR_FLOOR_CANDIDATES',rows)

assert level.load_level('/Game/Auditor/AncientCity/TeaHouse');w=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w);rows=[]
for x in range(-2150,-1599,50):
 for y in range(5200,6101,50):
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,250),unreal.Vector(x,y,-100),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if not h or not h.to_tuple()[0]:continue
  z=h.to_tuple()[5].z
  if not 19<z<21:continue
  c=unreal.Vector(x,y,z+65)
  h=unreal.SystemLibrary.box_trace_single_by_profile(w,c,c+unreal.Vector(0,0,.1),unreal.Vector(32,43,60),unreal.Rotator(),'BlockAll',False,[],unreal.DrawDebugTrace.NONE,True)
  if h and h.to_tuple()[0]:continue
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(-1530,5520,190),c,'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if h and h.to_tuple()[0]:continue
  rows.append([x,y,z])
(r/'out/era-v1/ac-floor-candidates.json').write_text(json.dumps(rows,indent=2));print('AC_FLOOR_CANDIDATES',rows)
