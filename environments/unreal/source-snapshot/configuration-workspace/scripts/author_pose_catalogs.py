import unreal,json,shutil,os
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');cfg=json.loads((w/'projects.json').read_text());family=os.environ['CONFIGURATION_FAMILY'];s=cfg[family];env={'subway':'subway','indoor':'residential-house','ancient':'ancient-chinese-city'}[family];root=Path(s['workspace']);catpath=root/'environments'/env/'tasks.json';catalog=json.loads(catpath.read_text());regs=json.loads((root/'environments'/env/'regions.json').read_text())['regions'];tid={'subway':'S18','indoor':'H13','ancient':'A18'}[family];recipe=next(t for t in catalog['tasks'] if t['id']==tid)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
report=[]
for reg in regs:
 p=Path(s['project']).parent/'Content'/(reg['map'][6:]+'.umap');b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True)
 if not b.exists():shutil.copy2(p,b)
 assert level.load_level(reg['map'])
 controllers=[a for a in actors.get_all_level_actors() if a.get_class().get_name()=='AuditorTasks'];assert len(controllers)==1
 if reg['id']==recipe['region']:
  target=next(a for a in actors.get_all_level_actors() if 'auditor_actor:'+recipe['target'] in list(map(str,a.tags)))
  before=target.get_actor_transform();center,extent=target.get_actor_bounds(False);localaxis=unreal.Vector(*recipe.get('configuration_local_axis',[0,0,1]));q=before.rotation;clean=q.rotate_vector(localaxis)
  pitch,yaw,roll=recipe['configuration_rotation'];rotation=unreal.Rotator(pitch=pitch,yaw=yaw,roll=roll);bug=(q*rotation.quaternion()).rotate_vector(localaxis)
  recipe['configuration_axis_clean']=[clean.x,clean.y,clean.z];recipe['configuration_axis_bug']=[bug.x,bug.y,bug.z]
 controllers[0].set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert level.save_current_level();report.append({'map':reg['map'],'entries':len(catalog['tasks'])})
catpath.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
# All maps must embed the same catalog, including final measured clean orientation.
for reg in regs:
 assert level.load_level(reg['map']);controller=next(a for a in actors.get_all_level_actors() if a.get_class().get_name()=='AuditorTasks');controller.set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert level.save_current_level()
if family=='indoor':
 p=Path(s['project']).parent/'Plugins/AuditorRuntime/Source/AuditorRuntime/Private/ResidentialTaskRevision.inl';p.write_text('static const TCHAR* ResidentialTaskRevision = TEXT(R"AUDITOR('+json.dumps(catalog,ensure_ascii=False)+')AUDITOR");\n')
if family=='ancient':
 p=root/'environments/ancient-chinese-city/concise-rubrics.json';d=json.loads(p.read_text());b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True)
 if not b.exists():shutil.copy2(p,b)
 d[tid]=recipe['rubrics_i18n'];p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
(w/'out'/('author-'+family+'.json')).write_text(json.dumps({'status':'PASS','maps':report,'recipe':recipe},ensure_ascii=False,indent=2));print('CONFIGURATION_AUTHOR_PASS',family)
