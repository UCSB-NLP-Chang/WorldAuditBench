"""Give both roadside wire fences one collision owner for the R04 task."""
from pathlib import Path
import json,shutil,unreal,math
root=Path('/home/ubuntu/unreal-auditor/rural-workspace');out=root/'out/fence-v7';out.mkdir(exist_ok=True)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);meshes=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
path=root/'environments/rural-australia/tasks.json';catalog=json.loads(path.read_text())
for name,p in [('tasks-before.json',path),('RoadBend-before.umap',root/'project/Content/Auditor/RuralAustralia/RoadBend.umap')]:
 if (out/name).exists():assert (out/name).read_bytes()==p.read_bytes(),'Source changed since backup'
 else:shutil.copy2(p,out/name)
assert levels.load_level('/Game/Auditor/RuralAustralia/RoadBend')
wire=[a for a in actors.get_all_level_actors() if a.get_actor_label().startswith('BendWireCollision_')];assert len(wire)==26
report=[]
for a in wire:
 p=a.get_actor_location();s=a.get_actor_scale3d();yaw=math.radians(a.get_actor_rotation().yaw);dx=math.cos(yaw)*s.x*50;dy=math.sin(yaw)*s.x*50
 report.append(dict(label=a.get_actor_label(),center=list(p.to_tuple()),start=[p.x-dx,p.y-dy],end=[p.x+dx,p.y+dy]))
options=unreal.MergeStaticMeshActorsOptions();options.destroy_source_actors=True;options.spawn_merged_actor=True;options.new_actor_label='BendBothWireFences';options.base_package_name='/Game/Auditor/RuralAustralia/SM_BothWireCollision'
source_collision=meshes.get_simple_collision_count(wire[0].static_mesh_component.static_mesh)
settings=unreal.MeshMergingSettings();settings.merge_physics_data=True;settings.merge_materials=False;settings.generate_light_map_uv=False;settings.pivot_point_at_zero=True;options.mesh_merging_settings=settings
merged=meshes.merge_static_mesh_actors(wire,options)
assert isinstance(merged,unreal.StaticMeshActor),str(merged)
merged.tags=[unreal.Name('auditor_actor:BendFence')];merged.set_actor_hidden_in_game(True);merged.set_actor_enable_collision(True);c=merged.static_mesh_component;c.set_collision_profile_name('BlockAll');c.set_cast_shadow(False)
count=meshes.get_simple_collision_count(c.static_mesh)+meshes.get_convex_collision_count(c.static_mesh)
(out/'merge-diagnostic.json').write_text(json.dumps(dict(source_collision=source_collision,merged_collision=count,mesh=c.static_mesh.get_path_name()),indent=2))
assert count==26,('Merged collision count',count,'source',source_collision)
unreal.EditorAssetLibrary.save_loaded_asset(c.static_mesh)
t=next(t for t in catalog['tasks'] if t['id']=='R04')
t['rubrics_i18n']={'zh':{'criteria':'人物可以直接穿过道路两侧可见的铁丝网，走到围栏另一侧。正常情况下完整的铁丝网围栏应阻挡人物通行。'},'en':{'criteria':'The player can walk through the visible wire fences on both sides of the road. Intact wire fencing should block passage.'}}
controller=next(a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks));controller.set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False))
assert levels.save_current_level();path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
(out/'wire-bays.json').write_text(json.dumps(report,indent=2));(out/'authoring.json').write_text(json.dumps(dict(merged_collision_primitives=26,source_fences_preserved=True,mesh=c.static_mesh.get_path_name()),indent=2))
