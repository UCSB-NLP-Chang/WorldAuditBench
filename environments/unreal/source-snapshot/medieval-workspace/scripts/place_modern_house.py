"""Find a supported clear site visible from the courtyard, without moving existing actors."""
import unreal,json,math
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');o=r/'out/house-v3';env=r/'environments/medieval-village'
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert level.load_level('/Game/Auditor/MedievalVillage/Windmill');w=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
v=lambda p:unreal.Vector(*p)
def trace(p,z=-2500,end=-4700):
 h=unreal.SystemLibrary.line_trace_single_by_profile(w,v([*p,z]),v([*p,end]),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
 return h.to_tuple() if h and h.to_tuple()[0] else None
points=json.loads((r/'out/walk-grid.json').read_text())['windmill']['points'].values();rows=[]
for x in range(42100,44501,300):
 for y in range(32500,34601,300):
  ground=[trace([x+dx,y+dy]) for dx in (-370,0,370) for dy in (-370,0,370)]
  if not all(ground):continue
  heights=[h[5].z for h in ground];spread=max(heights)-min(heights)
  if spread>18:continue
  z=max(heights)
  hit=unreal.SystemLibrary.box_trace_single_by_profile(w,v([x,y,z+660]),v([x,y,z+660.1]),v([380,380,635]),unreal.Rotator(),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if hit and hit.to_tuple()[0]:continue
  views=[]
  for p in points:
   distance=math.dist(p[:2],[x,y])
   if not 1400<distance<4000:continue
   h=unreal.SystemLibrary.line_trace_single_by_profile(w,v([p[0],p[1],p[2]+70]),v([x,y,z+450]),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
   if h and h.to_tuple()[0]:continue
   views.append(p)
  if views:rows.append(dict(position=[x,y],ground=z,spread=spread,probe=min(views,key=lambda p:math.dist(p,[39800,30200,-3605]))))
assert rows,'No clear building site'
rows.sort(key=lambda p:math.dist(p['position'],[42700,34000])+p['spread']*20)
(o/'house-sites.json').write_text(json.dumps(rows,indent=2));print('HOUSE_SITES',json.dumps(rows[:5]),flush=True)
chosen=next(row for row in rows if row['position']==[42700,34000])
settings=json.loads((env/'modern-props.json').read_text());settings['house']=dict(mesh='/Game/NYCBuildingVolume2/Static_Meshes/Buildings/SM_Building_G_V1',position=chosen['position'],yaw=0,scale=1,probe=[41600,31500,-3652.7668760161887])
(env/'modern-props.json').write_text(json.dumps(settings,indent=2))
