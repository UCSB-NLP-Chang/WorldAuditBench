"""Inspect already licensed building meshes through a temporary read-only source link."""
import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');o=r/'out/house-v3';o.mkdir(exist_ok=True)
rows=[]
for f in sorted((r/'project/Content/NYCBuildingVolume2/Static_Meshes/Buildings').glob('*.uasset')):
 p='/Game/NYCBuildingVolume2/Static_Meshes/Buildings/'+f.stem;m=unreal.load_asset(p);assert isinstance(m,unreal.StaticMesh),p
 b=m.get_bounds();rows.append(dict(mesh=p,origin=list(b.origin.to_tuple()),extent=list(b.box_extent.to_tuple()),materials=[x.material_interface.get_path_name() if x.material_interface else None for x in m.static_materials]))
(o/'building-inspection.json').write_text(json.dumps(rows,indent=2));print('BUILDING_INSPECTION',json.dumps(rows),flush=True)
