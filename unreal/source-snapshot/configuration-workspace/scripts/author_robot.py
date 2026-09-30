import unreal,json,shutil
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');root=Path('/home/ubuntu/unreal-auditor/industrial-workspace');env=root/'environments/industrial-factory';project=root/'project';path=env/'tasks.json';data=json.loads(path.read_text());assert not any(t['id']=='I19' for t in data['tasks'])
b=w/'backups'/path.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,b)
t={'id':'I19','region':'assembly_hall','map':'/Game/Auditor/Industrial/AssemblyHall','category':'semantic','subcategory':'S2','kind':'robot_configuration','target':'ConfigurationTray','title':'机械臂空焊，工件托盘偏离作业位置','probe':[1600,2260,120],'review_aim':[2010,1860,150],'rubrics_i18n':{'zh':{'criteria':'工件托盘偏离机械臂的作业位置，机械臂反复在空处执行焊接动作。','expected':'正常情况下，工件托盘应与机械臂的焊接位置对齐。','steps':'连续观察机械臂的动作和工件位置，再与正常对照比较。'},'en':{'criteria':'The workpiece tray is displaced from the robot workstation, while the arm repeatedly follows its weld path through empty space.','expected':'The workpiece tray should align with the robot’s welding path.','steps':'Watch repeated arm movements and the workpiece position, then compare with the baseline.'}}};data['tasks'].append(t)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);regs=json.loads((env/'regions.json').read_text())['regions'];reports=[]
for reg in regs:
 p=project/'Content'/(reg['map'][6:]+'.umap');b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True)
 if not b.exists():shutil.copy2(p,b)
 assert level.load_level(reg['map'])
 if reg['id']=='assembly_hall':
  existing=list(actors.get_all_level_actors());names={'StaticMeshActor_106','StaticMeshActor_107','StaticMeshActor_108','SkeletalMeshActor_27'}
  matched=[a for a in existing if a.get_name() in names];assert len(matched)==4
  for a in matched:assert 'RobotHend4' in a.get_actor_label();actors.destroy_actor(a)
  cls=unreal.load_class(None,'/Game/Blueprints/GamePlay/BP_RobotHend.BP_RobotHend_C');robot=actors.spawn_actor_from_class(cls,unreal.Vector(1905,1670,50),unreal.Rotator(pitch=0,yaw=90,roll=0));robot.set_actor_label('ConfigurationWeldingRobot');robot.tags=['configuration_robot']
  source=next(a for a in existing if a.get_name()=='SM_AssemblyLine20');material=source.static_mesh_component.get_material(0)
  def box(label,loc,scale):
   a=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*loc));a.set_actor_label(label);a.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'));a.static_mesh_component.set_material(0,material);a.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE);a.set_actor_scale3d(unreal.Vector(*scale));return a
  tray=box('ConfigurationWorkpieceTray',[1905,1887,144.7],[1,.65,.03]);tray.tags=['auditor_actor:ConfigurationTray']
  block=box('ConfigurationMetalWorkpiece',[1905,1887,158.1],[.55,.45,.238]);block.attach_to_actor(tray,'',unreal.AttachmentRule.KEEP_WORLD,unreal.AttachmentRule.KEEP_WORLD,unreal.AttachmentRule.KEEP_WORLD,False)
  ctrl=actors.spawn_actor_from_class(unreal.load_class(None,'/Script/AuditorRuntime.IndustrialConfiguration'),unreal.Vector());ctrl.set_actor_label('ConfigurationRobotController')
 controller=next(a for a in actors.get_all_level_actors() if a.get_class().get_name()=='AuditorTasks');controller.set_editor_property('catalog_json',json.dumps(data,ensure_ascii=False));assert level.save_current_level();reports.append(reg['map'])
path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(w/'out/author-industrial.json').write_text(json.dumps({'status':'PASS','maps':reports,'recipe':t},ensure_ascii=False,indent=2));print('CONFIGURATION_ROBOT_AUTHORED')
