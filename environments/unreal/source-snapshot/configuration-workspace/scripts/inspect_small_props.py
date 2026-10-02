import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/indoor-workspace/project/Content');paths=list(r.glob('**/StaticMesh/Props/*Can*'))+list(r.glob('**/StaticMesh/Props/*Bottle*'))+list(r.glob('**/StaticMesh/Props/*Tin*'))+list(r.glob('**/StaticMesh/Props/*Tablelamp*'));rows=[]
for p in paths:
 m=unreal.load_asset('/Game/'+str(p.relative_to(r).with_suffix('')));b=m.get_bounds();rows.append(dict(mesh=p.stem,extent=list(b.box_extent.to_tuple())))
Path('/home/ubuntu/unreal-auditor/configuration-workspace/out/small-props.json').write_text(json.dumps(rows,indent=2))
