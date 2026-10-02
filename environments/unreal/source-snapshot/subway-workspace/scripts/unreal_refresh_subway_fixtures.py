"""Remove retired water equipment and synchronize the staged subway catalogs."""
from pathlib import Path
import json
import sys
import runpy
import unreal
sys.path.insert(0, str(Path(__file__).resolve().parent))
from unreal_subway_fixtures import create
root=Path(__file__).resolve().parents[1]
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
catalog=json.loads((root/'environments/subway/tasks.json').read_text())
regions=json.loads((root/'environments/subway/regions.json').read_text())['regions']
legacy={'WaterCabinet','BenchInspectionLamp'}
legacy.update('Hose'+part+side for part in ('Top','Middle','Bottom') for side in ('A','B'))
legacy.update('Port'+part+side for part in ('Top','Bottom') for side in ('A','B'))
removed=[]
for region in regions:
 assert level.load_level(region['map'])
 for actor in actors.get_all_level_actors():
  if actor.actor_has_tag('auditor_fixture:concourse') or actor.get_actor_label() in legacy:
   removed.append(actor.get_actor_label())
   actors.destroy_actor(actor)
  elif actor.get_class().get_name()=='AuditorTasks':
   actor.set_editor_property('catalog_json',json.dumps(catalog))
 if region['id']=='concourse':create(actors,'concourse')
 assert level.save_current_level()
# The equipment-only materials are no longer referenced by any saved level.
for name in ['M_WaterCabinetEnamel','M_WaterCabinetFrame','M_WaterCabinetSteel','M_WaterHoseRubber','M_WaterGaugeFace','M_WaterCleanLabel','M_WaterWasteLabel']:
 path='/Game/Auditor/Subway/'+name
 if unreal.EditorAssetLibrary.does_asset_exist(path):assert unreal.EditorAssetLibrary.delete_asset(path)
(root/'out/subway/water-removal.json').write_text(json.dumps({'removed_actor_count':len(removed),'removed':removed,'tasks':len(catalog['tasks'])},indent=2)+'\n')
runpy.run_path(str(Path(__file__).with_name('unreal_verify_subway_regions.py')))
