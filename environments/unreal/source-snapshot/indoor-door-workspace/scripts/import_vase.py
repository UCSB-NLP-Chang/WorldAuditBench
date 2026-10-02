import unreal,json
from pathlib import Path
w=Path('/home/ubuntu/unreal-auditor/indoor-door-workspace')
t=unreal.AssetImportTask();t.filename=str(w/'out/vase.obj');t.destination_path='/Game/Auditor/Props';t.destination_name='SM_FloorVase';t.automated=True;t.save=True;t.replace_existing=True
options=unreal.FbxImportUI();options.import_mesh=True;options.import_materials=False;options.import_textures=False;options.import_as_skeletal=False;options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
options.static_mesh_import_data.set_editor_property('combine_meshes',True);options.static_mesh_import_data.set_editor_property('generate_lightmap_u_vs',False)
t.options=options
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t]);m=unreal.load_asset('/Game/Auditor/Props/SM_FloorVase');assert m
mat=unreal.load_asset('/Game/Auditor/Props/M_CeramicVase')
if not mat:
 mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_CeramicVase','/Game/Auditor/Props',unreal.Material,unreal.MaterialFactoryNew())
 color=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector);color.constant=unreal.LinearColor(.60,.52,.41,1)
 unreal.MaterialEditingLibrary.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
 rough=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant);rough.r=.55
 unreal.MaterialEditingLibrary.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS)
 unreal.MaterialEditingLibrary.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat)
m.set_material(0,mat);unreal.EditorAssetLibrary.save_loaded_asset(m)
(w/'out/vase-import.json').write_text(json.dumps(dict(path=m.get_path_name(),bounds=str(m.get_bounds()))))
