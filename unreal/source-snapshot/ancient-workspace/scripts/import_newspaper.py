"""Import the original typeset newspaper as a rough, opaque paper material."""
import unreal,json,hashlib
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');source=r/'source-additions/era-v1/modern-newspaper.png';dest='/Game/Auditor/AncientCity/EraProps'
tools=unreal.AssetToolsHelpers.get_asset_tools();task=unreal.AssetImportTask();task.filename=str(source);task.destination_path=dest;task.destination_name='T_ModernNewspaper';task.automated=True;task.save=True;task.replace_existing=True;tools.import_asset_tasks([task]);tex=unreal.load_asset(dest+'/T_ModernNewspaper');assert tex
tex.set_editor_property('srgb',True);tex.set_editor_property('max_texture_size',2048);unreal.EditorAssetLibrary.save_loaded_asset(tex)
mat=unreal.load_asset(dest+'/M_ModernNewspaper') if unreal.EditorAssetLibrary.does_asset_exist(dest+'/M_ModernNewspaper') else tools.create_asset('M_ModernNewspaper',dest,unreal.Material,unreal.MaterialFactoryNew())
unreal.MaterialEditingLibrary.delete_all_material_expressions(mat);mat.set_editor_property('two_sided',True)
sample=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionTextureSample);sample.texture=tex;unreal.MaterialEditingLibrary.connect_material_property(sample,'RGB',unreal.MaterialProperty.MP_BASE_COLOR)
rough=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant);rough.r=.92;unreal.MaterialEditingLibrary.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS)
unreal.MaterialEditingLibrary.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat)
(r/'out/era-v1/newspaper-import.json').write_text(json.dumps(dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),material=mat.get_path_name(),content='Original fictional modern newspaper, typeset with original phone illustrations.'),indent=2))
print('NEWSPAPER_IMPORTED',flush=True)
