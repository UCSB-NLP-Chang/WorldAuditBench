import unreal,json,copy
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/Auditor/MedievalVillage/Windmill');assert unreal.EditorLoadingAndSavingUtils.save_map(editor.get_editor_world(),'/Game/Auditor/MedievalVillage/HouseProbeQA')
assert level.load_level('/Game/Auditor/MedievalVillage/HouseProbeQA')
c=json.loads((r/'environments/medieval-village/tasks.json').read_text());base=next(t for t in c['tasks'] if t['id']=='MV21')
for id,pos,aim,probe in [('HOUSEQA1',[42700,34000,-3839.531241741437],[42700,34000,-3210.7730059888545],[41600,31500,-3652.7668760161887]),('HOUSEQA2',[42700,34000,-3839.531241741437],[42700,34000,-3210.7730059888545],[41900,31500,-3647.5389486692125]),('HOUSEQA3',base['position'],base['review_aim'],[41600,31500,-3652.7668760161887])]:
 t=copy.deepcopy(base);t.update(id=id,map="/Game/Auditor/MedievalVillage/HouseProbeQA",position=pos,review_aim=aim,probe=probe);c['tasks'].append(t)
for a in actors.get_all_level_actors():
 if isinstance(a,unreal.AuditorTasks):a.set_editor_property('catalog_json',json.dumps(c))
assert level.save_current_level()
