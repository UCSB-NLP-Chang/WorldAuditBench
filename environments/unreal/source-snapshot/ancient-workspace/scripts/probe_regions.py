import unreal,json
from pathlib import Path
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);ed=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert level.load_level('/Game/Auditor/AncientCity/Playtest');w=ed.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
def v(a):return unreal.Vector(*a)
def ground(x,y):
 h=unreal.SystemLibrary.line_trace_single(w,v([x,y,400]),v([x,y,-200]),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
 data=h.to_tuple() if h else None
 if not data or not data[0]:return None
 z=data[5].z
 p=[x,y,z+100]
 hit=unreal.SystemLibrary.capsule_trace_single_by_profile(w,v(p),v([x,y,z+101]),30,90,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
 return None if hit and hit.to_tuple()[0] else p
regions={'Market':[-1150,400,4800,6100],'TeaHouse':[-2300,-1300,5050,6250],'Courtyard':[-150,1150,6400,7480]}
r={}
for name,(xmin,xmax,ymin,ymax) in regions.items():
 points=[]
 for x in range(xmin+70,xmax-70,100):
  for y in range(ymin+70,ymax-70,100):
   p=ground(x,y)
   if p and p[2]<200:points.append(p)
 r[name]={'bounds':[xmin,xmax,ymin,ymax],'points':points}
Path('/home/ubuntu/unreal-auditor/ancient-workspace/out/region-probes.json').write_text(json.dumps(r,indent=2));print('REGION_PROBES_PASS',{k:len(v['points']) for k,v in r.items()})
