import unreal,json,shutil
from pathlib import Path
w=Path("/home/ubuntu/unreal-auditor/subway-workspace/concourse-cleanup-20260918");p=Path("/home/ubuntu/unreal-auditor/projects/Subway")
shutil.copy2(p/"Content/Auditor/Subway/Concourse.umap",w/"before/Concourse-v1.umap")
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);assert l.load_level("/Game/Auditor/Subway/Concourse");e=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);lib=unreal.MaterialEditingLibrary
m=unreal.load_asset("/Game/Auditor/ConcourseCleanup20260918/M_StreetFoundation");original=unreal.load_asset("/Game/Subway_Station/Materials/M_Concrete_A")
node=lib.get_material_property_input_node(original,unreal.MaterialProperty.MP_BASE_COLOR);queue=[node];seen=set();tex=None
while queue:
 n=queue.pop()
 if not n or n.get_path_name() in seen:continue
 seen.add(n.get_path_name())
 if isinstance(n,unreal.MaterialExpressionTextureSample):
  t=n.get_editor_property("texture")
  if t:tex=t;break
 queue.extend(lib.get_inputs_for_material_expression(original,n))
assert tex,"Concrete base color texture not found"
pos=lib.create_material_expression(m,unreal.MaterialExpressionWorldPosition);mask=lib.create_material_expression(m,unreal.MaterialExpressionComponentMask);mask.set_editor_property("r",True);mask.set_editor_property("g",True);mask.set_editor_property("b",False);mask.set_editor_property("a",False);lib.connect_material_expressions(pos,"",mask,"Input")
scale=lib.create_material_expression(m,unreal.MaterialExpressionMultiply);scale.set_editor_property("const_b",.002);lib.connect_material_expressions(mask,"",scale,"A")
sample=lib.create_material_expression(m,unreal.MaterialExpressionTextureSample);sample.set_editor_property("texture",tex);lib.connect_material_expressions(scale,"",sample,"UVs");lib.connect_material_property(sample,"RGB",unreal.MaterialProperty.MP_BASE_COLOR);lib.recompile_material(m);assert unreal.EditorAssetLibrary.save_loaded_asset(m,False)
# Exterior roof/road surfaces must not fill the occupied station below.
for a in e.get_all_level_actors():
 if a.get_actor_label() in ["Review_StreetFoundation_East","Review_StreetFoundation_North","Review_StreetFoundation_South"]:
  pos=a.get_actor_location();pos.z=860;a.set_actor_location(pos,False,False);s=a.get_actor_scale3d();s.z=.4;a.set_actor_scale3d(s)
assert l.save_current_level();(w/"out/refinement.json").write_text(json.dumps({"concrete_texture":tex.get_path_name(),"station_interior_preserved":True}))
