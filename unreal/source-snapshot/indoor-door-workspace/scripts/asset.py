import unreal,json
from pathlib import Path
p='/Game/GameReady3D/AtmosphericFarmhouse/StaticMesh/Props/SM_Storage_Box'
assets=unreal.EditorAssetLibrary.list_assets('/Game/GameReady3D/AtmosphericFarmhouse',recursive=True)
p=next(x for x in assets if x.endswith('/SM_Storage_Box.SM_Storage_Box'))
m=unreal.load_asset(p)
Path('/home/ubuntu/unreal-auditor/indoor-door-workspace/out/box.json').write_text(json.dumps(dict(path=p,bounds=str(m.get_bounds()),materials=[str(x.material_interface) for x in m.static_materials])))
