"""Reload saved subway maps and validate task targets, bounds and catalogs."""
import json
from collections import Counter
from pathlib import Path
import unreal
ROOT=Path(__file__).resolve().parents[1]
spec=json.loads((ROOT/'environments/subway/regions.json').read_text())
catalog=json.loads((ROOT/'environments/subway/tasks.json').read_text())
assert len(catalog['tasks'])==19 and {t['id'] for t in catalog['tasks']}=={f'S{i:02}' for i in range(1,20)}
assert Counter(t['category'] for t in catalog['tasks'])==dict(geometry=4,collision=4,visual=4,state=4,semantic=3)
assert Counter(t['region'] for t in catalog['tasks'])==dict(concourse=7,platform=7,trackside=5)
taxonomy=json.loads((ROOT/'environments/subway/taxonomy.json').read_text())
expected={s['id']:c['id'] for c in taxonomy['categories'] for s in c['subcategories']}
assert set(t['subcategory'] for t in catalog['tasks'])==set(expected)-{'S3'}
assert all(expected[t['subcategory']]==t['category'] for t in catalog['tasks'])
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reports=[]
for r in spec['regions']:
 assert level.load_level(r['map'])
 all_actors=actors.get_all_level_actors()
 # Removed equipment must leave neither meshes nor floating water-service text.
 assert not any(a.get_actor_label().startswith(('WaterCabinet','Hose','PortTop','PortBottom','Cabinet','Gauge','Valve','DoorLip','DoorHinge','DoorVent','DoorScrew')) for a in all_actors)
 assert not any(isinstance(a,unreal.TextRenderActor) and any(word in str(a.get_component_by_class(unreal.TextRenderComponent).get_editor_property('text')).upper() for word in ('CLEAN WATER','WASTE WATER','WATER SERVICES','ISOLATION','WS-01')) for a in all_actors)
 escalators=[a for a in all_actors if isinstance(a,unreal.SkeletalMeshActor) and a.get_actor_label().startswith('Escalator')]
 assert len(escalators)==8
 clips=Counter(a.get_component_by_class(unreal.SkeletalMeshComponent).get_editor_property('animation_data').get_editor_property('anim_to_play').get_name() for a in escalators)
 assert clips=={'Anim_Escalator':4,'Anim_Escalator_02':4},clips
 assert not any(a.get_actor_label() in ('SealedServicePanel','ServiceSign') for a in all_actors)
 if r.get('visible_train'):
  assert any('auditor_train:'+r['visible_train'] in [str(t) for t in a.tags] and isinstance(a,unreal.SkeletalMeshActor) for a in all_actors)
 assert not any(isinstance(a,unreal.CameraActor) for a in all_actors)
 regions=[a for a in all_actors if a.get_class().get_name()=='AuditorRegion']
 starts=[a for a in all_actors if isinstance(a,unreal.PlayerStart)]
 tasks=[a for a in all_actors if a.get_class().get_name()=='AuditorTasks']
 assert len(regions)==len(starts)==len(tasks)==1
 # Taxonomy annotations are served by the current API; compare all gameplay fields.
 def gameplay(value):
  if isinstance(value,dict):return {k:gameplay(v) for k,v in value.items() if k not in ('taxonomy_version','category','subcategory')}
  if isinstance(value,list):return [gameplay(v) for v in value]
  return value
 assert gameplay(json.loads(tasks[0].get_editor_property('catalog_json')))==gameplay(catalog)
 assert list(regions[0].get_editor_property('region_maps'))==[s['map'] for s in spec['regions']]
 for key in ['bounds_min','bounds_max']:
  v=regions[0].get_editor_property(key);assert [v.x,v.y,v.z]==r[key]
 targets={str(tag).removeprefix('auditor_actor:'):a for a in all_actors for tag in a.tags if str(tag).startswith('auditor_actor:')}
 for t in catalog['tasks']:
  if t['region']!=r['id']:continue
  assert t['map']==r['map']
  for key in ['target','source']:
   if t.get(key):assert t[key] in targets,(t['id'],key)
  if 'expected_yaw_difference' in t:
   target=targets[t['target']];source=targets[t['source']]
   delta=(source.get_actor_rotation().yaw-target.get_actor_rotation().yaw+180)%360-180
   assert abs(abs(delta)-t['expected_yaw_difference'])<.1,(t['id'],'orientation',delta)
   assert target.static_mesh_component.static_mesh==source.static_mesh_component.static_mesh
  if t['target'] and t['kind']!='semantic_add':
   c,e=targets[t['target']].get_actor_bounds(False)
   assert all(r['bounds_min'][i]<=v<=r['bounds_max'][i] for i,v in enumerate([c.x,c.y,c.z])),t['id']
 reports.append(dict(id=r['id'],map=r['map'],result='PASS',tasks=sum(t['region']==r['id'] for t in catalog['tasks']),tagged_meshes=len(targets)))
Path(unreal.Paths.project_dir(),'Saved/subway-map-verification.json').write_text(json.dumps(dict(result='PASS',regions=reports),indent=2)+'\n')
unreal.log('AUDITOR_SUBWAY_MAPS_VERIFIED')
