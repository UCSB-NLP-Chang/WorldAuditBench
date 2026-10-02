import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');dest='/Game/Auditor/AncientCity/EraProps/IndoorCola';at=unreal.AssetToolsHelpers.get_asset_tools();E=unreal.MaterialEditingLibrary
tex={n:unreal.load_asset(dest+'/T_'+n) for n in ['AC_Base','AC_ORM','AC_Normal','AC_Emissive','ColaGlass','ColaLabel']}
for name,t in tex.items():
 t.set_editor_property('srgb',name not in ['AC_ORM','AC_Normal'])
 if name=='AC_ORM':t.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS)
 if name=='AC_Normal':t.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP)
 unreal.EditorAssetLibrary.save_loaded_asset(t,False)
m=at.create_asset('M_IndoorAC_Final',dest,unreal.Material,unreal.MaterialFactoryNew())
for name,channel,prop in [('AC_Base','RGB',unreal.MaterialProperty.MP_BASE_COLOR),('AC_ORM','R',unreal.MaterialProperty.MP_AMBIENT_OCCLUSION),('AC_ORM','G',unreal.MaterialProperty.MP_ROUGHNESS),('AC_ORM','B',unreal.MaterialProperty.MP_METALLIC),('AC_Normal','RGB',unreal.MaterialProperty.MP_NORMAL),('AC_Emissive','RGB',unreal.MaterialProperty.MP_EMISSIVE_COLOR)]:
 s=E.create_material_expression(m,unreal.MaterialExpressionTextureSample);s.set_editor_property('texture',tex[name]);s.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_MASKS if name=='AC_ORM' else unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if name=='AC_Normal' else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR);E.connect_material_property(s,channel,prop)
E.recompile_material(m);unreal.EditorAssetLibrary.save_loaded_asset(m,False)
ac=unreal.load_asset(dest+'/SM_IndoorAC');ac.set_material(0,m);unreal.EditorAssetLibrary.save_loaded_asset(ac,False)
cluster=unreal.load_asset(dest+'/SM_SM_ThreeColaBottles');report=[]
for i,slot in enumerate(cluster.static_materials):
 report.append(dict(i=i,name=str(slot.material_slot_name),material=slot.material_interface.get_path_name() if slot.material_interface else None))
 # Merging under a commandlet may default actor overrides; restore material slots.
 cluster.set_material(i,unreal.load_asset(dest+('/M_ColaGlass' if i%2==0 else '/M_ColaLabel')))
unreal.EditorAssetLibrary.save_loaded_asset(cluster,False)
(r/'out/indoor-cola-v3/material-slots.json').write_text(json.dumps(report,indent=2))
