"""Replace four sign-only cases with authored local props and a real fence bay."""
from pathlib import Path
import json,math,shutil,unreal
ROOT=Path('/home/ubuntu/unreal-auditor/rural-workspace');ENV=ROOT/'environments/rural-australia';out=ROOT/'out/variety-v4';out.mkdir(exist_ok=True)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
regions=json.loads((ENV/'regions.json').read_text())['regions'];region=regions[0];catalog=json.loads((ENV/'tasks.json').read_text());backup=out/'source-backup';backup.mkdir(exist_ok=True)
for name in ('tasks.json','regions.json'):
 if not (backup/name).exists():shutil.copy2(ENV/name,backup/name)
for r in regions:
 p=ROOT/'project/Content'/(r['map'][6:]+'.umap')
 if not (backup/p.name).exists():shutil.copy2(p,backup/p.name)
assert level.load_level(region['map']);w=editor.get_editor_world()
assert not any(str(tag)=='auditor_actor:BendFence' for a in actors.get_all_level_actors() for tag in a.tags),'Already authored; inspect before rerun'
def vec(p):return unreal.Vector(*p)
def xyz(p):return list(p.to_tuple())
def spawn(mesh,tr,label,tag=None):
 a=unreal.AuditorSceneSetup.spawn_editor_actor(w,unreal.StaticMeshActor,unreal.Transform())
 a.set_actor_label(label);c=a.static_mesh_component;c.set_static_mesh(mesh);a.set_actor_transform(tr,False,True);c.set_collision_profile_name('BlockAll');a.set_actor_enable_collision(True)
 if tag:a.tags=[unreal.Name('auditor_actor:'+tag)]
 return a
# Retain the original spline meshes. Match their wire bays with invisible
# collision hulls so one bay can lose collision without altering the scenery.
cube=unreal.load_asset('/Engine/BasicShapes/Cube');target=None;copied=0;wire_segments=[]
for source in [a for a in actors.get_all_level_actors() if a.get_actor_label() in ('Spline_Fence2','Spline_Fence')]:
 source.set_actor_enable_collision(False)
 for c in source.get_components_by_class(unreal.SplineMeshComponent):
  tr=c.get_world_transform();start=tr.transform_location(c.get_start_position());end=tr.transform_location(c.get_end_position());middle=(start+end)*.5
  if not (region['bounds_min'][0]-1000<middle.x<region['bounds_max'][0]+1000 and region['bounds_min'][1]-1000<middle.y<region['bounds_max'][1]+1000):continue
  delta=end-start;length=math.hypot(delta.x,delta.y);yaw=math.degrees(math.atan2(delta.y,delta.x))
  a=spawn(cube,unreal.Transform(location=unreal.Vector(middle.x,middle.y,min(start.z,end.z)+65),rotation=unreal.Rotator(yaw=yaw),scale=vec([(length+12)/100,.16,1.5])),'BendWireCollision_'+str(copied))
  a.set_actor_hidden_in_game(True);a.static_mesh_component.set_cast_shadow(False)
  wire_segments.append((a,source.get_actor_label(),xyz(start),xyz(end)));copied+=1
assert copied>10,('No wire segments',copied)
left=[row for row in wire_segments if row[1]=='Spline_Fence2']
target=min(left,key=lambda row:(row[0].get_actor_location().x-9800)**2+(row[0].get_actor_location().y-10300)**2)[0]
target.tags=[unreal.Name('auditor_actor:BendFence')]
# Ground height ignores props so every added object is seated on the terrain.
unreal.AuditorSceneSetup.prepare_editor_collision(w)
def ground(x,y):
 ignore=[a for a in actors.get_all_level_actors() if 'Landscape' not in a.get_class().get_name()]
 hit=unreal.SystemLibrary.line_trace_single_by_profile(w,vec([x,y,1800]),vec([x,y,-500]),'BlockAll',True,ignore,unreal.DrawDebugTrace.NONE,True)
 assert hit and hit.to_tuple()[0],('ground',x,y)
 return hit.to_tuple()[5].z
meshes={k:unreal.load_asset(v) for k,v in {'log':'/Game/RuralAustralia/StaticMeshes/Vegetation/Log_S_01/SM_Log_S_01','rock':'/Game/RuralAustralia/StaticMeshes/Rocks/Rock_M_01/SM_Rock_M_01','tree':'/Game/RuralAustralia/StaticMeshes/Vegetation/Tree_S_01/SM_Tree_S_01'}.items()}
def prop(kind,name,x,y,yaw,scale=1):
 a=spawn(meshes[kind],unreal.Transform(location=vec([x,y,ground(x,y)]),rotation=unreal.Rotator(yaw=yaw),scale=vec([scale]*3)),name,name)
 # Keep the mesh's bottom on the terrain; preserve natural local pivot offsets.
 center,extent=a.get_actor_bounds(False);p=a.get_actor_location();p.z+=ground(x,y)-(center.z-extent.z);a.set_actor_location(p,False,True)
 return a
log=prop('log','BendLog',10300,10900,70)
rock=prop('rock','BendRock',11350,10250,10,.45)
reference=prop('rock','BendReferenceRock',11380,10640,10,.45)
tree=prop('tree','BendTree',9700,10900,0)
changes={
'R02':dict(target='BendLog',title='Intersecting roadside logs',kind='duplicate',offset=[25,0,0],yaw=40,zh='路边两根倒木相互穿插，木质表面交叉重叠。正常情况下实体倒木不应互相穿透。',en='Two roadside logs intersect, with overlapping wooden surfaces. Solid logs should not penetrate one another.'),
'R03':dict(target='BendRock',title='Oversized roadside rock',kind='axis_scale',scale=[2.8,2.8,2.8],zh='路边一块岩石放大到同款邻近岩石的约 2.8 倍，尺寸比例明显异常。正常情况下这两块同款岩石应保持一致的尺寸。',en='One roadside rock is about 2.8 times the size of the matching nearby rock. These matching rocks should have consistent dimensions.'),
'R04':dict(target='BendFence',title='Walk through wire fence',kind='no_collision',zh='人物可以从两根立柱之间直接穿过可见的铁丝网，走到围栏另一侧。正常情况下完整的铁丝网围栏应阻挡人物通行。',en='The player can walk through the visible wire span between two fence posts and reach the other side. An intact wire fence should block passage.'),
'R05':dict(target='BendTree',title='Roadside tree disappears at center of view',kind='view_cull',threshold=.99,zh='把路边树木移到视野中央时，整棵树突然消失；偏转视角后又出现。正常情况下近处未被遮挡的树应持续可见。',en='The roadside tree disappears when centered in view and returns when the view shifts. A nearby unobstructed tree should remain visible.')}
targets={'BendLog':log,'BendRock':rock,'BendFence':target,'BendTree':tree}
def accessible(p):
 x,y=p[:2]
 if not(region['bounds_min'][0]+70<x<region['bounds_max'][0]-70 and region['bounds_min'][1]+70<y<region['bounds_max'][1]-70):return None
 q=[x,y,ground(x,y)+100]
 h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,vec(q),vec([x,y,q[2]+1]),30,90,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
 return None if h and h.to_tuple()[0] else q
report={'wire_collision_bays':copied,'original_spline_fences_preserved':True,'targets':{}}
for t in catalog['tasks']:
 if t['id'] not in changes:continue
 change=dict(changes[t['id']]);zh,en=change.pop('zh'),change.pop('en');t.update(change);a=targets[t['target']];c,e=a.get_actor_bounds(False);p=a.get_actor_location();center=xyz(c)
 preferred=math.atan2(region['spawn'][1]-c.y,region['spawn'][0]-c.x)
 radii=[450,550,650,800] if t['id']!='R03' else [650,800,900]
 if t['id']=='R04':
  # Stay near the middle of the bay, not near a post or a boundary.
  radii=[250,300,350];center[2]=ground(c.x,c.y)+110;t['collision_center']=center;t['review_aim']=center
 elif t['id']=='R05':t['review_aim']=[c.x,c.y,p.z+350]
 else:t['review_aim']=[c.x,c.y+(100 if t['id']=='R03' else 0),c.z+(e.z*1.8 if t['id']=='R03' else 0)]
 probe=None
 for radius in radii:
  for delta in (0,15,-15,30,-30,60,-60,90,-90,180):
   angle=preferred+math.radians(delta);q=accessible([c.x+radius*math.cos(angle),c.y+radius*math.sin(angle)])
   if q:
    hit=unreal.SystemLibrary.line_trace_single_by_profile(w,vec([q[0],q[1],q[2]+65]),vec(t['review_aim']),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
    if not hit or not hit.to_tuple()[0] or hit.to_tuple()[10]==a.static_mesh_component:probe=q;break
  if probe:break
 assert probe,('No clear probe',t['id']);t['probe']=probe;t['rubrics_i18n']={'zh':{'criteria':zh},'en':{'criteria':en}}
 report['targets'][t['id']]=dict(target=t['target'],center=center,extent=xyz(e),location=xyz(p),probe=probe,aim=t['review_aim'])
assert level.save_current_level()
# Roadside and Canyon content are unchanged, including their embedded catalog;
# these revised task IDs are only requested in RoadBend.
controllers=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks)];assert len(controllers)==1;controllers[0].set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert level.save_current_level()
(ENV/'tasks.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2));(out/'authoring.json').write_text(json.dumps(report,indent=2));print('RURAL_VARIETY_AUTHORED',json.dumps(report))
