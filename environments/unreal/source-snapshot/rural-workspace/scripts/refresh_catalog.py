import unreal,json
from pathlib import Path
root=Path('/home/ubuntu/unreal-auditor/rural-workspace');env=root/'environments/rural-australia';catalog=json.loads((env/'tasks.json').read_text())
for t in catalog['tasks']:
 if t['id']=='R08':t['collision_center']=[-2177.630859375,-5404.6298828125,100];t['review_aim']=[-2177.63,-5404.63,150]
 if t['id']=='R15':
  t.update(kind='view_cull',subcategory='V1',title='Creek rock disappears at center of view',threshold=.99)
  t.pop('offset',None)
  t['rubrics_i18n']={'zh':{'criteria':'把溪边倒木旁的小石块移到视野中央时，它突然消失，偏转视角后又恢复。正常情况下近处未被遮挡的石块应持续可见。'},'en':{'criteria':'The small rock beside the creek log disappears when centered in view and returns when the view shifts. A nearby unobstructed rock should remain visible.'}}
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for r in json.loads((env/'regions.json').read_text())['regions']:
 assert levels.load_level(r['map'])
 controllers=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks)];assert len(controllers)==1
 controllers[0].set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert levels.save_current_level()
(env/'tasks.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2));print('RURAL_CATALOG_REFRESHED')
