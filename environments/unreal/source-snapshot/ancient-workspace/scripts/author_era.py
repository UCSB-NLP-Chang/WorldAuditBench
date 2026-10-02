"""Append four isolated S3 cases without regenerating the authored Ancient scenes."""
import json,math,subprocess
from pathlib import Path
import unreal
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');env=r/'environments/ancient-chinese-city';out=r/'out/era-v1'
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
catalog=json.loads((env/'tasks.json').read_text());tasks={t['id']:t for t in catalog['tasks']};regions=json.loads((env/'regions.json').read_text())['regions'];report=[]
specs=[
 dict(id='A21',region='tea_house',target='EraDrinkCan',mesh='/Game/GameReady3D/AtmosphericFarmhouse/StaticMesh/Props/SM_SM_Can_V3',center=[-1664,5685],ray_z=115,yaw=0,scale=1,probe=[-1530,5520,120.125],title='Modern food tin on an ancient tea table',zh=['古代茶馆的木桌上摆着一罐带现代印刷包装的食品罐头。','正常情况下，桌上的食品及其包装应符合古代茶馆的时代背景。'],en=['A food tin with modern printed packaging sits on a wooden table in the ancient tea house.','Food and its packaging should fit the historical era of the tea house.']),
 dict(id='A22',region='market',target='EraNewspaper',mesh='/Engine/BasicShapes/Plane',material='/Game/Auditor/AncientCity/EraProps/M_ModernNewspaper',center=[405,5900],ray_z=160,yaw=90,roll=90,scale=[.62,.86,1],probe=[300,5900,88],wall=True,title='Modern newspaper on an ancient market wall',zh=['古代中国集市的墙上贴着一张刊有智能手机和地铁新闻的现代报纸。','正常情况下墙上文字和图像的内容应符合古代城市的时代背景。'],en=['A modern newspaper reporting on smartphones and metro trains is pasted to a wall in the ancient Chinese market.','The content of writing and images on the walls should fit the era of the ancient city.']),
 dict(id='A23',region='courtyard',target='EraCamera',mesh='/Game/Meshes/SM_VideoCamera_01',center=[880,7000],ray_z=100,yaw=180,scale=1,probe=[920,6770,88],title='Video camera at an ancient residence entrance',zh=['古代中国宅院入口旁架着一台现代摄像机。','正常情况下宅院门前的设备应符合古代的时代背景。'],en=['A modern video camera stands beside the entrance to an ancient Chinese residence.','Equipment at the entrance should fit the historical era of the residence.']),
 dict(id='A24',region='tea_house',target='EraAirConditioner',mesh='/Game/Meshes/SM_AirConditioner01',center=[-1900,5550],ray_z=100,yaw=90,scale=.7,probe=[-1530,5520,120.125],title='Air-conditioning equipment in an ancient tea house',zh=['古代中国茶馆里出现了带风扇格栅的现代空调机组。','正常情况下茶馆的设施应符合古代城市的时代背景。'],en=['A modern air-conditioning unit with fan grilles stands in the ancient Chinese tea house.','Facilities at the tea house should fit the era of the ancient city.']),
]
for reg in regions:
 assert level.load_level(reg['map']);world=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(world)
 for old in list(actors.get_all_level_actors()):
  if unreal.Name('auditor_actor:EraSolarPanel') in old.tags:actors.destroy_actor(old)
 for s in specs:
  if s['region']!=reg['id']:continue
  matches=[a for a in actors.get_all_level_actors() if unreal.Name('auditor_actor:'+s['target']) in a.tags];assert len(matches)<=1
  a=matches[0] if matches else unreal.AuditorSceneSetup.spawn_editor_actor(world,unreal.StaticMeshActor,unreal.Transform(location=unreal.Vector(0,0,-10000)))
  mesh=unreal.load_asset(s['mesh']);assert mesh
  a.static_mesh_component.set_static_mesh(mesh);a.static_mesh_component.set_collision_profile_name('BlockAll');a.set_actor_scale3d(unreal.Vector(*(s['scale'] if isinstance(s['scale'],list) else [s['scale']]*3)));a.set_actor_rotation(unreal.Rotator(yaw=s['yaw'],roll=s.get('roll',0)),False)
  if s.get('material'):a.static_mesh_component.set_material(0,unreal.load_asset(s['material']))
  a.tags=[unreal.Name('auditor_actor:'+s['target'])];a.set_actor_hidden_in_game(True);a.set_actor_enable_collision(False)
  a.set_actor_location(unreal.Vector(0,0,-10000),False,False);b=a.get_actor_bounds(False)
  x,y=s['center']
  if s.get('wall'):
   hit=unreal.SystemLibrary.line_trace_single_by_profile(world,unreal.Vector(x-30,y,160),unreal.Vector(x+30,y,160),'BlockAll',True,[a],unreal.DrawDebugTrace.NONE,True)
   assert hit and hit.to_tuple()[0],s['id'];point=hit.to_tuple()[5];normal=hit.to_tuple()[6];assert normal.x<-.99
   position=list((point+normal*.2).to_tuple());floor=160
   # All corners must be supported by the same solid wall, including above eye level.
   for dy in [-30,0,30]:
    for dz in [-42,0,42]:
     h=unreal.SystemLibrary.line_trace_single_by_profile(world,unreal.Vector(x-3,y+dy,160+dz),unreal.Vector(x+3,y+dy,160+dz),'BlockAll',True,[a],unreal.DrawDebugTrace.NONE,True)
     assert h and h.to_tuple()[0] and abs(h.to_tuple()[5].x-point.x)<.4,('paper corner lacks wall',dy,dz)
  else:
   hit=unreal.SystemLibrary.line_trace_single_by_profile(world,unreal.Vector(x,y,s['ray_z']),unreal.Vector(x,y,-100),'BlockAll',True,[a],unreal.DrawDebugTrace.NONE,True)
   assert hit and hit.to_tuple()[0],s['id'];floor=hit.to_tuple()[5].z
   position=[x-b[0].x,y-b[0].y,floor-(b[0].z-b[1].z+10000)]
  rubrics={lang:dict(criteria=s[lang][0],expected=s[lang][1],steps='靠近并从不同角度观察。' if lang=='zh' else 'Approach and inspect from different viewpoints.') for lang in ['en','zh']}
  t={k:s[k] for k in ['id','region','target','yaw','title','probe']};t.update(map=reg['map'],kind='semantic_add',subcategory='S3',position=position,review_aim=[x,y,floor+b[1].z],rubrics_i18n=rubrics)
  if s.get('wall'):t.update(roll=s['roll'],support_point=list(point.to_tuple()),support_normal=list(normal.to_tuple()),support_gap=.2,review_aim=list(point.to_tuple()))
  tasks[t['id']]=t;report.append(dict(**t,mesh=s['mesh'],scale=s['scale'],support_actor=hit.to_tuple()[9].get_name(),floor=floor))
 assert level.save_current_level()
catalog['tasks']=sorted(tasks.values(),key=lambda t:t['id']);assert len(catalog['tasks'])==24
(env/'tasks.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
concise=json.loads((env/'concise-rubrics.json').read_text())
for s in specs:concise[s['id']]={lang:dict(criteria=s[lang][0],expected=s[lang][1]) for lang in ['en','zh']}
(env/'concise-rubrics.json').write_text(json.dumps(concise,ensure_ascii=False,indent=2))
for reg in regions:
 assert level.load_level(reg['map']);controllers=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks)];assert len(controllers)==1
 controllers[0].set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert level.save_current_level()
# Preserve the current user-approved scene introductions, then extend membership.
live=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip())
allscenes=json.loads((live/'review-scene-descriptions.json').read_text())
maps={reg['map'] for reg in regions};scenes=[s for s in allscenes['scenes'] if s['map'] in maps];assert len(scenes)==3
scene_copy={'Market': {'en': 'A market street in an ancient Chinese city, lined with wooden stalls, tables, benches and paper umbrellas. The furniture is fixed; loose paper umbrellas and the wicker basket can be pushed.', 'zh': '这是一条中国古代城市的集市街道，两侧摆有木制摊位、桌椅和纸伞。桌椅为固定陈设，散放的纸伞和藤筐可以推动。'}, 'TeaHouse': {'en': 'A tea house in an ancient Chinese city, furnished with wooden tables, benches and hanging lanterns. Its fixed furnishings surround the room and entrance passage.', 'zh': '这是一间中国古代城市的茶馆，摆有木桌、长凳，挂有灯笼。家具与灯笼为固定陈设，室内与入口之间留有通道。'}, 'Courtyard': {'en': 'A residence entrance in an ancient Chinese city, with stone lions, hanging lanterns and two wooden door leaves, one open and one closed. The decorations are fixed, and the two door leaves open and close independently.', 'zh': '这是中国古代城市的一处宅院入口，设有石狮、悬挂灯笼和两扇木门，初始一开一关。石狮与灯笼为固定陈设，两扇木门可以分别开关。'}}
for scene in scenes:scene['description']=scene_copy[scene['map'].split('/')[-1]]
for s in scenes:s['task_ids']=list(dict.fromkeys(s['task_ids']+[t['id'] for t in catalog['tasks'] if t['map']==s['map']]))
(env/'scene-descriptions.json').write_text(json.dumps(dict(scenes=scenes),ensure_ascii=False,indent=2))
(out/'authored-cases.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('ERA_AUTHORED',[t['id'] for t in report],flush=True)

# A24 uses the subsequently approved Fab household condenser.
import runpy
runpy.run_path(str(r/"scripts/author_ac.py"), run_name="__main__")
