import unreal, json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace')
src=r/'source-additions/indoor-cola-v3'; out=r/'out/indoor-cola-v3'
at=unreal.AssetToolsHelpers.get_asset_tools(); dest='/Game/Auditor/AncientCity/EraProps/IndoorCola'
def texture(path,name,normal=False,linear=False):
 t=unreal.AssetImportTask();t.filename=str(path);t.destination_path=dest;t.destination_name=name;t.automated=True;t.save=True;at.import_asset_tasks([t]);a=t.get_objects()[0]
 if normal:a.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP)
 if linear:a.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS)
 a.set_editor_property('srgb',not (normal or linear));unreal.EditorAssetLibrary.save_loaded_asset(a,False);return a
def material(name,base,orm=None,normal=None,emissive=None,roughness=.3):
 m=at.create_asset(name,dest,unreal.Material,unreal.MaterialFactoryNew())
 def tex(t,prop,channel='RGB'):
  s=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionTextureSample);s.texture=t
  if t.compression_settings==unreal.TextureCompressionSettings.TC_NORMALMAP:s.sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
  elif not t.srgb:s.sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS
  unreal.MaterialEditingLibrary.connect_material_property(s,channel,prop)
 tex(base,unreal.MaterialProperty.MP_BASE_COLOR)
 if orm:
  for channel,prop in [('R',unreal.MaterialProperty.MP_AMBIENT_OCCLUSION),('G',unreal.MaterialProperty.MP_ROUGHNESS),('B',unreal.MaterialProperty.MP_METALLIC)]:tex(orm,prop,channel)
 else:
  c=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant);c.r=roughness;unreal.MaterialEditingLibrary.connect_material_property(c,'',unreal.MaterialProperty.MP_ROUGHNESS)
 if normal:tex(normal,unreal.MaterialProperty.MP_NORMAL)
 if emissive:tex(emissive,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
 unreal.MaterialEditingLibrary.recompile_material(m);unreal.EditorAssetLibrary.save_loaded_asset(m,False);return m
ac=src/'ac/model/TexturesIndoorUE4K'
acmat=material('M_IndoorAC',texture(ac/'AC_Indoor_low_mIndoor_BaseColor.png','T_AC_Base'),texture(ac/'AC_Indoor_low_mIndoor_OcclusionRoughnessMetallic.png','T_AC_ORM',linear=True),texture(ac/'AC_Indoor_low_mIndoor_Normal.png','T_AC_Normal',normal=True),texture(ac/'AC_Indoor_low_mIndoor_Emissive.png','T_AC_Emissive'))
label=material('M_ColaLabel',texture(src/'cola/model/Soda1.jpg','T_ColaLabel'),roughness=.4)
glass=material('M_ColaGlass',texture(src/'cola/model/Glass.jpg','T_ColaGlass'),roughness=.16)
report=[]
for path,name in [(src/'ac/model/AC_Indoor_low.fbx','SM_IndoorAC'),(src/'cola/model/Coca Cola Bottle.FBX','SM_ColaBottle')]:
 t=unreal.AssetImportTask();t.filename=str(path);t.destination_path=dest;t.destination_name=name;t.automated=True;t.save=True
 ui=unreal.FbxImportUI();ui.automated_import_should_detect_type=False;ui.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;ui.import_as_skeletal=False;ui.import_materials=False;ui.import_textures=False;ui.static_mesh_import_data.combine_meshes=True;ui.static_mesh_import_data.auto_generate_collision=True;t.options=ui
 at.import_asset_tasks([t])
 for mesh in t.get_objects():
  if not isinstance(mesh,unreal.StaticMesh):continue
  slots=[str(s.material_slot_name) for s in mesh.static_materials]
  for i,slot in enumerate(slots):mesh.set_material(i,acmat if name=='SM_IndoorAC' else (glass if i==0 else label))
  mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);unreal.EditorAssetLibrary.save_loaded_asset(mesh,False);b=mesh.get_bounds()
  report.append(dict(mesh=mesh.get_path_name(),slots=slots,origin=list(b.origin.to_tuple()),extent=list(b.box_extent.to_tuple())))
(out/'import.json').write_text(json.dumps(report,indent=2))
