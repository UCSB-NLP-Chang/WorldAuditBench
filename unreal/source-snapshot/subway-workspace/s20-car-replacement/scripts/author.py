import unreal,json,shutil
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor');w=r/'subway-workspace/s20-car-replacement';dest='/Game/Auditor/Props/PrivateCoupe'
t=unreal.AssetImportTask();t.filename=str(w/'private_coupe.fbx');t.destination_path=dest;t.destination_name='SM_PrivateCoupe';t.automated=True;t.save=True;t.replace_existing=False
opts=unreal.FbxImportUI();opts.import_mesh=True;opts.import_materials=False;opts.import_textures=False;opts.import_as_skeletal=False;opts.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;opts.automated_import_should_detect_type=False;opts.static_mesh_import_data.combine_meshes=True;opts.static_mesh_import_data.generate_lightmap_u_vs=True;t.options=opts

if not unreal.EditorAssetLibrary.does_asset_exist(dest+'/SM_PrivateCoupe'):unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
m=unreal.load_asset(dest+'/SM_PrivateCoupe');assert m
ml=unreal.MaterialEditingLibrary;at=unreal.AssetToolsHelpers.get_asset_tools();materials={};slots=[]
def material(name,color,metal=0,rough=.45,opacity=1):
 if name in materials:return materials[name]
 mat=at.create_asset('M_'+name,dest,unreal.Material,unreal.MaterialFactoryNew());assert mat
 def scalar(value,prop):
  e=ml.create_material_expression(mat,unreal.MaterialExpressionConstant);e.r=value;ml.connect_material_property(e,'',prop)
 e=ml.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector);e.constant=unreal.LinearColor(*color,1);ml.connect_material_property(e,'',unreal.MaterialProperty.MP_BASE_COLOR);scalar(metal,unreal.MaterialProperty.MP_METALLIC);scalar(rough,unreal.MaterialProperty.MP_ROUGHNESS)
 if opacity<1:
  mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT);mat.set_editor_property('two_sided',True);scalar(opacity,unreal.MaterialProperty.MP_OPACITY)
 ml.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat);materials[name]=mat;return mat
for i,slot in enumerate(m.static_materials):
 name=str(slot.material_slot_name);s=name.lower();slots.append(name)
 if 'carshell' in s:mat=material('SilverBluePaint',[.15,.22,.29],.7,.24)
 elif s=='glass':mat=material('WindowGlass',[.055,.08,.105],.1,.12,.42)
 elif 'glass' in s:mat=material('LampGlass',[.72,.78,.8],.1,.1,.28)
 elif 'tail' in s:mat=material('TailLamp',[.38,.008,.01],.15,.18)
 elif 'chrome' in s or 'silver' in s:mat=material('Chrome',[.55,.58,.61],.95,.22)
 elif 'rubber' in s:mat=material('Rubber',[.012,.014,.016],0,.8)
 elif 'white' in s or 'plate' in s or 'angeleye' in s:mat=material('White',[.65,.69,.7],.05,.3)
 elif 'blue' in s:mat=material('Blue',[.02,.1,.4],.3,.3)
 else:mat=material('DarkTrim',[.018,.023,.026],.05,.6)
 m.set_material(i,mat)
m.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);unreal.EditorAssetLibrary.save_loaded_asset(m);bounds=m.get_bounding_box();dims=bounds.max-bounds.min;assert 400<max(dims.x,dims.y)<500,(dims.x,dims.y,dims.z)
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);catpath=r/'subway-workspace/environments/subway/tasks.json';shutil.copy2(catpath,w/'tasks.before.json');catalog=json.loads(catpath.read_text());recipe=next(t for t in catalog['tasks'] if t['id']=='S20');recipe['position'][2]=-bounds.min.z;recipe['yaw']=0 if dims.x>dims.y else 90
for reg in json.loads((catpath.parent/'regions.json').read_text())['regions']:
 p=r/'projects/Subway/Content'/(reg['map'][6:]+'.umap');shutil.copy2(p,w/(p.name+'.before'));assert l.load_level(reg['map'])
 if reg['id']=='platform':
  car=next(x for x in a.get_all_level_actors() if 'auditor_actor:PrivateCarTemplate' in list(map(str,x.tags)));car.static_mesh_component.set_static_mesh(m)
  for i in range(car.static_mesh_component.get_num_materials()):car.static_mesh_component.set_material(i,m.get_material(i))
  car.set_actor_scale3d(unreal.Vector(1,1,1));car.set_actor_hidden_in_game(True);car.set_actor_enable_collision(False)
 ctrl=next(x for x in a.get_all_level_actors() if x.get_class().get_name()=='AuditorTasks');ctrl.set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert l.save_current_level()
catpath.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n');(w/'out/author.json').write_text(json.dumps(dict(status='PASS',dimensions=[dims.x,dims.y,dims.z],slots=slots,recipe=recipe),ensure_ascii=False,indent=2));print('AUTHOR_PASS')
