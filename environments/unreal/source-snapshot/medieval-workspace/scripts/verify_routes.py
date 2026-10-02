import unreal,json,math,collections
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');env=r/'environments/medieval-village';regions=json.loads((env/'regions.json').read_text())['regions'];tasks=json.loads((env/'tasks.json').read_text())['tasks'];grids=json.loads((r/'out/walk-grid.json').read_text());reports=[]
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);vec=lambda p:unreal.Vector(*p)
for reg in regions:
 assert level.load_level(reg['map']);w=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
 def clear(p,q):
  h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,vec(p),vec(q),30,90,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
  return not h or not h.to_tuple()[0]
 g=grids[reg['id']];points={k:p for k,p in g['points'].items() if clear(p,[p[0],p[1],p[2]+.1])};edges={k:[n for n in g['edges'][k] if n in points and clear(p,points[n])] for k,p in points.items()};start=min(points,key=lambda k:math.dist(points[k],reg['spawn']));todo=[start];connected={start}
 while todo:
  for n in edges[todo.pop()]:
   if n not in connected:connected.add(n);todo.append(n)
 checks=[]
 for t in tasks:
  if t['region']!=reg['id']:continue
  for kind in ['probe','far_probe']:
   if kind not in t:continue
   p=t[kind];nearest=min(points,key=lambda k:math.dist(points[k],p));ok=nearest in connected and math.dist(points[nearest],p)<1
   assert ok,(t['id'],kind,p)
   checks.append(dict(id=t['id'],kind=kind,reachable=True))
 reports.append(dict(region=reg['id'],connected_ground_points=len(connected),checks=checks))
(r/'out/route-verification.json').write_text(json.dumps(dict(result='PASS',regions=reports),indent=2))
