import bpy,json
from pathlib import Path
from mathutils import Vector,Matrix
w=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20-car-replacement')
for o in bpy.data.objects:
 for m in o.modifiers:
  if m.type=='SUBSURF':m.levels=min(m.levels,2);m.render_levels=m.levels
bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();parts=[]
for i in deps.object_instances:
 o=i.object
 if o.type!='MESH' or o.name in ['Floor','Light','carRigArrow','carRigOutline'] or (i.parent and i.parent.name=='1M'):continue
 mesh=bpy.data.meshes.new_from_object(o,depsgraph=deps);mesh.transform(i.matrix_world);parts.append((o.name,mesh))
assert sum(n=='TireRubber' for n,m in parts)==4
vs=[v.co for n,m in parts for v in m.vertices];lo=Vector([min(v[k] for v in vs) for k in range(3)]);hi=Vector([max(v[k] for v in vs) for k in range(3)]);center=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z));scale=4.45/(hi.x-lo.x)
for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
for n,m in parts:
 for v in m.vertices:v.co=(v.co-center)*scale
 o=bpy.data.objects.new(n,m);bpy.context.collection.objects.link(o);o.select_set(True)
bpy.context.view_layer.objects.active=o;bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
bpy.ops.export_scene.fbx(filepath=str(w/'private_coupe.fbx'),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',bake_anim=False,apply_unit_scale=True,use_mesh_modifiers=False)
(w/'out/export.json').write_text(json.dumps(dict(parts=len(parts),dimensions=list((hi-lo)*scale),vertices=sum(len(m.vertices) for n,m in parts),materials=list(set(x.name for n,m in parts for x in m.materials))),indent=2));print('EXPORT_PASS')
