import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');src=r/'source-additions/ac-v2/extracted/LowPoly_Outdoor_AC_Unit';dest='/Game/Auditor/AncientCity/EraProps/HouseholdAC';at=unreal.AssetToolsHelpers.get_asset_tools()
t=unreal.AssetImportTask();t.filename=str(src/'Outdoor_AC_Unit.fbx');t.destination_path=dest;t.automated=True;t.save=True
ui=unreal.FbxImportUI();ui.automated_import_should_detect_type=False;ui.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;ui.import_as_skeletal=False;ui.import_materials=False;ui.import_textures=False;ui.static_mesh_import_data.combine_meshes=False;ui.static_mesh_import_data.auto_generate_collision=True;t.options=ui;at.import_asset_tasks([t]);meshes=[a for a in t.get_objects() if isinstance(a,unreal.StaticMesh)]
x=unreal.AssetImportTask();x.filename=str(src/'Texture/Outdoor_AC_Unit.png');x.destination_path=dest;x.destination_name='T_HouseholdAC';x.automated=True;x.save=True;at.import_asset_tasks([x]);tex=x.get_objects()[0]
m=at.create_asset('M_HouseholdAC',dest,unreal.Material,unreal.MaterialFactoryNew());s=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionTextureSample);s.texture=tex;unreal.MaterialEditingLibrary.connect_material_property(s,'RGB',unreal.MaterialProperty.MP_BASE_COLOR);v=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant);v.r=.65;unreal.MaterialEditingLibrary.connect_material_property(v,'',unreal.MaterialProperty.MP_ROUGHNESS);unreal.MaterialEditingLibrary.recompile_material(m);unreal.EditorAssetLibrary.save_loaded_asset(m)
report=[]
for a in meshes:
 for i in range(len(a.static_materials)):a.set_material(i,m)
 a.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);unreal.EditorAssetLibrary.save_loaded_asset(a);b=a.get_bounds();report.append(dict(mesh=a.get_path_name(),origin=list(b.origin.to_tuple()),extent=list(b.box_extent.to_tuple())))
(r/'out/ac-v2/import.json').write_text(json.dumps(report,indent=2))
