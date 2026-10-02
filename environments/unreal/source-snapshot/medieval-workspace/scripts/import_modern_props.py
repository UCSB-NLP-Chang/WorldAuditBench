"""Import the original, checksummed Fab FBX props on A10 and wire PBR textures."""
import json
from pathlib import Path
import unreal

ROOT = Path('/home/ubuntu/unreal-auditor/medieval-workspace')
SOURCE = ROOT / 'source-additions/fab-props-20260912/extracted'
OUTPUT = ROOT / 'out/props-v2'
OUTPUT.mkdir(exist_ok=True)
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
specs = [
    ('DeskLamp', SOURCE/'modern-minimal-desk-lamp/FBX', 'Lamp.fbx', 'Textures/lamp_',
     {'basecolor':'BASE_COLOR','metalness':'METALLIC','roughness':'ROUGHNESS','normal':'NORMAL','ao':'AMBIENT_OCCLUSION'}),
    ('FireExtinguisher', SOURCE/'fire-extinguisher', 'fire_extinguisher.fbx', 'fire_extinguisher_',
     {'CM':'BASE_COLOR','MM':'METALLIC','RM':'ROUGHNESS','NM':'NORMAL','AO':'AMBIENT_OCCLUSION'}),
]
results = []
for name, directory, filename, prefix, maps in specs:
    dest = '/Game/Auditor/MedievalVillage/ModernProps/'+name
    mesh = unreal.load_asset(dest+'/SM_'+name) if unreal.EditorAssetLibrary.does_asset_exist(dest+'/SM_'+name) else None
    if not mesh:
        task = unreal.AssetImportTask()
        task.filename = str(directory/filename)
        task.destination_path = dest
        task.destination_name = 'SM_'+name
        task.automated = True
        task.save = True
        ui = unreal.FbxImportUI()
        ui.automated_import_should_detect_type = False
        ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
        ui.import_as_skeletal = False
        ui.import_materials = False
        ui.import_textures = False
        ui.static_mesh_import_data.combine_meshes = True
        ui.static_mesh_import_data.auto_generate_collision = True
        task.options = ui
        asset_tools.import_asset_tasks([task])
        meshes = [a for a in task.get_objects() if isinstance(a, unreal.StaticMesh)]
        assert len(meshes) == 1, task.imported_object_paths
        mesh = meshes[0]
    material_path = dest+'/M_'+name
    material = unreal.load_asset(material_path) if unreal.EditorAssetLibrary.does_asset_exist(material_path) else asset_tools.create_asset('M_'+name,dest,unreal.Material,unreal.MaterialFactoryNew())
    unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
    for i, (suffix, prop) in enumerate(maps.items()):
        texture_path = dest+'/T_'+name+'_'+suffix
        texture = unreal.load_asset(texture_path) if unreal.EditorAssetLibrary.does_asset_exist(texture_path) else None
        if not texture:
            task = unreal.AssetImportTask()
            task.filename = str(directory/(prefix+suffix+'.png'))
            assert Path(task.filename).is_file(), task.filename
            task.destination_path = dest
            task.destination_name = 'T_'+name+'_'+suffix
            task.automated = True
            task.save = True
            asset_tools.import_asset_tasks([task])
            texture = task.get_objects()[0]
        texture.set_editor_property('srgb', prop == 'BASE_COLOR')
        texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP if prop=='NORMAL' else unreal.TextureCompressionSettings.TC_DEFAULT)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
        sample = unreal.MaterialEditingLibrary.create_material_expression(material,unreal.MaterialExpressionTextureSample,-400,i*220)
        sample.texture = texture
        sample.sampler_type = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if prop=='NORMAL' else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if prop=='BASE_COLOR' else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR
        unreal.MaterialEditingLibrary.connect_material_property(sample,'RGB' if prop in ('BASE_COLOR','NORMAL') else 'R',getattr(unreal.MaterialProperty,'MP_'+prop))
    # Keep the lamp off: its electric construction is the era anomaly.
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    for i in range(len(mesh.static_materials)):
        mesh.set_material(i, material)
    mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    bounds = mesh.get_bounds()
    results.append(dict(name=name,mesh=mesh.get_path_name(),origin=list(bounds.origin.to_tuple()),extent=list(bounds.box_extent.to_tuple()),materials=len(mesh.static_materials)))
(OUTPUT/'imported-props.json').write_text(json.dumps(results,indent=2))
print('MODERN_PROPS_IMPORTED',json.dumps(results),flush=True)
