"""Restore the original sign-proportion task in the current RoadBend map."""
from pathlib import Path
import json,shutil,unreal
root=Path('/home/ubuntu/unreal-auditor/rural-workspace');env=root/'environments/rural-australia'
out=root/'out/r03-sign-v6';out.mkdir(exist_ok=True)
path=env/'tasks.json';catalog=json.loads(path.read_text())
original=json.loads((root/'out/variety-v4/source-backup/tasks.json').read_text())
spec=next(t for t in original['tasks'] if t['id']=='R03')
assert spec['target']=='BendSign' and spec['scale']==[1,1,3]
assert next(t for t in catalog['tasks'] if t['id']=='R03')['target']=='BendRock'
for name,p in [('tasks-before.json',path),('RoadBend-before.umap',root/'project/Content/Auditor/RuralAustralia/RoadBend.umap')]:
 assert not (out/name).exists();shutil.copy2(p,out/name)
catalog['tasks']=[spec if t['id']=='R03' else t for t in catalog['tasks']]
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert levels.load_level('/Game/Auditor/RuralAustralia/RoadBend')
controller=next(a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks))
controller.set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False))
assert levels.save_current_level();path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
(out/'restored-task.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2))
