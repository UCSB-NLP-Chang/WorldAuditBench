import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');d='/Game/Auditor/AncientCity/EraProps/HouseholdAC';rows=[]
for n in ['Outdoor_AC_Unit','SM_SM_HouseholdCondenser']:
 a=unreal.load_asset(d+'/'+n);rows.append(dict(name=n,materials=[str(m.material_interface) for m in a.static_materials]))
(r/'out/ac-v2/materials.json').write_text(json.dumps(rows,indent=2))
exec((r/'scripts/verify_ac_route.py').read_text())
