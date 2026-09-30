import unreal,json,sys,shutil,hashlib,os
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');sys.path.insert(0,str(r/'scripts'))
from npc_policy import apply_npc_policy
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
backup=r/'out/npc-reduction/map-backup';backup.mkdir(parents=True,exist_ok=True)
def props():
 return sorted([(a.get_actor_label(),[round(float(v),5) for v in (a.get_actor_location().x,a.get_actor_location().y,a.get_actor_location().z,a.get_actor_rotation().pitch,a.get_actor_rotation().yaw,a.get_actor_rotation().roll,a.get_actor_scale3d().x,a.get_actor_scale3d().y,a.get_actor_scale3d().z)],[str(t) for t in a.tags]) for a in actors.get_all_level_actors() if any(str(t).startswith('auditor_actor:') for t in a.tags)])
report=[]
for reg in json.loads((r/'environments/ancient-chinese-city/regions.json').read_text())['regions']:
 source=r/'project/Content'/(reg['map'][6:]+'.umap');dest=backup/source.name
 if not dest.exists():shutil.copy2(source,dest)
 elif os.getenv('ANCIENT_RESTORE_NPC_BASELINE')=='1':shutil.copy2(dest,source)
 assert level.load_level(reg['map']);before=props();entry=apply_npc_policy(reg['id']);assert props()==before,'Task props changed'
 assert level.save_current_level()
 # Reload to catch construction-script regeneration of crowd actors.
 assert level.load_level('/Game/Auditor/AncientCity/Playtest');assert level.load_level(reg['map'])
 entry['reload_check']=apply_npc_policy(reg['id'])
 assert entry['reload_check']['removed_actors']==[]
 assert props()==before,(reg['id'],props(),before)
 report.append(entry)
 (r/'out/npc-reduction/layout-report.json').write_text(json.dumps(report,indent=2))
(r/'out/npc-reduction/layout-report.json').write_text(json.dumps(report,indent=2))
print('NPC_REDUCTION_PASS',json.dumps([{k:x[k] for k in ('region','before_npcs','after_npcs','kept')} for x in report]))
