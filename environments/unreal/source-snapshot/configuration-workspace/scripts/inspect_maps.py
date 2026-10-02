"""Read current authored region actors without saving or changing any map."""
import unreal,json,os,re
from pathlib import Path
work=Path('/home/ubuntu/unreal-auditor/configuration-workspace');family=os.environ['CONFIGURATION_FAMILY'];spec=json.loads((work/'projects.json').read_text())[family]
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def v(x):return [round(x.x,4),round(x.y,4),round(x.z,4)]
def r(x):return [round(x.pitch,4),round(x.yaw,4),round(x.roll,4)]
def prop(c,n):
 try:
  value=c.get_editor_property(n)
  return value.get_path_name() if isinstance(value,unreal.Object) else str(value)
 except Exception:return None
out=[]
for name in spec['maps']:
 assert level.load_level(name)
 rows=[]
 for a in actors.get_all_level_actors():
  parts=[]
  for c in a.get_components_by_class(unreal.MeshComponent):
   mesh=prop(c,'static_mesh') or prop(c,'skeletal_mesh_asset')
   if not mesh:continue
   bounds=c.get_local_bounds() if isinstance(c,unreal.StaticMeshComponent) else None
   parts.append({'name':c.get_name(),'mesh':mesh,'relative_location':v(c.get_editor_property('relative_location')),'relative_rotation':r(c.get_editor_property('relative_rotation')),'world_location':v(c.get_world_location()),'world_rotation':r(c.get_world_rotation()),'parent':c.get_attach_parent().get_name() if c.get_attach_parent() else None,'bounds_local':[v(x) for x in bounds] if bounds else None,'animation':prop(c,'animation_data'),'anim_class':prop(c,'anim_class'),'collision':str(c.get_collision_enabled())})
  row={'name':a.get_name(),'label':a.get_actor_label(),'class':a.get_class().get_name(),'location':v(a.get_actor_location()),'rotation':r(a.get_actor_rotation()),'scale':v(a.get_actor_scale3d()),'bounds':[v(x) for x in a.get_actor_bounds(False)],'tags':list(map(str,a.tags)),'parts':parts}
  if 'AuditorTasks' in a.get_class().get_name():row['catalog_json']=prop(a,'catalog_json')
  for c in a.get_components_by_class(unreal.RotatingMovementComponent):row['rotor']={'rate':prop(c,'rotation_rate'),'local':prop(c,'rotation_in_local_space'),'updated':prop(c,'updated_component')}
  rows.append(row)
 out.append({'map':name,'actors':rows})
(work/'out'/('inventory-'+family+'.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2));print('CONFIGURATION_INSPECT_PASS',family,len(out),sum(len(x['actors']) for x in out))
