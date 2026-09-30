import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace')
source=r/'scripts/create_regions.py';s=source.read_text().replace("position=[-350,5900,-12],yaw=90","position=[-350,5900,-12],yaw=270");source.write_text(s)
p=r/'environments/ancient-chinese-city/tasks.json';data=json.loads(p.read_text())
next(t for t in data['tasks'] if t['id']=='A20')['yaw']=270
p.write_text(json.dumps(data,ensure_ascii=False,indent=2))
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for reg in json.loads((r/'environments/ancient-chinese-city/regions.json').read_text())['regions']:
 assert level.load_level(reg['map'])
 controllers=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks)];assert len(controllers)==1
 controllers[0].set_editor_property('catalog_json',json.dumps(data,ensure_ascii=False))
 assert level.save_current_level()
print('ANCIENT_CATALOG_PATCH_PASS')

