import unreal,json,math
from pathlib import Path
ROOT=Path('/home/ubuntu/unreal-auditor/ancient-workspace');OUT=ROOT/'out';ENV=ROOT/'environments/ancient-chinese-city'
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
def vec(p):return unreal.Vector(*p)
def xyz(v):return [v.x,v.y,v.z]
def spawn(cls,loc=[0,0,0],rot=None):
 a=unreal.AuditorSceneSetup.spawn_editor_actor(editor.get_editor_world(),cls,unreal.Transform(location=vec(loc),rotation=rot or unreal.Rotator(),scale=vec([1,1,1])))
 assert a;return a
aliases={
 ('BP_chairandtable3','SM_stall_SM_Chair_02'):'MarketBench',('BP_chairandtable3','SM_stall_SM_Table_01'):'MarketTable',
 ('BP_Stall_02','SM_stall_SM_Stall_01'):'MarketCanopy',
 ('BP_chairandtable_01','SM_stall_SM_Chair_02'):'TeaBench',('BP_chairandtable_01','SM_stall_SM_Table_01'):'TeaTable',
 ('SM_doorMain_SM_Door_MainEntrance_01','SM_doorstonelion_SM_DoorMain_02'):'InteractiveDoor',
 ('BP_Lantern','SM_Asset_01_SM_Lantern_01'):'CourtLantern'}
regions=[
 dict(id='market',name='Market street',name_zh='集市街道',map='/Game/Auditor/AncientCity/Market',bounds_min=[-1150,4800,-25],bounds_max=[400,6100,650],spawn=[-480,5470,80],yaw=0,boundary_test_start=[-80,4920,80],boundary_test_direction=[0,-1,0],traversal_points=[[-480,5470,80],[-280,5470,80],[-280,5870,80],[-480,5870,80],[-480,5470,80]]),
 dict(id='tea_house',name='Tea house',name_zh='茶馆',map='/Game/Auditor/AncientCity/TeaHouse',bounds_min=[-2300,5050,-25],bounds_max=[-1300,6250,650],spawn=[-1530,5520,120],yaw=150,boundary_test_start=[-1430,6120,80],boundary_test_direction=[0,1,0],traversal_points=[[-1530,5520,120],[-1530,5320,120],[-1530,5420,120],[-1530,5320,120],[-1530,5520,120]]),
 dict(id='courtyard',name='Residence entrance',name_zh='宅院入口',map='/Game/Auditor/AncientCity/Courtyard',bounds_min=[-150,6400,-25],bounds_max=[1150,7480,700],spawn=[520,7070,80],yaw=90,boundary_test_start=[520,6520,80],boundary_test_direction=[0,-1,0],traversal_points=[[520,7070,80],[520,6770,80],[920,6770,80],[920,6970,80],[920,6770,80],[520,6770,80],[520,7070,80]])]
region_by={r['id']:r for r in regions}
def task(i,region,kind,target,code,title,zh,en,probe,**kw):
 return dict(id=f'A{i:02}',region=region,map=region_by[region]['map'],kind=kind,target=target,subcategory=code,title=title,rubrics_i18n={'zh':{'criteria':zh},'en':{'criteria':en}},probe=probe,**kw)
tasks=[
 task(1,'market','offset','MarketBench','G1','Floating market bench','集市木凳整体悬在地面上方约 80 厘米，凳脚没有接触地面或其他支撑。','The market bench floats about 80 cm above the ground, with no support beneath its legs.',[-780,5470,80],offset=[0,0,80]),
 task(2,'courtyard','offset','CourtLion','G1','Floating stone lion','宅院门口左侧石狮整体悬空约 80 厘米，底座下方没有支撑。','The stone lion to the left of the residence entrance floats about 80 cm above its supporting ground.',[120,6770,80],offset=[0,0,80]),
 task(3,'tea_house','duplicate','TeaTable','G2','Intersecting tea tables','同一位置有两张木桌穿插重叠，桌面和桌腿互相穿入。','Two wooden tea tables intersect at the same location, with overlapping tabletops and legs.',[-1530,5520,120],offset=[25,0,0],yaw=18),
 task(4,'market','duplicate','MarketCanopy','G2','Overlapping stall frames','集市同一个摊位上叠着两套错位的棚架，立柱和顶棚互相穿插。','Two misaligned canopy frames overlap on one market stall, with intersecting posts and roofs.',[-380,5270,80],offset=[25,0,0],yaw=8),
 task(5,'tea_house','axis_scale','TeaBench','G3','Bench too tall for its table','茶馆木凳被竖向拉长到三倍，凳面高过配套桌面，无法按正常成人座椅使用。','The tea-house bench is stretched to three times its normal height; its seat is above the matching table and cannot serve as a normal adult seat.',[-1530,5520,120],scale=[1,1,3]),
 task(6,'market','axis_scale','MarketTable','G3','Table below seat height','集市木桌被竖向压缩到四分之一，桌面低于周围配套木凳的凳面，尺寸不满足用餐用途。','The market table is compressed to one quarter of its height, placing its tabletop below the surrounding matching seats.',[-780,5470,80],scale=[1,1,.25]),
 task(7,'market','no_collision','MarketTable','C1','Walk through a wooden table','人物可以走进并穿过可见的实体木桌；干净基准中的同一张桌子应阻挡人物。','The player can walk through the visible solid wooden table; the same table blocks the player in the clean baseline.',[-780,5570,80]),
 task(8,'tea_house','blocker','','C2','Invisible barrier in a clear passage','茶馆入口旁清晰可见的空地出现空气墙，人物无法穿过，现场没有对应的实体障碍。','An invisible barrier blocks an otherwise clear passage beside the tea-house entrance, with no visible object accounting for the obstruction.',[-1530,5520,120],position=[-1530,5420,120],extent=[90,8,95]),
 task(9,'market','basket_bounce','InteractiveBasket','C3','Basket keeps bouncing after a push','对准藤筐按一次 E 轻推；藤筐反复自行向上弹跳，未继续操作也不停止。','Aim at the wicker basket and press E to give it a gentle push; it repeatedly bounces upward without further input.',[-180,5570,80]),
 task(10,'courtyard','view_cull','CourtLion','V1','Stone lion disappears when centered','把左侧石狮移到视野正中央时，它突然消失；稍微转动视角后又出现。','The left stone lion disappears when centered in view and reappears when the viewing angle shifts slightly.',[120,6770,80],threshold=.99),
 task(11,'market','distance_cull','MarketCanopy','V1','Stall canopy disappears at a distance','从近处后退到几米外时，摊位的棚架突然消失，靠近后恢复；摊位仍在清晰可见范围内。','The stall canopy abruptly disappears a few metres away and returns when approached, despite remaining within a clear viewing distance.',[-380,5270,80],far_probe=[-180,5270,80],threshold=350),
 task(12,'tea_house','distance_scale','TeaBench','V2','Bench changes size with distance','同一张茶馆木凳在近处正常，稍微走远后外形突然放大为两倍，靠近又恢复。','The same tea-house bench abruptly doubles in visible size when viewed from farther away and returns to normal when approached.',[-1530,5520,120],far_probe=[-1530,5320,120],threshold=300,factor=2),
 task(13,'courtyard','shadow_offset','CourtLion','V3','Detached stone-lion shadow','左侧石狮本体位置正常，但其阴影被平移约 2 米，与石狮的位置和当前光照不一致。','The left stone lion stays in place while its shadow is displaced by about two metres, inconsistent with the object and lighting.',[120,6770,80],offset=[0,-180,0]),
 task(14,'market','return_hide','InteractiveBasket','T1','Basket disappears after returning','先看清藤筐，离开并背向它，再回到原处；未进行 E 操作，藤筐却永久消失。','Observe the wicker basket, walk away while facing away, then return; it has disappeared without being picked up or removed.',[-180,5570,80],far_probe=[-480,4870,80],near=260,far=500),
 task(15,'tea_house','return_move','TeaBench','T2','Bench moves between visits','先观察木凳，离开并背向它，再返回；同一张凳子在无人搬动的情况下平移了约 80 厘米。','Observe the bench, leave while facing away, then return; it has shifted about 80 cm without anyone moving it.',[-1530,5520,120],far_probe=[-1530,5320,120],near=200,far=300,offset=[0,-80,0]),
 task(16,'courtyard','return_material','CourtLantern','T2','Lantern changes colour between visits','先观察门口红灯笼，离开并背向它，再返回；同一个灯笼无原因地变成蓝色。','Observe the red entrance lantern, leave while facing away, then return; the same lantern has changed to blue without a cause.',[620,6970,80],far_probe=[620,6470,80],near=300,far=550),
 task(17,'courtyard','door_revisit','InteractiveDoor','T3','Entrance door opens by itself','先观察关闭的门扇，离开并背向大门，再返回；没有按 E，门扇却自行打开。','Observe the closed door leaf, walk away while facing away, then return; the door opens without pressing E.',[520,7070,80]),
 task(18,'tea_house','semantic_add','TeaTable','S1','Table blocks the tea-house passage','一张落地木桌被摆到茶馆原本可行走的狭窄通道中央，阻挡正常通行。','A grounded wooden table is placed across the tea house’s narrow walking passage, obstructing its normal use.',[-1530,5520,120],position=[-1530,5420,20],yaw=0),
 task(19,'courtyard','semantic_add','CourtLion','S1','Stone lion blocks the doorway','石狮被摆在宅院打开的半扇门通道中，占据入口，人物无法从该门口正常进出。','A stone lion is placed in the open half of the residence doorway, occupying the entrance and preventing normal passage.',[420,6970,80],position=[435,7220,65],yaw=180),
 task(20,'market','semantic_add','ModernVendingSource','S3','Modern vending machine in an ancient market','中国古代集市中出现带现代商品展示和电子面板的自动售货机，与场景时代设定冲突。','A modern vending machine with product displays and an electronic panel appears in the ancient Chinese market, conflicting with its historical setting.',[-180,5570,80],position=[-350,5900,-12],yaw=270)
]
# Repair the authored visible road plane: it had no simple collision.
ground_mesh=unreal.load_asset('/Game/AncientChinese/Mesh/floor/SM_floor_02')
ground_mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
unreal.EditorAssetLibrary.save_loaded_asset(ground_mesh)
# Physics must wait for asynchronous mesh compilation before editor traces.
assert level.load_level('/Game/Auditor/AncientCity/Playtest')
world=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(world)
ignore=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.PlayerStart)]
def safe_point(desired,reg):
 candidates=sorted([(dx,dy) for dx in range(-150,151,25) for dy in range(-150,151,25)],key=lambda p:p[0]**2+p[1]**2)
 for dx,dy in candidates:
  x,y=desired[0]+dx,desired[1]+dy
  if not(reg['bounds_min'][0]+40<x<reg['bounds_max'][0]-40 and reg['bounds_min'][1]+40<y<reg['bounds_max'][1]-40):continue
  hit=unreal.SystemLibrary.line_trace_single_by_profile(world,vec([x,y,300]),vec([x,y,-200]),'BlockAll',False,ignore,unreal.DrawDebugTrace.NONE,True)
  data=hit.to_tuple()
  if not data[0] or data[5].z>40:continue
  component=data[10]
  if isinstance(component,unreal.StaticMeshComponent):
   mesh=component.get_editor_property('static_mesh')
   if mesh and any(k in mesh.get_name().lower() for k in ['chair','table','stall','lion','basket','lantern']):continue
  p=[x,y,data[5].z+100]
  collision=unreal.SystemLibrary.capsule_trace_single_by_profile(world,vec(p),vec([x,y,p[2]+1]),30,90,'Pawn',False,ignore,unreal.DrawDebugTrace.NONE,True)
  if not collision or not collision.to_tuple()[0]:return p
 raise RuntimeError('No clear ground near '+str(desired)+' in '+reg['id'])
for reg in regions:
 reg['spawn']=safe_point(reg['spawn'],reg)
 reg['traversal_points']=[safe_point(v,reg) for v in reg['traversal_points']]
 reg['boundary_test_start']=safe_point(reg['boundary_test_start'],reg)
for t in tasks:
 reg=region_by[t['region']]
 for key in ['probe','far_probe']:
  if key in t:t[key]=safe_point(t[key],reg)
 if t['kind']=='semantic_add':t['review_aim']=[t['position'][0],t['position'][1],t['position'][2]+90]
rubric_file=ENV/'rubrics.bilingual.json'
if rubric_file.exists():
 translations=json.loads(rubric_file.read_text())
 for t in tasks:t['rubrics_i18n']=translations[t['id']]
(ENV/'regions.json').write_text(json.dumps({'source_map':'/Game/AncientChinese/map/Demomap','regions':regions},ensure_ascii=False,indent=2))
(ENV/'tasks.json').write_text(json.dumps({'taxonomy_version':'user-2026-09-11-motion','tasks':tasks},ensure_ascii=False,indent=2))
# Shared authored material for the revisit-colour task.
matpath='/Game/Auditor/AncientCity/M_ReviewBlue';mat=unreal.load_asset(matpath)
if not mat:
 mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_ReviewBlue','/Game/Auditor/AncientCity',unreal.Material,unreal.MaterialFactoryNew())
 color=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector);color.set_editor_property('constant',unreal.LinearColor(.015,.07,.7,1));unreal.MaterialEditingLibrary.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR);unreal.MaterialEditingLibrary.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat)
reports=[]
for region in regions:
 assert level.load_level('/Game/Auditor/AncientCity/Playtest');world=editor.get_editor_world()
 assert unreal.EditorLoadingAndSavingUtils.save_map(world,region['map']);assert level.load_level(region['map']);world=editor.get_editor_world()
 tagged={}
 for a in list(actors.get_all_level_actors()):
  label=a.get_actor_label()
  if label in {k[0] for k in aliases}:
   for i,c in enumerate(a.get_components_by_class(unreal.StaticMeshComponent)):
    mesh=c.get_editor_property('static_mesh')
    if not mesh:continue
    copy=spawn(unreal.StaticMeshActor);copy.set_mobility(unreal.ComponentMobility.MOVABLE);m=copy.static_mesh_component;m.set_static_mesh(mesh)
    for j in range(c.get_num_materials()):m.set_material(j,c.get_material(j))
    m.set_collision_profile_name(c.get_collision_profile_name());m.set_collision_enabled(c.get_collision_enabled());copy.set_actor_transform(c.get_world_transform(),False,True)
    alias=aliases.get((label,c.get_name()),'Scenery_'+label+'_'+str(i));copy.set_actor_label('Ancient_'+alias);copy.tags=[unreal.Name('auditor_actor:'+alias)];tagged[alias]=copy
   actors.destroy_actor(a)
  elif label=='SM_doorstonelion_SM_StoneLion_01_low':a.tags=list(a.tags)+[unreal.Name('auditor_actor:CourtLion')];tagged['CourtLion']=a
  elif isinstance(a,(unreal.PlayerStart,unreal.AuditorRegion,unreal.AuditorTasks)):actors.destroy_actor(a)
 # Basket and hidden modern source use authored meshes; no substitute geometry.
 if region['id']=='market':
  b=spawn(unreal.StaticMeshActor,[-320,5580,-12]);b.set_actor_label('Ancient_InteractiveBasket');b.static_mesh_component.set_static_mesh(unreal.load_asset('/Game/AncientChinese/Mesh/asset/SM_WickerBasket_01'));b.tags=[unreal.Name('auditor_actor:InteractiveBasket')]
  origin,extent=b.get_actor_bounds(False);b.add_actor_world_offset(vec([0,0,-12-(origin.z-extent.z)]),False,True);tagged['InteractiveBasket']=b
  modern=spawn(unreal.StaticMeshActor,[-20000,-20000,0]);modern.static_mesh_component.set_static_mesh(unreal.load_asset('/Game/Subway_Station/Meshes/SM_Vending_Machine'));modern.set_actor_hidden_in_game(True);modern.set_actor_enable_collision(False);modern.tags=[unreal.Name('auditor_actor:ModernVendingSource')];tagged['ModernVendingSource']=modern
 else:
  # Door interaction belongs only to the residence scene.
  if region['id']!='courtyard':tagged['InteractiveDoor'].tags=[]
  # Avoid retaining a hidden modern asset in non-market maps.
 if region['id']!='courtyard':tagged['InteractiveDoor'].tags=[]
 reg=spawn(unreal.AuditorRegion);reg.set_actor_label('Ancient_'+region['name'])
 for name,key in [('region_name','name'),('bounds_min','bounds_min'),('bounds_max','bounds_max'),('spawn_location','spawn'),('boundary_test_start','boundary_test_start'),('boundary_test_direction','boundary_test_direction')]:reg.set_editor_property(name,vec(region[key]) if isinstance(region[key],list) else region[key])
 reg.set_editor_property('spawn_rotation',unreal.Rotator(pitch=0,yaw=region['yaw'],roll=0));reg.set_editor_property('traversal_points',[vec(v) for v in region['traversal_points']]);reg.set_editor_property('region_maps',[r['map'] for r in regions]);spawn(unreal.PlayerStart,region['spawn'])
 controller=spawn(unreal.AuditorTasks);controller.set_editor_property('catalog_json',json.dumps({'tasks':tasks},ensure_ascii=False));controller.set_editor_property('error_material',mat)
 world.get_world_settings().set_editor_property('default_game_mode',unreal.load_class(None,'/Script/AuditorRuntime.AuditorGameMode'))
 import sys
 if str(ROOT/'scripts') not in sys.path:sys.path.insert(0,str(ROOT/'scripts'))
 from npc_policy import apply_npc_policy
 apply_npc_policy(region['id'])
 assert level.save_current_level()
 reports.append({'region':region['id'],'map':region['map'],'actors':len(actors.get_all_level_actors()),'targets':{k:{'location':xyz(a.get_actor_location()),'center':xyz(a.get_actor_bounds(False)[0]),'extent':xyz(a.get_actor_bounds(False)[1])} for k,a in tagged.items()}})
(OUT/'map-setup.json').write_text(json.dumps(reports,indent=2));print('ANCIENT_REGIONS_CREATED',len(regions),len(tasks))
