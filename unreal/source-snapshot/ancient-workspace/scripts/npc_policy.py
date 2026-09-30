import unreal,json
from pathlib import Path
ROOT=Path('/home/ubuntu/unreal-auditor/ancient-workspace')
def apply_npc_policy(region_id):
 actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
 policy=json.loads((ROOT/'environments/ancient-chinese-city/npc-layout.json').read_text())
 keep=set(policy['keep_actor_labels'][region_id])
 before=[];removed=[];kept=[]
 for actor in list(actors.get_all_level_actors()):
  components=actor.get_components_by_class(unreal.SkeletalMeshComponent)
  if not components:continue
  # These meshes belong only to the authored population, not task props.
  paths=[c.get_editor_property('skeletal_mesh_asset').get_path_name() for c in components if c.get_editor_property('skeletal_mesh_asset')]
  if not paths or not all('/AncientChinese/Mesh/CharacterNpc/' in p for p in paths):continue
  label=actor.get_actor_label();before.append(dict(label=label,count=len(components)))
  if label in keep:
   assert len(components)==1,(label,'Unexpected crowd actor')
   kept.append(label)
  else:
   assert not any(str(t).startswith('auditor_actor:') for t in actor.tags),label
   assert actors.destroy_actor(actor),label
   removed.append(label)
 assert set(kept)==keep,dict(region=region_id,missing=list(keep-set(kept)))
 return dict(region=region_id,before_npcs=sum(a['count'] for a in before),after_npcs=len(kept),kept=kept,removed_actors=removed)
