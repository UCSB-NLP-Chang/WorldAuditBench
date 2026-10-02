import unreal,json,shutil
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor');w=r/'subway-workspace/s20';catpath=r/'subway-workspace/environments/subway/tasks.json';catalog=json.loads(catpath.read_text());regs=json.loads((catpath.parent/'regions.json').read_text())['regions']
assert not any(t['id']=='S20' for t in catalog['tasks'])
shutil.copy2(catpath,w/'tasks.before.json')
recipe=dict(id='S20',region='platform',map='/Game/Auditor/Subway/Platform',category='semantic',subcategory='S1',title='地铁站台候车区停着一辆私家车',kind='semantic_add',target='PrivateCarTemplate',position=[1500,1660,0.585220933],yaw=0,probe=[1050,1810,100],review_aim=[1500,1660,75],expected_behavior='地铁站台候车区供乘客候车，不应停放普通私家车。',observable_failure='一辆正常尺寸的普通轿车停在站台候车区内。',trigger='查看候车区里的轿车及周围的站台设施。',reset='重置任务恢复初始状态；切回正常场景后车辆消失。',rubrics_i18n={'zh':{'criteria':'一辆普通私家车停在地铁站台候车区内。','expected':'地铁站台候车区供乘客候车，不应停放普通私家车。','steps':'查看候车区里的轿车及周围的站台设施。'},'en':{'criteria':'An ordinary private passenger car is parked in the subway platform waiting area.','expected':'The subway platform waiting area is for passengers and should not contain a parked private car.','steps':'Inspect the car and the surrounding platform facilities.'}})
catalog['tasks'].append(recipe)
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);m=unreal.load_asset('/Game/M3D_Old_Car/Meshes/SM_Old_Car');assert m
m.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);unreal.EditorAssetLibrary.save_loaded_asset(m)
for reg in regs:
 path=r/'projects/Subway/Content'/(reg['map'][6:]+'.umap');shutil.copy2(path,w/(path.name+'.before'))
 assert l.load_level(reg['map'])
 if reg['id']=='platform':
  car=a.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(0,0,-5000));car.set_actor_label('PrivateCarTemplate');car.tags=[unreal.Name('auditor_actor:PrivateCarTemplate')];car.static_mesh_component.set_static_mesh(m);car.static_mesh_component.set_collision_profile_name('BlockAll');car.set_actor_hidden_in_game(True);car.set_actor_enable_collision(False)
 controller=next(x for x in a.get_all_level_actors() if x.get_class().get_name()=='AuditorTasks');controller.set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert l.save_current_level()
catpath.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n');(w/'out/author.json').write_text(json.dumps(dict(status='PASS',recipe=recipe),ensure_ascii=False,indent=2))
