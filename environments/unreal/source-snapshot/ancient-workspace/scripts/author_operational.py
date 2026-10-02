import json,unreal
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');data=json.loads((r/'environments/ancient-chinese-city/tasks.json').read_text())
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for reg in json.loads((r/'environments/ancient-chinese-city/regions.json').read_text())['regions']:
 assert l.load_level(reg['map'])
 cs=[x for x in a.get_all_level_actors() if isinstance(x,unreal.AuditorTasks)];assert len(cs)==1
 cs[0].set_editor_property('catalog_json',json.dumps(data,ensure_ascii=False));assert l.save_current_level()
print('OPERATIONAL_CATALOG_PASS')

