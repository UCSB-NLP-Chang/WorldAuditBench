import unreal,json,hashlib
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');root=Path('/home/ubuntu/unreal-auditor/builds/core18-ue561-20260911');plan=json.loads((root/'migration-plan.json').read_text());baseline=plan['baselines']['shopfront'];source=root/'Content'/(baseline[6:]+'.umap');assert hashlib.sha256(source.read_bytes()).hexdigest()==plan['baseline_hashes']['shopfront']
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);report={'source':baseline,'source_sha256':plan['baseline_hashes']['shopfront'],'maps':[]}
for variant in ['Clean','Bug']:
 path='/Game/Auditor/Configuration/UrbanMailbox'+variant;assert not unreal.EditorAssetLibrary.does_asset_exist(path);assert unreal.EditorAssetLibrary.duplicate_asset(baseline,path);assert level.load_level(path)
 target=next(a for a in actors.get_all_level_actors() if a.get_actor_label()=='SM_Mailbox2');assert abs(target.get_actor_scale3d().z-1)<.001
 target.tags=list(target.tags)+['configuration_mailbox'];center,extent=target.get_actor_bounds(False);before=target.get_actor_transform()
 if variant=='Bug':
  target.set_actor_rotation((before.rotation*unreal.Rotator(pitch=180,yaw=0,roll=0).quaternion()).rotator(),False)
  after,_=target.get_actor_bounds(False);target.set_actor_location(before.translation+center-after,False,False)
 assert level.save_current_level();c,e=target.get_actor_bounds(False);report['maps'].append({'map':path,'variant':variant,'target':target.get_name(),'location':[c.x,c.y,c.z],'extent':[e.x,e.y,e.z],'up':[target.get_actor_up_vector().x,target.get_actor_up_vector().y,target.get_actor_up_vector().z]})
assert hashlib.sha256(source.read_bytes()).hexdigest()==report['source_sha256']
(w/'out/author-urban.json').write_text(json.dumps(report,indent=2));print('CONFIGURATION_URBAN_AUTHOR_PASS')
