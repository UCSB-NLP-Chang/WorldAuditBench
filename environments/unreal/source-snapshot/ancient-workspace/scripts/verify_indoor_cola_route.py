import unreal,json,collections
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');lev=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);ed=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);lev.load_level('/Game/Auditor/AncientCity/TeaHouse');w=ed.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w);vec=lambda p:unreal.Vector(*p)
def clear(p,q):
 h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,vec(p),vec(q),30,90,'Pawn',True,[],unreal.DrawDebugTrace.NONE,True);return not h or not h.to_tuple()[0]
points={}
for x in range(-2250,-1324,25):
 for y in range(5075,6226,25):
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,130),unreal.Vector(x,y,-60),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if h and h.to_tuple()[0]:
   z=h.to_tuple()[5].z
   if -15<=z<=100 and clear([x,y,z+100],[x,y,z+100.1]):points[(x,y)]=[x,y,z+100]
start=(-1550,5500);target=(-1800,5550);assert start in points and clear([-1530,5520,120.125],points[start]);parent={start:None};q=collections.deque([start])
while q:
 k=q.popleft()
 for dx,dy in [(25,0),(-25,0),(0,25),(0,-25)]:
  n=(k[0]+dx,k[1]+dy)
  if n not in points or n in parent:continue
  a,b=points[k],points[n];z=max(a[2],b[2])
  if abs(a[2]-b[2])<=35 and clear([a[0],a[1],z],[b[0],b[1],z]):parent[n]=k;q.append(n)
(r/'out/indoor-cola-v3/route-nodes.json').write_text(json.dumps(dict(points=list(points.values()),connected=[points[k] for k in parent]),indent=2))
report=dict(result='PASS' if target in parent else 'FAIL',nodes=len(points),connected=len(parent),target=target,route=[])
if target in parent:
 n=target
 while n is not None:report['route'].append(points[n]);n=parent[n]
 report['route'].reverse()
(r/'out/indoor-cola-v3/route.json').write_text(json.dumps(report,indent=2));assert report['result']=='PASS'
