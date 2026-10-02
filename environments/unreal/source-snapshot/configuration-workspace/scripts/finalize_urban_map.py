import unreal,json
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');p=w/'out/author-urban.json';d=json.loads(p.read_text());new='/Game/Auditor/Migration/UE561/U046/R01/TaskMap_Candidate02';level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not unreal.EditorAssetLibrary.does_asset_exist(new):assert unreal.EditorAssetLibrary.duplicate_asset('/Game/Auditor/Configuration/UrbanMailboxBug',new)
assert level.load_level(new);assert level.save_current_level();asset=Path('/home/ubuntu/unreal-auditor/builds/core18-ue561-20260911/Content')/(new[6:]+'.umap');assert asset.exists()
next(r for r in d['maps'] if r['variant']=='Bug')['map']=new;p.write_text(json.dumps(d,indent=2));print('URBAN_CANONICAL_MAP_SAVED')
