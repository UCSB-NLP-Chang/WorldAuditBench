import unreal,json,shutil
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');root=Path('/home/ubuntu/unreal-auditor/medieval-workspace');catalog=json.loads((root/'environments/medieval-village/tasks.json').read_text());regions=json.loads((root/'environments/medieval-village/regions.json').read_text())['regions'];level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for reg in regions:
 p=root/'project/Content'/(reg['map'][6:]+'.umap');b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True)
 if not b.exists():shutil.copy2(p,b)
 assert level.load_level(reg['map']);controller=next(a for a in actors.get_all_level_actors() if a.get_class().get_name()=='AuditorTasks');controller.set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert level.save_current_level()
(w/'out/author-medieval.json').write_text(json.dumps({'status':'PASS','maps':[r['map'] for r in regions]},indent=2));print('CONFIGURATION_WINDMILL_AUTHORED')
