from pathlib import Path
import unreal,json,shutil
w=Path("/home/ubuntu/unreal-auditor/subway-workspace/review-concourse-20260917");project=Path("/home/ubuntu/unreal-auditor/projects/Subway")
mp="/Game/Auditor/Subway/Concourse";source=project/"Content/Auditor/Subway/Concourse.umap"
assert not (w/"before/Concourse.umap").exists();shutil.copy2(source,w/"before/Concourse.umap")
l=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);assert l.load_level(mp)
aa=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors();a=next(a for a in aa if a.get_name()=="Actor_Deco_Fountain_C_2");meshes=a.get_components_by_class(unreal.StaticMeshComponent);assert len(meshes)==1;c=meshes[0]
folder="/Game/Auditor/ReviewConcourseRepair";unreal.EditorAssetLibrary.make_directory(folder);original=[];fixed=[]
for i in range(c.get_num_materials()):
 old=c.get_material(i);original.append(old.get_path_name());path=folder+"/"+old.get_name()+"_TwoSided";assert not unreal.EditorAssetLibrary.does_asset_exist(path);m=unreal.EditorAssetLibrary.duplicate_asset(old.get_path_name(),path);assert m
 m.set_editor_property("two_sided",True);unreal.MaterialEditingLibrary.recompile_material(m);assert unreal.EditorAssetLibrary.save_loaded_asset(m,False);c.set_material(i,m);fixed.append(m.get_path_name())
controller=next(a for a in aa if a.get_class().get_name()=="AuditorTasks");catalog=json.loads(controller.get_editor_property("catalog_json"));assert all(t["id"]!="S22" for t in catalog["tasks"])
task={"id":"S22","region":"concourse","map":mp,"category":"visual","subcategory":"V1","title":"瀑布装饰墙背面消失","kind":"fountain_backface","target":"","actor_target":a.get_name(),"materials":original,"status":"draft","rubrics_i18n":{"zh":{"expected":"实体瀑布装饰墙从前后观察都应保有墙体和对应的水面，不应因绕行而凭空消失。","steps":"从正面观察瀑布，再沿台阶走到上方草坪，从背面观察同一装饰墙。","criteria":"正面可见的瀑布装饰墙从背面消失或呈现错误的透视；绕回正面后恢复，场景和时间状态保持不变。"},"en":{"expected":"The waterfall feature retains its solid backing and appropriate visible surfaces from both sides.","steps":"Inspect the waterfall from the front, then walk up the stairs to the lawn and inspect the same feature from behind.","criteria":"A surface visible from the front disappears or incorrectly reveals the scene behind it when viewed from the back, and reappears upon returning to the original viewpoint without a time-dependent state change."}}}
catalog["tasks"].append(task);controller.set_editor_property("catalog_json",json.dumps(catalog,ensure_ascii=False));assert l.save_current_level();(w/"out/authoring.json").write_text(json.dumps({"status":"PASS","map":mp,"actor":a.get_name(),"original_materials":original,"fixed_materials":fixed,"draft_task":task},ensure_ascii=False,indent=2));(w/"out/S22-draft.json").write_text(json.dumps(task,ensure_ascii=False,indent=2))
