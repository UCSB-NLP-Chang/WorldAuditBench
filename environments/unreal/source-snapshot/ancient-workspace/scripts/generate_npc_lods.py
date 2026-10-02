import unreal,json,shutil
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');backup=r/'out/npc-lod-backup';backup.mkdir(exist_ok=True)
report=[]
for name in ['/Game/AncientChinese/Mesh/CharacterNpc/female/SkM_Female_01','/Game/AncientChinese/Mesh/CharacterNpc/male/SKM_MaleCharacter_01']:
 p=r/'project/Content'/(name[6:]+'.uasset');shutil.copy2(p,backup/p.name)
 m=unreal.load_asset(name);before=unreal.EditorSkeletalMeshLibrary.get_num_verts(m,0)
 assert unreal.EditorSkeletalMeshLibrary.regenerate_lod(m,3,False,False)
 infos=m.get_editor_property('lod_info')
 for i,ratio,screen in [(1,.35,.5),(2,.1,.2)]:
  red=infos[i].get_editor_property('reduction_settings');red.set_editor_property('num_of_triangles_percentage',ratio);red.set_editor_property('num_of_vert_percentage',ratio)
  infos[i].set_editor_property('reduction_settings',red)
  size=infos[i].get_editor_property('screen_size');size.set_editor_property('default',screen);infos[i].set_editor_property('screen_size',size)
 m.set_editor_property('lod_info',infos)
 assert unreal.EditorSkeletalMeshLibrary.regenerate_lod(m,3,True,False)
 assert unreal.EditorAssetLibrary.save_loaded_asset(m)
 report.append(dict(mesh=name,original_vertices=before,lod_vertices=[unreal.EditorSkeletalMeshLibrary.get_num_verts(m,i) for i in range(3)]))
(r/'out/npc-lods.json').write_text(json.dumps(report,indent=2));print('NPC_LODS_PASS',json.dumps(report))
