"""Author functional reference equipment shared by clean and injected subway maps."""
import math
import unreal

def create(actors, scene):
 def material(name,color,metallic,roughness=.55):
  path='/Game/Auditor/Subway/'+name
  if unreal.EditorAssetLibrary.does_asset_exist(path):return unreal.load_asset(path)
  m=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Auditor/Subway',unreal.Material,unreal.MaterialFactoryNew())
  c=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant3Vector)
  c.set_editor_property('constant',unreal.LinearColor(*color,1))
  unreal.MaterialEditingLibrary.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
  for prop,value in [(unreal.MaterialProperty.MP_METALLIC,metallic),(unreal.MaterialProperty.MP_ROUGHNESS,roughness)]:
   e=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant)
   e.set_editor_property('r',value)
   unreal.MaterialEditingLibrary.connect_material_property(e,'',prop)
  unreal.MaterialEditingLibrary.recompile_material(m)
  unreal.EditorAssetLibrary.save_loaded_asset(m,False)
  return m
 paint=material('M_ServicePaint',[.035,.075,.085],.6)
 metal=material('M_ServicePipe',[.55,.60,.65],.9)
 sign=material('M_ServiceSign',[.015,.07,.035],.2)
 def vec(a): return unreal.Vector(x=a[0],y=a[1],z=a[2])
 def mesh(name, pos, scale, shape='Cube', rotation=None, finish=None):
  a=actors.spawn_actor_from_class(unreal.StaticMeshActor,vec(pos))
  a.set_actor_label(name);a.tags=['auditor_actor:'+name,'auditor_fixture:'+scene]
  a.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/'+shape))
  a.static_mesh_component.set_material(0,finish or (metal if shape=='Cylinder' or name.startswith('FanBlade') else (sign if name=='ServiceSign' else paint)))
  a.static_mesh_component.set_collision_profile_name('BlockAll')
  a.set_actor_scale3d(vec(scale))
  if rotation:a.set_actor_rotation(rotation,False)
  return a
 def text(name, value, pos, size=12):
  a=actors.spawn_actor_from_class(unreal.TextRenderActor,vec(pos),unreal.Rotator(yaw=-90))
  a.tags=['auditor_text:'+name,'auditor_fixture:'+scene];a.set_actor_label(name)
  c=a.get_component_by_class(unreal.TextRenderComponent)
  c.set_text(value);c.set_world_size(size)
  c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
  c.set_text_render_color(unreal.Color(r=235,g=245,b=250,a=255))
  return a
 if scene=='concourse':
  light=actors.spawn_actor_from_class(unreal.PointLight,vec([-510,4890,670]))
  light.set_actor_label('BenchInspectionLamp')
  light.tags=['auditor_fixture:'+scene]
  light.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
  light.light_component.set_editor_property('intensity',8000.0)
  light.light_component.set_editor_property('attenuation_radius',650.0)
  light.light_component.set_editor_property('cast_shadows',True)
 elif scene=='platform':
  mesh('FanPanel',[2450,1975,300],[1.3,.2,1.3])
  rotor=mesh('VentilationRotor',[2450,1950,300],[.18,.18,.15],'Cylinder',unreal.Rotator(roll=90))
  rotor.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
  for i in range(4):
   angle=i*90
   x=2450+24*math.cos(math.radians(angle));z=300+24*math.sin(math.radians(angle))
   a=mesh('FanBlade'+str(i),[x,1950,z],[.45,.06,.13],rotation=unreal.Rotator(pitch=-angle))
   a.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
   a.attach_to_actor(rotor,'',unreal.AttachmentRule.KEEP_WORLD,unreal.AttachmentRule.KEEP_WORLD,unreal.AttachmentRule.KEEP_WORLD,False)
  text('FanLabel','CONTINUOUS EXHAUST',[2450,1958,365],10)
  text('FanDirection','FIXED DIRECTION',[2450,1958,235],10)
