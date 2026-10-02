"""Author two bounded review maps from the verified Medieval Village source."""
import unreal,json,math,collections
from pathlib import Path
ROOT=Path('/home/ubuntu/unreal-auditor/medieval-workspace');ENV=ROOT/'environments/medieval-village';ENV.mkdir(parents=True,exist_ok=True)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
car=json.loads((ENV/'modern-props.json').read_text())['car']
vec=lambda p:unreal.Vector(*p)
xyz=lambda p:list(p.to_tuple())
def spawn(cls,p=(0,0,0)):return unreal.AuditorSceneSetup.spawn_editor_actor(editor.get_editor_world(),cls,unreal.Transform(location=vec(p)))
regions=[dict(id='market',name='Market street',name_zh='市场街',map='/Game/Auditor/MedievalVillage/Market',bounds_min=[42550,25500,-3950],bounds_max=[44850,27350,-2000],spawn=[43500,26600,-3647.337],yaw=-105),dict(id='windmill',name='Windmill courtyard',name_zh='风车庭院',map='/Game/Auditor/MedievalVillage/Windmill',bounds_min=[39500,29000,-3950],bounds_max=[42050,31600,-1800],spawn=[39800,30200,-3605.17],yaw=-47)]
# Actor names are unique; source labels are not.
names={'market':{'Sacks':'StaticMeshActor_341','MarketCrates':'StaticMeshActor_357','MarketBarrel':'StaticMeshActor_351','Bench':'StaticMeshActor_46','InteractiveBasket':'StaticMeshActor_367','Chair':'StaticMeshActor_379','EastBarrel':'StaticMeshActor_416','Bread':'StaticMeshActor_323'},'windmill':{'MillCrates':'StaticMeshActor_1047','Cart':'StaticMeshActor_802','MillBarrel':'StaticMeshActor_1594','Planks':'StaticMeshActor_1332'}}
specs=[
('market','offset','Sacks','G1','Unsupported grain sacks','装粮食的麻袋悬在地面上方，下方没有支撑。正常情况下麻袋应落在地面上。','The grain sacks float above the ground without support. They should rest on the ground.',dict(offset=[0,0,85])),
('market','duplicate','MarketCrates','G2','Intersecting market crates','两组木箱相互穿插，实体表面重叠。正常情况下木箱应各自占据独立空间。','Two sets of crates intersect with overlapping solid surfaces. Each crate should occupy its own space.',dict(offset=[50,25,0],yaw=45)),
('market','axis_scale','MarketBarrel','G3','Stretched market barrel','木桶被竖向拉长为原来的两倍半，高宽比例异常。正常情况下它应保持与附近同类木桶一致的比例。','The barrel is stretched to two and a half times its height, distorting its proportions. Its proportions should match nearby barrels of the same type.',dict(scale=[1,1,2.5])),
('market','no_collision','Bench','C1','Walk through wooden bench','人物可以穿过可见的木长凳。正常情况下实体长凳应阻挡人物。','The player can walk through the visible wooden bench. A solid bench should block the player.',{}),
('market','blocker','','C2','Invisible market barrier','市场空旷的通道出现空气墙，人物无法穿过。正常情况下没有障碍物的通道应允许通行。','An invisible barrier blocks an open part of the market aisle. An unobstructed aisle should allow passage.',dict(position=[43800,26700,-3647.337],extent=[10,150,95])),
('market','basket_bounce','InteractiveBasket','C3','Basket repeatedly rebounds','靠近空地上的篮筐按 E 轻推后，篮筐持续反复向上弹跳。正常情况下轻推应使它沿地面短距离移动并停下。','After an E-key push, the basket repeatedly bounces upward. A gentle push should move it a short distance along the ground and let it settle.',{}),
('market','distance_cull','Chair','V1','Chair vanishes with distance','后退几米时木椅突然消失，靠近后又出现。正常情况下未被遮挡的近处木椅应持续可见。','The chair suddenly disappears a few metres away and returns on approach. A nearby unobstructed chair should remain visible.',dict(threshold=500)),
('market','distance_scale','EastBarrel','V2','Barrel changes size with distance','后退几米时同一个木桶突然放大，靠近后恢复。正常情况下观察距离不应改变木桶的实际尺寸。','The same barrel abruptly grows at a greater viewing distance and returns to normal nearby. Viewing distance should not change its actual size.',dict(threshold=550,factor=2)),
('market','shadow_offset','Bench','V3','Detached bench shadow','长凳位置正常，但阴影与长凳本体错开。正常情况下阴影应与长凳的位置及日照方向一致。','The bench remains in place while its shadow is displaced. Its shadow should agree with its position and the sunlight.',dict(offset=[170,0,0])),
('market','return_hide','Bread','T1','Bread disappears between visits','看清摊位上的面包，背向它走远再返回后，面包无原因地消失。正常情况下未被取走的面包应仍在原处。','Observe the bread, walk away facing away, and return; it has disappeared without a cause. Bread that nobody took should remain in place.',dict(near=550,far=800)),
('windmill','offset','MillCrates','G1','Unsupported mill crates','庭院里的木箱悬在地面上方，没有支撑。正常情况下木箱应接触地面。','The courtyard crates float above the ground without support. They should rest on the ground.',dict(offset=[0,0,85])),
('windmill','duplicate','Cart','G2','Intersecting wooden carts','两辆木推车相互穿插，车轮和车架重叠。正常情况下实体推车不应互相穿透。','Two wooden carts intersect, with overlapping wheels and frames. Solid carts should not penetrate one another.',dict(offset=[35,20,0],yaw=25)),
('windmill','return_move','MillBarrel','T2','Barrel moves between visits','看清木桶，背向它走远再返回后，木桶在无人搬动时换了位置。正常情况下静止木桶应保持原来的位置。','Observe the barrel, walk away facing away, and return; it has moved without being touched. A stationary barrel should retain its position.',dict(near=550,far=800,offset=[100,0,0])),
('windmill','windmill_reverse','','T3','Windmill reverses after looking away','看清正在转动的风车叶片，转身再看时叶片无原因地反向转动。正常情况下没有操作或风向变化时应保持原来的转动方向。','Observe the turning windmill, look away, and look back; the blades reverse without a cause. Without an intervention or wind change, their direction should remain consistent.',dict(review_aim=[40271.5,29638.1,-2738.9])),
('windmill','view_cull','MillCrates','V1','Crates disappear in central view','把木箱移到视野中央时它们消失，偏转视角后又出现。正常情况下未被遮挡的木箱不应随视角突然消失。','The crates disappear at the centre of view and return when the view shifts. Unobstructed crates should not abruptly vanish with the viewing angle.',dict(threshold=.99)),
('windmill','return_material','Planks','T2','Planks change material between visits','看清木板，背向它们走远再返回后，同一组木板无原因地变成蓝色。正常情况下无人修改的木板应保持原来的材质。','Observe the planks, walk away facing away, and return; the same planks have turned blue without a cause. Their material should remain unchanged.',dict(near=550,far=800)),
('windmill','semantic_add','Cart','S1','Cart blocks windmill doorway','木推车被横放在风车木门前，阻碍门口的正常出入。正常情况下门前应保持畅通，推车应停放在旁边。','A cart is placed across the windmill doorway, obstructing access. The doorway should remain clear, with carts parked beside it.',dict(position=[40000,29950,-3739],yaw=0)),
('windmill','semantic_add','ModernCar','S3','Automobile parked beyond the medieval courtyard','中世纪村庄庭院远处停着一辆现代汽车。正常情况下这里的交通工具应符合中世纪的时代背景。','A modern automobile is parked in the distance beyond the medieval courtyard. Vehicles here should fit the medieval era.',dict(position=[*car['position'][:2],-3740],yaw=car['yaw']))]
mat=unreal.load_asset('/Game/Auditor/MedievalVillage/M_ReviewBlue')
if not mat:
 mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_ReviewBlue','/Game/Auditor/MedievalVillage',unreal.Material,unreal.MaterialFactoryNew());c=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector);c.set_editor_property('constant',unreal.LinearColor(.015,.07,.7,1));unreal.MaterialEditingLibrary.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR);unreal.MaterialEditingLibrary.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat)
def rubric(text,lang):
 sep='。' if lang=='zh' else '. ';first,found,last=text.partition(sep);assert found and last.strip()
 return dict(criteria=first+('。' if lang=='zh' else '.'),expected=last.strip(),steps='靠近目标并观察；按异常描述改变视角、距离或进行交互。' if lang=='zh' else 'Approach the target and observe; follow the described view, distance or interaction trigger.')
tasks=[];reports=[]
for region in regions:
 assert level.load_level('/Game/Medieval_Village/Demo/Maps/Medieval_Village');w=editor.get_editor_world();assert unreal.EditorLoadingAndSavingUtils.save_map(w,region['map']);assert level.load_level(region['map']);w=editor.get_editor_world();tagged={};removed=[]
 for a in list(actors.get_all_level_actors()):
  if isinstance(a,(unreal.PlayerStart,unreal.Pawn,unreal.AuditorRegion,unreal.AuditorTasks)):
   actors.destroy_actor(a);continue
  if isinstance(a,unreal.StaticMeshActor) and not a.static_mesh_component.get_editor_property('visible'):
   removed.append(a.get_name());actors.destroy_actor(a);continue
  if a.get_name() in names[region['id']].values():
   alias=next(k for k,v in names[region['id']].items() if v==a.get_name());a.tags=list(a.tags)+[unreal.Name('auditor_actor:'+alias)];tagged[alias]=a
  if a.get_name()=='wind_mill_turbine_BP_C_0':a.tags=list(a.tags)+[unreal.Name('auditor_windmill')]
 unreal.AuditorSceneSetup.prepare_editor_collision(w)
 def floor(p):
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,vec([p[0],p[1],-3580]),vec([p[0],p[1],-4000]),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  if not h or not h.to_tuple()[0]:raise RuntimeError('No floor '+str(p))
  return h.to_tuple()[5].z
 def seat(alias,p):
  a=tagged[alias];o,e=a.get_actor_bounds(False);bottom=o.z-e.z-a.get_actor_location().z;a.set_actor_location(vec([p[0],p[1],floor(p)-bottom]),False,False)
 if region['id']=='market':
  for alias,pos in {'InteractiveBasket':[43400,26700],'Sacks':[44200,26900],'MarketCrates':[43200,26300],'MarketBarrel':[44000,27000],'Bench':[43100,27150],'Chair':[43700,26400],'EastBarrel':[44400,26400]}.items():seat(alias,pos)
 else:
  # Bring workshop supplies outside the closed tower into the usable courtyard.
  seat('MillCrates',[41300,31150]);seat('MillBarrel',[41000,30300]);seat('Planks',[41700,30900])
  a=spawn(unreal.StaticMeshActor,[0,0,-10000]);a.static_mesh_component.set_static_mesh(unreal.load_asset(car['mesh']));a.tags=[unreal.Name('auditor_actor:ModernCar')];a.set_actor_hidden_in_game(True);a.set_actor_enable_collision(False);tagged['ModernCar']=a
 # Reachable probes come exclusively from the main ground-connected component.
 grid=json.loads((ROOT/'out/walk-grid.json').read_text())[region['id']];points=grid['points'];edges=grid['edges'];left=set(points);comps=[]
 while left:
  stack=[left.pop()];c=set(stack)
  while stack:
   for n in edges[stack.pop()]:
    if n in left:left.remove(n);c.add(n);stack.append(n)
  comps.append(c)
 connected=max(comps,key=len)
 def clear(p,q):
  h=unreal.SystemLibrary.capsule_trace_single_by_profile(w,vec(p),vec(q),30,90,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
  return not h or not h.to_tuple()[0]
 candidates=[points[k] for k in connected if clear(points[k],[points[k][0],points[k][1],points[k][2]+.1])]
 def visible(p,center,a):
  h=unreal.SystemLibrary.line_trace_single_by_profile(w,vec([p[0],p[1],p[2]+70]),vec(center),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
  return not h or not h.to_tuple()[0] or (a and h.to_tuple()[10] in a.get_components_by_class(unreal.PrimitiveComponent))
 def probe(center,a,lo=260,hi=470,prefer=None):
  ps=[p for p in candidates if lo<math.dist(p[:2],center[:2])<hi and visible(p,center,a)]
  if not ps:raise RuntimeError('No visible reachable probe '+str(center))
  return min(ps,key=lambda p:math.dist(p[:2],(prefer or region['spawn'])[:2]))
 region['spawn']=min(candidates,key=lambda p:math.dist(p,region['spawn']))
 # Exact swept route from the spawn, not just disconnected clear endpoints.
 sk=min(connected,key=lambda k:math.dist(points[k],region['spawn'])); route=[points[sk]];prev=None;key=sk
 for i in range(5):
  ns=[n for n in edges[key] if n!=prev and clear(points[key],points[n])]
  if not ns:break
  nxt=max(ns,key=lambda n:math.dist(points[n],route[0]));route.append(points[nxt]);prev,key=key,nxt
 region['traversal_points']=route+list(reversed(route[:-1]))
 boundary=[]
 for p in candidates:
  for axis,direction,limit in [(0,-1,region['bounds_min'][0]),(0,1,region['bounds_max'][0]),(1,-1,region['bounds_min'][1]),(1,1,region['bounds_max'][1])]:
   dist=abs(p[axis]-limit)
   if 80<dist<200:
    q=p.copy();q[axis]=limit-direction*35
    if clear(p,q):d=[0,0,0];d[axis]=direction;boundary.append((math.dist(p,region['spawn']),p,d))
 assert boundary
 _,region['boundary_test_start'],region['boundary_test_direction']=min(boundary)
 for idx,(rid,kind,target,code,title,zh,en,extra) in enumerate(specs,1):
  if rid!=region['id']:continue
  a=tagged.get(target);center=xyz(a.get_actor_bounds(False)[0]) if a else extra.get('review_aim',extra.get('position'));extra=extra.copy()
  if kind=='semantic_add':
   pos=extra['position'];o,e=a.get_actor_bounds(False);bottom=o.z-e.z-a.get_actor_location().z;pos[2]=floor(pos)-bottom;center=[pos[0],pos[1],floor(pos)+100];extra['review_aim']=center
  if kind=='blocker':extra['review_aim']=center
  if kind=='windmill_reverse':p=region['spawn']
  else:p=probe(center,None if kind=='semantic_add' else a)
  if kind=='basket_bounce':p=probe(center,a,150,220)
  fixed={1:[43800,26900],2:[43200,26600],3:[43700,27000]}
  if idx in fixed:
   p=min(candidates,key=lambda q:math.dist(q[:2],fixed[idx]));assert math.dist(p[:2],fixed[idx])<1 and visible(p,center,a)
  t=dict(id=f'MV{idx:02}',region=rid,map=region['map'],kind=kind,target=target,subcategory=code,title=title,probe=p,rubrics_i18n={'zh':rubric(zh,'zh'),'en':rubric(en,'en')},**extra)
  if kind in ['return_move','return_hide','return_material','distance_scale','distance_cull']:
   t['far_probe']=probe(center,a,920,1150,prefer=p)
  tasks.append(t)
 reg=spawn(unreal.AuditorRegion);reg.set_actor_label('Medieval_'+region['id'])
 for name,key in [('region_name','name'),('bounds_min','bounds_min'),('bounds_max','bounds_max'),('spawn_location','spawn'),('boundary_test_start','boundary_test_start'),('boundary_test_direction','boundary_test_direction')]:reg.set_editor_property(name,vec(region[key]) if isinstance(region[key],list) else region[key])
 reg.set_editor_property('spawn_rotation',unreal.Rotator(yaw=region['yaw']));reg.set_editor_property('traversal_points',[vec(p) for p in region['traversal_points']]);reg.set_editor_property('region_maps',[r['map'] for r in regions]);spawn(unreal.PlayerStart,region['spawn']);w.get_world_settings().set_editor_property('default_game_mode',unreal.load_class(None,'/Script/AuditorRuntime.AuditorGameMode'));assert level.save_current_level()
 reports.append(dict(region=region['id'],removed_invisible_markers=removed,connected_ground_samples=len(connected),targets={k:dict(name=a.get_name(),location=xyz(a.get_actor_location()),center=xyz(a.get_actor_bounds(False)[0])) for k,a in tagged.items()}))
 print('MEDIEVAL_REGION_CREATED',region['id'],flush=True)
tasks.sort(key=lambda t:t['id'])
for region in regions:
 assert level.load_level(region['map']);a=spawn(unreal.AuditorTasks);a.set_editor_property('catalog_json',json.dumps({'tasks':tasks},ensure_ascii=False));a.set_editor_property('error_material',mat);assert level.save_current_level()
(ENV/'regions.json').write_text(json.dumps({'regions':regions},ensure_ascii=False,indent=2));(ENV/'tasks.json').write_text(json.dumps({'taxonomy_version':'user-2026-09-12-scene-semantics','tasks':tasks},ensure_ascii=False,indent=2));(ROOT/'out/map-setup.json').write_text(json.dumps(reports,indent=2));print('MEDIEVAL_MAPS_PASS',len(tasks),flush=True)

# Apply all three final anachronisms after the common region setup.
exec(compile((ROOT/'scripts/author_modern_cases.py').read_text(), str(ROOT/'scripts/author_modern_cases.py'), 'exec'), {'__name__':'__main__'})
