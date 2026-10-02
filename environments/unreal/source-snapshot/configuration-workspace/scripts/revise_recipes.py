from pathlib import Path
import json,shutil
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');cfg=json.loads((w/'projects.json').read_text())
def save(p,data):
 b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True)
 if not b.exists():shutil.copy2(p,b)
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
for family,env,tid in [('subway','subway','S18'),('indoor','residential-house','H13'),('ancient','ancient-chinese-city','A18')]:
 root=Path(cfg[family]['workspace']);path=root/'environments'/env/'tasks.json';data=json.loads(path.read_text());t=next(t for t in data['tasks'] if t['id']==tid)
 for k in ['source','expected_yaw_difference','scenario','offset','position']:t.pop(k,None)
 t['subcategory']='S2';t['kind']='configuration_pose';t['configuration_offset']=[0,0,0]
 if family=='subway':
  t.update(title='售货机平放在地上，操作面朝天',target='Vending_Machine4',configuration_rotation=[90,0,0],configuration_seat=True,configuration_offset=[0,-130,0],configuration_local_axis=[1,0,0],configuration_axis_clean=[0,-1,0],configuration_axis_bug=[0,0,1],probe=[2480,1590,100],review_aim=[2480,1800,45])
  zh=['售货机背面贴地，按钮、显示窗和取货口朝天。','正常情况下，售货机应直立摆放，操作面朝向乘客。','走到站台售货机旁，查看它与地面接触的面及操作面方向。'];en=['The vending machine lies on its back, with its controls, display and collection opening facing upwards.','The machine should stand upright with its operating face accessible to passengers.','Approach the platform machine and inspect its ground contact and operating face.']
  t.update(observable_failure=zh[0],expected_behavior=zh[1],trigger=zh[2])
 elif family=='indoor':
  t.update(title='厨房冰箱上下倒置',region='kitchen_dining',kind='residential_configuration_pose',scenario='configuration_pose',target='StaticMeshActor_173',configuration_rotation=[180,0,0],configuration_seat=True,configuration_local_axis=[0,0,1],configuration_axis_clean=[0,0,1],configuration_axis_bug=[0,0,-1],probe=[-90,-820,239])
  zh=['厨房冰箱上下倒置，顶部贴地、底脚朝上。','正常情况下，冰箱应由底脚支撑，保持直立。','从厨房正面和侧面查看冰箱的底脚、门把手与地面关系。'];en=['The kitchen refrigerator is upside down, with its top on the floor and its feet pointing upwards.','The refrigerator should stand upright on its feet.','Inspect the refrigerator from the front and side, checking its feet, handles and floor contact.']
 else:
  t.update(title='Residence name plaque mounted upside down',region='courtyard',map='/Game/Auditor/AncientCity/Courtyard',target='Scenery_SM_doorMain_SM_Door_MainEntrance_01_5',configuration_rotation=[180,0,0],configuration_seat=False,configuration_local_axis=[0,0,1],configuration_axis_clean=[0,-0.224951,0.974370],configuration_axis_bug=[0,0.224951,-0.974370],probe=[500,7510,110],review_aim=[479,7094,411])
  zh=['宅院门上的“陈府”匾额上下倒装，文字整体颠倒。','正常情况下，门匾应保持文字正向可读。','从门口正前方观察匾额文字，并从侧面确认匾额仍安装在门上。'];en=['The residence name plaque is mounted upside down, inverting its lettering.','The entrance plaque should be mounted with its lettering upright.','Inspect the plaque from in front of the entrance, then confirm from the side that it remains mounted above the doorway.']
 t['rubrics_i18n']={lang:dict(zip(['criteria','expected','steps'],vals)) for lang,vals in [('zh',zh),('en',en)]}
 save(path,data)
 if family=='indoor':
  p=Path(cfg[family]['project']).parent/'Plugins/AuditorRuntime/Source/AuditorRuntime/Private/ResidentialTaskRevision.inl';b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b)
  p.write_text('static const TCHAR* ResidentialTaskRevision = TEXT(R"AUDITOR('+json.dumps(data,ensure_ascii=False)+')AUDITOR");\n')
 if family=='ancient':
  p=root/'environments/ancient-chinese-city/concise-rubrics.json'
  if p.exists():
   d=json.loads(p.read_text());print('CONCISE_STRUCTURE',type(d).__name__,list(d)[:5])
print('CONFIGURATION_RECIPES_UPDATED')
