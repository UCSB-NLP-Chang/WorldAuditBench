import unreal,json,math
from pathlib import Path
root=Path('/home/ubuntu/unreal-auditor/medieval-workspace')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert level.load_level('/Game/Medieval_Village/Demo/Maps/Medieval_Village')
world=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(world)
vec=lambda p:unreal.Vector(*p)
ignore=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.Pawn)]
regions={'market':{'bounds':[42550,25500,44850,27350],'desired_spawn':[43550,26550]},'windmill':{'bounds':[39500,29000,42050,31600],'desired_spawn':[39850,30200]}}
def ground(x,y):
 h=unreal.SystemLibrary.line_trace_single_by_profile(world,vec([x,y,-3600]),vec([x,y,-4010]),'BlockAll',True,ignore,unreal.DrawDebugTrace.NONE,True)
 if h is None:return None
 h=h.to_tuple()
 if not h[0] or h[5].z > -3680 or h[5].z < -3880:return None
 p=[x,y,h[5].z+92]
 hit=unreal.SystemLibrary.capsule_trace_single_by_profile(world,vec(p),vec([x,y,p[2]+.1]),30,90,'Pawn',False,ignore,unreal.DrawDebugTrace.NONE,True)
 return None if hit and hit.to_tuple()[0] else p
for name,reg in regions.items():
 x0,y0,x1,y1=reg['bounds'];points={};edges={}
 for x in range(math.ceil((x0+60)/100)*100,int(x1-60)+1,100):
  for y in range(math.ceil((y0+60)/100)*100,int(y1-60)+1,100):
   p=ground(x,y)
   if p:points[f'{x},{y}']=p
 for key,p in points.items():
  edges[key]=[]
  for dx,dy in [(100,0),(-100,0),(0,100),(0,-100)]:
   other=f'{p[0]+dx},{p[1]+dy}'
   if other not in points:continue
   q=points[other]
   h=unreal.SystemLibrary.capsule_trace_single_by_profile(world,vec(p),vec(q),30,90,'Pawn',False,ignore,unreal.DrawDebugTrace.NONE,True)
   if not h or not h.to_tuple()[0]:edges[key].append(other)
 reg['points']=points;reg['edges']=edges
 print('MEDIEVAL_GRID',name,len(points),sum(map(len,edges.values())))
(root/'out/walk-grid.json').write_text(json.dumps(regions,indent=2))
info=[]
for a in actors.get_all_level_actors():
 if a.get_actor_label() in ['barrel','barrel2','barrel7','bench8','market','basket_big2','two_crates_with_lid11','cart_two_wheels4','garden_fork3']:
  parts=[]
  for c in a.get_components_by_class(unreal.StaticMeshComponent):
   m=c.get_editor_property('static_mesh')
   if m:
    setup=m.get_editor_property('body_setup')
    parts.append({'mesh':m.get_path_name(),'collision':str(c.get_collision_enabled()),'profile':str(c.get_collision_profile_name()),'trace':str(setup.get_editor_property('collision_trace_flag')) if setup else None,'simple':unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).get_simple_collision_count(m)})
  info.append({'label':a.get_actor_label(),'parts':parts})
(root/'out/target-collision.json').write_text(json.dumps(info,indent=2))
