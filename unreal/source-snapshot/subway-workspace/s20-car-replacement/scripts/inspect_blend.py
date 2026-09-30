import bpy,json
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20-car-replacement')
rows=[]
for o in bpy.data.objects:
 rows.append(dict(name=o.name,type=o.type,location=list(o.location),dimensions=list(o.dimensions),hidden=o.hide_render,materials=[x.name for x in o.data.materials] if o.type=='MESH' else [],modifiers=[(m.name,m.type) for m in o.modifiers]))
(w/'out/blend-inspection.json').write_text(json.dumps(dict(objects=rows,texts={t.name:t.as_string() for t in bpy.data.texts}),indent=2))
