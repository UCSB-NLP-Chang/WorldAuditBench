"""Verify a capsule route around the market furniture to the newspaper reading point."""
import unreal,json,collections,math
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);vec=lambda p:unreal.Vector(*p)
assert level.load_level('/Game/Auditor/AncientCity/Market');w=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
def clear(p,q):
 h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,vec(p),vec(q),30,88,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
 return not h or not h.to_tuple()[0]
points={}
for x in range(-500,351,50):
 for y in range(5400,6051,50):
  p=[x,y,88]
  if clear(p,[x,y,88.1]):points[(x,y)]=p
start=(-300,5450);assert start in points and clear([-280,5470,88],points[start]);queue=collections.deque([start]);parent={start:None}
while queue:
 k=queue.popleft()
 for dx,dy in [(50,0),(-50,0),(0,50),(0,-50)]:
  n=(k[0]+dx,k[1]+dy)
  if n in points and n not in parent and clear(points[k],points[n]):parent[n]=k;queue.append(n)
target=(300,5900);assert target in parent,'Newspaper reading point is unreachable'
route=[];node=target
while node is not None:route.append(points[node]);node=parent[node]
route.reverse();report=dict(result='PASS',id='A22',route=[[-280,5470,88]]+route,clear_points=len(points),connected_points=len(parent),capsule_radius_cm=30,capsule_half_height_cm=88)
(r/'out/era-v1/route.json').write_text(json.dumps(report,indent=2));unreal.log('ERA_ROUTE_PASS')
