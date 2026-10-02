import unreal,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/industrial-workspace');levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert levels.load_level('/Game/Auditor/Industrial/ControlRoom')
cls=unreal.load_class(None,'/Script/AuditorRuntime.IndustrialOperational');assert cls
for a in list(actors.get_all_level_actors()):
 if a.get_class()==cls:actors.destroy_actor(a)
 if a.get_name()=='PointLight94':a.tags=list(a.tags)+['operational_light']
folder='/Game/Auditor/Industrial';name='M_OperationalScreenOff'
m=unreal.load_asset(folder+'/'+name)
if not m:
 m=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,folder,unreal.Material,unreal.MaterialFactoryNew())
 c=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant3Vector);c.constant=unreal.LinearColor(.002,.003,.004,1)
 unreal.MaterialEditingLibrary.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
 rough=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant);rough.r=.25
 unreal.MaterialEditingLibrary.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS)
 unreal.MaterialEditingLibrary.recompile_material(m)
assert unreal.EditorAssetLibrary.save_loaded_asset(m,False)
task=unreal.AssetImportTask();task.filename=str(r/'out/operational/console-display.png');task.destination_path=folder;task.destination_name='T_ConsoleOperating';task.automated=True;task.save=True
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task]);tex=unreal.load_asset(folder+'/T_ConsoleOperating');assert tex
screen=unreal.load_asset(folder+'/M_ConsoleOperating')
if not screen:
 screen=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_ConsoleOperating',folder,unreal.Material,unreal.MaterialFactoryNew())
 sample=unreal.MaterialEditingLibrary.create_material_expression(screen,unreal.MaterialExpressionTextureSample);sample.texture=tex
 unreal.MaterialEditingLibrary.connect_material_property(sample,'RGB',unreal.MaterialProperty.MP_BASE_COLOR)
 unreal.MaterialEditingLibrary.connect_material_property(sample,'RGB',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
 unreal.MaterialEditingLibrary.recompile_material(screen)
assert unreal.EditorAssetLibrary.save_loaded_asset(screen,False)
console=next(x for x in actors.get_all_level_actors() if x.get_name()=='SM_DeskControl_4')
for slot in range(1,console.static_mesh_component.get_num_materials()):console.static_mesh_component.set_material(slot,screen)
a=actors.spawn_actor_from_class(cls,unreal.Vector());a.set_actor_label('OperationalStateCases');a.set_editor_property('off_material',m)
assert levels.save_current_level()
print('INDUSTRIAL_OPERATIONAL_AUTHOR_PASS')

