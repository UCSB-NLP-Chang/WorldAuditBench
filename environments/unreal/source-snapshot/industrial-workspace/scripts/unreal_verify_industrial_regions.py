"""Reload the three factory maps and check the portable first-person setup."""
import json
from pathlib import Path
import unreal
ROOT=Path(__file__).resolve().parents[1]
spec=json.loads((ROOT/'environments/industrial-factory/regions.json').read_text())
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
results=[]
for r in spec['regions']:
    assert level.load_level(r['map'])
    all_actors=actors.get_all_level_actors()
    regions=[a for a in all_actors if a.get_class().get_name()=='AuditorRegion']
    starts=[a for a in all_actors if isinstance(a,unreal.PlayerStart)]
    assert len(regions)==len(starts)==1
    region=regions[0]
    assert list(region.get_editor_property('region_maps'))==[q['map'] for q in spec['regions']]
    assert editor.get_editor_world().get_world_settings().get_editor_property('default_game_mode').get_name()=='AuditorGameMode'
    for key in ['bounds_min','bounds_max']:
        v=region.get_editor_property(key)
        assert [v.x,v.y,v.z]==r[key]
    assert region.get_editor_property('spawn_location')==starts[0].get_actor_location()
    assert not any('/Maps/TechArt.' in a.get_outer().get_path_name() for a in all_actors)
    assert not any(a.get_class().get_name().startswith(('PW_','BP_')) and a.get_class().get_name()!='BP_Sky_Sphere_C' and not (a.get_class().get_name()=='BP_RobotHend_C' and 'configuration_robot' in map(str,a.tags)) for a in all_actors)
    animated=[]
    for a in all_actors:
        for comp in a.get_components_by_class(unreal.SkeletalMeshComponent):
            if comp.get_editor_property('animation_data').get_editor_property('anim_to_play'):
                animated.append(a.get_actor_label())
    assert len(animated)>=5
    results.append(dict(id=r['id'],map=r['map'],actors=len(all_actors),authored_animation_actors=len(animated),result='PASS'))
Path(unreal.Paths.project_dir(),'Saved/industrial-map-verification.json').write_text(json.dumps(dict(result='PASS',regions=results),indent=2))
unreal.log('AUDITOR_INDUSTRIAL_MAPS_VERIFIED')
