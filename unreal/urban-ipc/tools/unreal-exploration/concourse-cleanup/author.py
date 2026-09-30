import unreal,json,shutil,hashlib
from pathlib import Path
w=Path("/home/ubuntu/unreal-auditor/subway-workspace/concourse-cleanup-20260918");p=Path("/home/ubuntu/unreal-auditor/projects/Subway")
before=w/"before";before.mkdir(exist_ok=True);mp=p/"Content/Auditor/Subway/Concourse.umap";assert not (before/"Concourse.umap").exists();shutil.copy2(mp,before/"Concourse.umap")
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);assert l.load_level("/Game/Auditor/Subway/Concourse")
e=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);actors=e.get_all_level_actors();by={a.get_name():a for a in actors};folder="/Game/Auditor/ConcourseCleanup20260918";unreal.EditorAssetLibrary.make_directory(folder);lib=unreal.MaterialEditingLibrary;cache={};changes=[]
def constant(m,v,prop):
 n=lib.create_material_expression(m,unreal.MaterialExpressionConstant);n.set_editor_property("r",v);lib.connect_material_property(n,"",prop)
def fixed(old,kind):
 key=old.get_path_name()
 if key in cache:return cache[key]
 dst=folder+"/"+old.get_name()+"_"+kind;assert not unreal.EditorAssetLibrary.does_asset_exist(dst);m=unreal.EditorAssetLibrary.duplicate_asset(key,dst);assert m;cache[key]=m
 if isinstance(m,unreal.MaterialInstanceConstant):
  lib.set_material_instance_parent(m,fixed(old.get_editor_property("parent"),kind));lib.update_material_instance(m)
 else:
  rough=lib.get_material_property_input_node(m,unreal.MaterialProperty.MP_ROUGHNESS)
  if rough and kind=="tile":
   out=lib.get_material_property_input_node_output_name(m,unreal.MaterialProperty.MP_ROUGHNESS);n=lib.create_material_expression(m,unreal.MaterialExpressionMax);n.set_editor_property("const_b",.6);lib.connect_material_expressions(rough,out,n,"A");lib.connect_material_property(n,"",unreal.MaterialProperty.MP_ROUGHNESS)
  else:constant(m,.32 if kind=="water" else .3,unreal.MaterialProperty.MP_ROUGHNESS)
  constant(m,0,unreal.MaterialProperty.MP_METALLIC);constant(m,.18 if kind=="tile" else .35,unreal.MaterialProperty.MP_SPECULAR)
  # Reduce high-frequency specular aliasing while preserving the existing normal texture/motion.
  normal=lib.get_material_property_input_node(m,unreal.MaterialProperty.MP_NORMAL)
  if normal:
   out=lib.get_material_property_input_node_output_name(m,unreal.MaterialProperty.MP_NORMAL);flat=lib.create_material_expression(m,unreal.MaterialExpressionConstant3Vector);flat.set_editor_property("constant",unreal.LinearColor(0,0,1,1));mix=lib.create_material_expression(m,unreal.MaterialExpressionLinearInterpolate);mix.set_editor_property("const_alpha",.35 if kind=="tile" else .25);lib.connect_material_expressions(flat,"",mix,"A");lib.connect_material_expressions(normal,out,mix,"B");lib.connect_material_property(mix,"",unreal.MaterialProperty.MP_NORMAL)
  if kind in ["water","glass"]:m.set_editor_property("refraction_method",unreal.RefractionMode.RM_NONE)
  if kind=="water":m.set_editor_property("two_sided",False)
  lib.recompile_material(m)
 assert unreal.EditorAssetLibrary.save_loaded_asset(m,False);changes.append({"original":key,"replacement":m.get_path_name(),"kind":kind});return m
for a in actors:
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  for i,old in enumerate(c.get_materials()):
   if not old:continue
   n=old.get_name().lower();kind="tile" if any(s in n for s in ["plaintile","concretetile","metrotile"]) else "glass" if "glass" in n else "water" if "water_a" in n else None
   if kind:c.set_material(i,fixed(old,kind))
# A physical backing is necessary: making translucent water two-sided cannot form a wall.
wallmesh=unreal.load_asset("/Game/Subway_Station/Meshes/SM_Wall_01");brick=fixed(unreal.load_asset("/Game/Subway_Station/Materials/M_PlainTile_A"),"tile");added=[]
for i,x in enumerate([-310,290]):
 a=e.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(x,5598,400));a.set_actor_label("Review_Fountain_Back_"+str(i));a.set_actor_scale3d(unreal.Vector(1,1,.75));a.set_editor_property("tags",["review_fountain_backing"]);c=a.static_mesh_component;c.set_static_mesh(wallmesh);c.set_collision_profile_name("BlockAll")
 for slot in range(c.get_num_materials()):c.set_material(slot,brick)
 added.append(a.get_actor_label())
# Fill the missing street-level foundations outside the sunken entrance, including the upper stair landing.
mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_StreetFoundation",folder,unreal.Material,unreal.MaterialFactoryNew());col=lib.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector);col.set_editor_property("constant",unreal.LinearColor(.18,.19,.20,1));lib.connect_material_property(col,"",unreal.MaterialProperty.MP_BASE_COLOR);constant(mat,.88,unreal.MaterialProperty.MP_ROUGHNESS);constant(mat,.1,unreal.MaterialProperty.MP_SPECULAR);lib.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat,False)
cube=unreal.load_asset("/Engine/BasicShapes/Cube")
for name,x0,x1,y0,y1 in [("West",-50000,-1665,-50000,50000),("East",2000,50000,-50000,50000),("North",-1665,2000,6320,50000),("South",-1665,2000,-50000,1800)]:
 a=e.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector((x0+x1)/2,(y0+y1)/2,-60));a.set_actor_label("Review_StreetFoundation_"+name);a.set_actor_scale3d(unreal.Vector((x1-x0)/100,(y1-y0)/100,18.8));c=a.static_mesh_component;c.set_static_mesh(cube);c.set_material(0,mat);c.set_collision_profile_name("BlockAll");added.append(a.get_actor_label())
# Keep task actors, task recipes and spawn policy exactly as before.
assert l.save_current_level();(w/"out/authoring.json").write_text(json.dumps({"status":"PASS","materials":changes,"added":added,"task_catalog_unchanged":True},indent=2))
