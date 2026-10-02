import bpy,json
from pathlib import Path
from mathutils import Vector
r=[]
for i in bpy.context.evaluated_depsgraph_get().object_instances:
 o=i.object
 if o.type!='MESH':continue
 vs=[i.matrix_world@Vector(v) for v in o.bound_box];lo=[min(v[k] for v in vs) for k in range(3)];hi=[max(v[k] for v in vs) for k in range(3)]
 r.append(dict(name=o.name,instance=i.is_instance,parent=i.parent.name if i.parent else None,min=lo,max=hi,visible=o.visible_get()))
Path('/home/ubuntu/unreal-auditor/subway-workspace/s20-car-replacement/out/instances.json').write_text(json.dumps(r,indent=2))
