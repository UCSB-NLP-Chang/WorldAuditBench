"""Author bounded Rural Australia maps using the verified source on A10."""
import json,math
from pathlib import Path
import unreal
ROOT=Path('/home/ubuntu/unreal-auditor/rural-workspace'); ENV=ROOT/'environments/rural-australia'; ENV.mkdir(parents=True,exist_ok=True)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem); actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem); editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
def vec(p):return unreal.Vector(*p)
def xyz(p):return list(p.to_tuple())
def spawn(cls,p=(0,0,0)):
 return unreal.AuditorSceneSetup.spawn_editor_actor(editor.get_editor_world(),cls,unreal.Transform(location=vec(p)))
regions=[
 dict(id='road_bend',name='Bush road bend',name_zh='林间弯道',source='01',map='/Game/Auditor/RuralAustralia/RoadBend',center=[10500,10100],bounds_min=[8900,8800,-1000],bounds_max=[12100,11600,3000],spawn=[10250,10000,150],yaw=145),
 dict(id='roadside',name='Country roadside',name_zh='乡间路边',source='03',map='/Game/Auditor/RuralAustralia/Roadside',center=[-2100,-4600],bounds_min=[-4200,-6000,-1000],bounds_max=[600,-2900,3000],spawn=[-1450,-4782,100],yaw=180),
 dict(id='canyon',name='Creek canyon',name_zh='溪谷林地',source='02',map='/Game/Auditor/RuralAustralia/Canyon',center=[12000,-3000],bounds_min=[10800,-4100,-1000],bounds_max=[13400,-1700,4000],spawn=[12100,-3250,350],yaw=135)]
labels={
 'road_bend':{'BendSign':'SM_KangarooSign_3','BendOtherSign':'SM_KangarooSign_4'},
 'roadside':{'RoadSign':'SM_KangarooSign_3','RoadTree':'SM_Tree_M_9','RoadLog':'SM_Log_S_3'},
 'canyon':{'CreekRock':'SM_Rock_M_184','CreekLog':'SM_Log_S_21','CreekTree':'SM_Tree_S_11'}}
# Task IDs are family-specific in the web catalog and R01-R18 in this executable.
specs=[
 ('road_bend','offset','BendSign','G1','Floating wildlife sign','袋鼠警示牌整体悬在地面上方，立柱下方没有支撑。正常情况下立柱应落地固定。','The wildlife sign floats above the ground without support. Its post should be anchored in the ground.',dict(offset=[0,0,100])),
 ('road_bend','duplicate','BendSign','G2','Intersecting wildlife signs','同一位置的两块警示牌相互穿插。正常情况下应只有一块完整且不重叠的标牌。','Two wildlife signs intersect at the same location. A single intact sign should occupy this position.',dict(offset=[0,22,0],yaw=25)),
 ('road_bend','axis_scale','BendSign','G3','Stretched wildlife sign','警示牌被竖向拉长为三倍，牌面和立柱比例异常。正常情况下应与对面同类标牌的尺寸比例一致。','The sign is stretched to three times its height, distorting its panel and post. Its proportions should match the same type of sign across the road.',dict(scale=[1,1,3])),
 ('road_bend','no_collision','BendSign','C1','Walk through signpost','人物可以穿过可见的警示牌立柱。正常情况下实体立柱应阻挡人物。','The player can walk through the visible signpost. The solid post should block the player.',{}),
 ('road_bend','view_cull','BendOtherSign','V1','Sign disappears at center of view','把警示牌移到视野中央时它消失，偏转视角后又出现。正常情况下清晰可见的标牌不应随视角突然消失。','The sign disappears when centered in view and returns when the view shifts. A clearly visible sign should remain present across viewing angles.',dict(threshold=.99)),
 ('road_bend','shadow_offset','BendSign','V3','Detached sign shadow','警示牌位置正常，但阴影偏移到不对应的位置。正常情况下阴影应与标牌和日照方向一致。','The sign remains in place while its shadow is displaced. Its shadow should agree with the sign position and sunlight.',dict(offset=[180,0,0])),
 ('roadside','offset','RoadLog','G1','Floating roadside log','路边倒木悬在地面上方，没有接触地面。正常情况下倒木应由地面支撑。','The roadside log floats above the ground. A fallen log should rest on the ground.',dict(offset=[0,0,100])),
 ('roadside','no_collision','RoadTree','C1','Walk through tree trunk','人物可以走进并穿过可见的树干。正常情况下实体树干应阻挡人物。','The player can walk into and through the visible tree trunk. A solid trunk should block the player.',dict(collision_center=[-2177.630859375,-5404.6298828125,100],review_aim=[-2177.63,-5404.63,150])),
 ('roadside','blocker','','C2','Invisible road barrier','道路空旷处出现空气墙，人物无法穿过。正常情况下没有可见障碍的路面应允许通行。','An invisible barrier blocks a clear part of the road. The unobstructed road should allow passage.',dict(position=[-1700,-4782,110],extent=[200,8,105])),
 ('roadside','distance_scale','RoadLog','V2','Log changes size with distance','同一根倒木在后退几米后突然放大，靠近又恢复。正常情况下观察距离不应改变倒木的实际外形尺寸。','The same log suddenly grows when viewed from farther away and returns to normal nearby. Viewing distance should not change its physical dimensions.',dict(threshold=550,factor=2)),
 ('roadside','return_hide','RoadSign','T1','Road sign disappears between visits','先看清警示牌，背向它走远后返回，标牌无原因地消失。正常情况下无人移除的标牌应仍在原处。','Observe the sign, walk away facing away, and return; the sign has disappeared. A sign that nobody removed should remain in place.',dict(near=550,far=750)),
 ('roadside','semantic_add','RoadTree','S1','Tree planted in road lane','一棵树被布置在完好的道路车道中央，妨碍道路使用。正常情况下道路行车空间应保持畅通，树木应位于路侧。','A tree is placed in the middle of an intact road lane, obstructing its use. The roadway should remain clear, with trees at the roadside.',dict(position=[-1600,-4782,0],yaw=0)),
 ('canyon','offset','CreekRock','G1','Floating creek rock','溪谷中的石块悬在地面上方，下方没有支撑。正常情况下石块应接触地面。','A creek rock floats above the ground without support. It should rest on the ground.',dict(offset=[0,0,100])),
 ('canyon','duplicate','CreekLog','G2','Intersecting fallen logs','两根倒木在同一位置相互穿入，木质表面交叉重叠。正常情况下实体倒木不应互相穿透。','Two fallen logs intersect at the same position, with overlapping wooden surfaces. Solid logs should not penetrate one another.',dict(offset=[30,0,0],yaw=35)),
 ('canyon','view_cull','CreekRock','V1','Creek rock disappears at center of view','把溪边倒木旁的小石块移到视野中央时，它突然消失，偏转视角后又恢复。正常情况下近处未被遮挡的石块应持续可见。','The small rock beside the creek log disappears when centered in view and returns when the view shifts. A nearby unobstructed rock should remain visible.',dict(threshold=.99)),
 ('canyon','return_move','CreekLog','T2','Log moves between visits','观察倒木，背向它走远再返回后，倒木在无人搬动时平移。正常情况下静止倒木应保持原来的位置。','Observe the log, walk away facing away, and return; it has moved without being touched. A stationary log should retain its position.',dict(near=550,far=750,offset=[80,0,0])),
 ('canyon','return_material','CreekRock','T2','Rock changes colour between visits','观察石块，背向它走远再返回后，同一石块无原因地变成蓝色。正常情况下无人修改的石块应保持原有材质。','Observe the rock, walk away facing away, and return; the same rock has turned blue without a cause. Its material should remain unchanged.',dict(near=550,far=750)),
 ('canyon','distance_cull','CreekTree','V1','Tree vanishes a few metres away','后退几米时眼前的树突然消失，靠近又出现。正常情况下近距离且未被遮挡的树应持续可见。','A nearby tree abruptly disappears when stepping back and returns on approach. A nearby, unobstructed tree should remain visible.',dict(threshold=650))]
tasks=[]; reports=[]
mat=unreal.load_asset('/Game/Auditor/RuralAustralia/M_ReviewBlue')
if not mat:
 mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_ReviewBlue','/Game/Auditor/RuralAustralia',unreal.Material,unreal.MaterialFactoryNew()); color=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector);color.set_editor_property('constant',unreal.LinearColor(.015,.07,.7,1));unreal.MaterialEditingLibrary.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR);unreal.MaterialEditingLibrary.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat)
def ground_point(p,region,search=200):
 w=editor.get_editor_world()
 offsets=sorted([(x,y) for x in range(-search,search+1,50) for y in range(-search,search+1,50)],key=lambda v:v[0]**2+v[1]**2)
 for dx,dy in offsets:
  x,y=p[0]+dx,p[1]+dy
  if not(region['bounds_min'][0]+50<x<region['bounds_max'][0]-50 and region['bounds_min'][1]+50<y<region['bounds_max'][1]-50):continue
  hit_ground=unreal.SystemLibrary.line_trace_single_by_profile(w,vec([x,y,p[2]+350]),vec([x,y,p[2]-650]),'BlockAll',False,[],unreal.DrawDebugTrace.NONE,True)
  if not hit_ground:continue
  h=hit_ground.to_tuple()
  if not h[0] or h[6].z<.75:continue
  c=h[10]
  if isinstance(c,unreal.StaticMeshComponent):
   m=c.get_editor_property('static_mesh')
   if m and any(k in m.get_name().lower() for k in ['tree','log','sign','fence','grass']):continue
  pos=[x,y,h[5].z+100]
  hit=unreal.SystemLibrary.capsule_trace_single_by_profile(w,vec(pos),vec([x,y,pos[2]+1]),30,90,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
  if not hit or not hit.to_tuple()[0]:return pos
 raise RuntimeError('No accessible ground '+str(p)+' '+region['id'])
for region in regions:
 assert level.load_level('/Game/RuralAustralia/Maps/RuralAustralia_Example_'+region['source']);w=editor.get_editor_world()
 assert unreal.EditorLoadingAndSavingUtils.save_map(w,region['map']); assert level.load_level(region['map']);w=editor.get_editor_world()
 before=len(actors.get_all_level_actors()); removed=0; foliage_removed=0;landscape_removed=0; tagged={};cx,cy=region['center']; radius=8500
 for a in list(actors.get_all_level_actors()):
  cls=a.get_class().get_name(); label=a.get_actor_label();o,e=a.get_actor_bounds(False)
  if label in labels[region['id']].values():
   alias=next(k for k,v in labels[region['id']].items() if v==label);a.tags=list(a.tags)+[unreal.Name('auditor_actor:'+alias)];tagged[alias]=a
   a.static_mesh_component.set_collision_profile_name('BlockAll');a.set_actor_enable_collision(True)
   mesh=a.static_mesh_component.get_editor_property('static_mesh');mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);unreal.EditorAssetLibrary.save_loaded_asset(mesh)
  elif isinstance(a,(unreal.PlayerStart,unreal.AuditorRegion,unreal.AuditorTasks)) or 'Camera' in cls or 'ProceduralFoliageVolume' in cls or 'Niagara' in cls or cls in ['PlanarReflection','BlockingVolume']:
   actors.destroy_actor(a);removed+=1;continue
  elif isinstance(a,unreal.StaticMeshActor) and (abs(o.x-cx)>radius+e.x or abs(o.y-cy)>radius+e.y):
   actors.destroy_actor(a);removed+=1;continue
  if isinstance(a,unreal.DirectionalLight):a.light_component.set_editor_property('contact_shadow_length',.04)
  for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
   drop=[]
   for i in range(c.get_instance_count()):
    p=c.get_instance_transform(i,True).translation
    if abs(p.x-cx)>radius or abs(p.y-cy)>radius:drop.append(i)
   if drop:c.remove_instances(drop);foliage_removed+=len(drop)
  # Retain a scenic buffer, but remove landscape tiles outside it.
  terrain_components=list(a.get_components_by_class(unreal.SceneComponent))
  tile_x=sorted(set(c.get_world_location().x for c in terrain_components if c.get_class().get_name()=='LandscapeComponent'))
  tile_size=min([b-a for a,b in zip(tile_x,tile_x[1:])],default=25500)
  for c in terrain_components:
   if c.get_class().get_name() not in ['LandscapeComponent','LandscapeHeightfieldCollisionComponent']:continue
   try:
    size=c.get_editor_property('component_size_quads')*a.get_actor_scale3d().x
   except: size=tile_size
   p=c.get_world_location()
   if p.x>cx+radius or p.x+size<cx-radius or p.y>cy+radius or p.y+size<cy-radius:
    c.destroy_component(a);landscape_removed+=1
 unreal.AuditorSceneSetup.prepare_editor_collision(w)
 region['spawn']=ground_point(region['spawn'],region,400)
 # Walk a modest loop around the actual starting ground; all endpoints validated.
 x,y,z=region['spawn'];region['traversal_points']=[ground_point([x+dx,y+dy,z],region,200) for dx,dy in [(0,0),(180,0),(180,180),(0,180),(0,0)]]
 # Boundary path uses a clear edge close to the spawn's y coordinate.
 edge=region['bounds_max'][0]-130
 region['boundary_test_start']=ground_point([edge,y,z],region,100);region['boundary_test_direction']=[1,0,0]
 for idx,s in enumerate(specs,1):
  rid,kind,target,code,title,zh,en,extra=s
  if rid!=region['id']:continue
  a=tagged.get(target); center=xyz(a.get_actor_bounds(False)[0]) if a else extra['position']; location=xyz(a.get_actor_location()) if a else center
  probe=None
  if a:
   # Ground candidates approach target horizontally, preferring unobstructed views.
   for radius_probe in [350,450,550,650,800]:
    for angle in range(0,360,30):
     q=[center[0]+radius_probe*math.cos(math.radians(angle)),center[1]+radius_probe*math.sin(math.radians(angle)),location[2]+100]
     try:p=ground_point(q,region,0)
     except RuntimeError:continue
     eye=[p[0],p[1],p[2]+70]
     viewhit=unreal.SystemLibrary.line_trace_single_by_profile(w,vec(eye),vec(center),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
     if not viewhit or not viewhit.to_tuple()[0] or viewhit.to_tuple()[10] in a.get_components_by_class(unreal.PrimitiveComponent):probe=p;break
    if probe:break
  else:probe=ground_point([extra['position'][0],extra['position'][1]-250,extra['position'][2]],region,100)
  if not probe:raise RuntimeError('No clear target view '+target)
  t=dict(id=f'R{idx:02}',region=rid,map=region['map'],kind=kind,target=target,subcategory=code,title=title,probe=probe,rubrics_i18n={'zh':{'criteria':zh},'en':{'criteria':en}},**extra)
  if kind in ['return_move','return_hide','return_material','distance_scale','distance_cull']:
   d=[probe[0]-center[0],probe[1]-center[1]];mag=math.hypot(*d); far=None
   for angle in [0,30,-30,60,-60,90,-90,180]:
    an=math.atan2(d[1],d[0])+math.radians(angle)
    try:far=ground_point([center[0]+1050*math.cos(an),center[1]+1050*math.sin(an),location[2]+100],region,100);break
    except RuntimeError:continue
   if not far:raise RuntimeError('No far probe '+target)
   t['far_probe']=far
  if kind=='blocker':t['position']=ground_point(t['position'],region,0);t['review_aim']=t['position']
  if kind=='semantic_add':
   p=ground_point([*t['position'][:2],100],region,0);bottom=a.get_actor_bounds(False)[0].z-a.get_actor_bounds(False)[1].z-a.get_actor_location().z;t['position'][2]=p[2]-100-bottom;t['review_aim']=[*t['position'][:2],p[2]+100]
  tasks.append(t)
 reg=spawn(unreal.AuditorRegion);reg.set_actor_label('Rural_'+region['id'])
 for name,key in [('region_name','name'),('bounds_min','bounds_min'),('bounds_max','bounds_max'),('spawn_location','spawn'),('boundary_test_start','boundary_test_start'),('boundary_test_direction','boundary_test_direction')]:reg.set_editor_property(name,vec(region[key]) if isinstance(region[key],list) else region[key])
 reg.set_editor_property('spawn_rotation',unreal.Rotator(yaw=region['yaw']));reg.set_editor_property('traversal_points',[vec(p) for p in region['traversal_points']]);reg.set_editor_property('region_maps',[r['map'] for r in regions]);spawn(unreal.PlayerStart,region['spawn'])
 worldsettings=w.get_world_settings();worldsettings.set_editor_property('default_game_mode',unreal.load_class(None,'/Script/AuditorRuntime.AuditorGameMode'))
 assert level.save_current_level()
 reports.append(dict(region=region['id'],actors_before=before,actors_after=len(actors.get_all_level_actors()),actors_removed=removed,foliage_instances_removed=foliage_removed,landscape_components_removed=landscape_removed,targets={k:dict(location=xyz(a.get_actor_location()),center=xyz(a.get_actor_bounds(False)[0])) for k,a in tagged.items()}))
 print('RURAL_REGION_CREATED',region['id'],reports[-1])
tasks.sort(key=lambda t:t['id'])
for region in regions:
 assert level.load_level(region['map']);controller=spawn(unreal.AuditorTasks);controller.set_editor_property('catalog_json',json.dumps({'tasks':tasks},ensure_ascii=False));controller.set_editor_property('error_material',mat);assert level.save_current_level()
(ENV/'regions.json').write_text(json.dumps({'regions':regions},ensure_ascii=False,indent=2));(ENV/'tasks.json').write_text(json.dumps({'taxonomy_version':'user-2026-09-12-scene-semantics','tasks':tasks},ensure_ascii=False,indent=2));(ROOT/'out/map-setup.json').write_text(json.dumps(reports,indent=2));print('RURAL_REGIONS_CREATED',len(regions),len(tasks))
