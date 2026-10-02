import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');env=r/'environments/medieval-village';file=env/'tasks.json';catalog=json.loads(file.read_text())
for t in catalog['tasks']:
 if t['kind']=='blocker':t['review_aim']=t['position']
 for lang,rub in t['rubrics_i18n'].items():
  if rub.get('expected'):continue
  sep='。' if lang=='zh' else '. ';first,found,last=rub['criteria'].partition(sep);assert found and last.strip();rub['criteria']=first+('。' if lang=='zh' else '.');rub['expected']=last.strip();rub['steps']='靠近目标并观察；按异常描述改变视角、距离或进行交互。' if lang=='zh' else 'Approach the target and observe; follow the described view, distance or interaction trigger.'
file.write_text(json.dumps(catalog,ensure_ascii=False,indent=2));level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for reg in json.loads((env/'regions.json').read_text())['regions']:
 assert level.load_level(reg['map']);controllers=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks)];assert len(controllers)==1;controllers[0].set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert level.save_current_level()
