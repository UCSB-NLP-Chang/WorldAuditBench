from pathlib import Path
import json,heapq,math
import unreal
root=Path(__file__).resolve().parents[1];spec=json.loads((root/'environments/subway/regions.json').read_text());r=next(x for x in spec['regions'] if x['id']=='platform')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);assert level.load_level(r['map']);world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();unreal.SystemLibrary.execute_console_command(world,'Editor.AsyncStaticMeshCompilationFinishAll')
def v(p):return unreal.Vector(x=p[0],y=p[1],z=100)
cache={}
def clear(a,b):
 key=tuple(sorted((a,b)))
 if key not in cache:
  h=unreal.SystemLibrary.capsule_trace_single(world,v(a),v(b) if a!=b else v(b)+unreal.Vector(z=1),32,90,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
  cache[key]=not(h and h.to_tuple()[0])
 return cache[key]
# Keep the previous east-platform coverage, then reach both escalator pairs and the task probe.
goals=[(1100,1700),(2400,1700),(2650,1700),(2650,1200),(2000,1200),(1300,1200),(0,1700),(-500,1700),(0,1200)]
nodes={(x,y) for x in range(-500,2701,100) for y in range(1000,1901,100)}|set(goals)
nodes={p for p in nodes if clear(p,p)}
def route(a,b):
 assert a in nodes and b in nodes,(a,b)
 queue=[(math.dist(a,b),0,a)];cost={a:0};prev={}
 while queue:
  _,g,p=heapq.heappop(queue)
  if p==b:
   result=[b]
   while result[-1]!=a:result.append(prev[result[-1]])
   return list(reversed(result))
  if g>cost[p]:continue
  for q in nodes:
   distance=math.dist(p,q)
   if 0<distance<=225 and clear(p,q):
    ng=g+distance
    if ng<cost.get(q,1e30):cost[q]=ng;prev[q]=p;heapq.heappush(queue,(ng+math.dist(q,b),ng,q))
 raise RuntimeError(('No walkable connection',a,b))
points=[goals[0]]
for a,b in zip(goals,goals[1:]):
 path=route(a,b);i=0
 while i<len(path)-1:
  j=next(j for j in range(len(path)-1,i,-1) if math.dist(path[i],path[j])<=1400 and clear(path[i],path[j]))
  points.append(path[j]);i=j
assert all(clear(a,b) for a,b in zip(points,points[1:]))
r['traversal_points']=[[x,y,100] for x,y in points]
for a in actors.get_all_level_actors():
 if a.get_class().get_name()=='AuditorRegion':a.set_editor_property('traversal_points',[v(p) for p in points])
assert level.save_current_level();(root/'environments/subway/regions.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n');(root/'out/route-fix.json').write_text(json.dumps({'points':r['traversal_points'],'capsule_radius':32,'all_segments_clear':True},indent=2));unreal.log('SUBWAY_ROUTE_FIXED')
