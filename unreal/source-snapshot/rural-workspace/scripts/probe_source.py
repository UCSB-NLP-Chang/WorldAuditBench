import unreal,json
from pathlib import Path
root=Path('/home/ubuntu/unreal-auditor/rural-workspace'); level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem); actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem); editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
results=[]
for suffix,c in [('01',[10500,10100]),('03',[-1928,-4782]),('02',[12000,-3000])]:
 level.load_level('/Game/RuralAustralia/Maps/RuralAustralia_Example_'+suffix);w=editor.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
 info={'map':suffix,'special':[],'ground':[]}
 for a in actors.get_all_level_actors():
  cls=a.get_class().get_name()
  if 'Landscape' in cls or 'Foliage' in cls or 'Camera' in cls:
   d={'label':a.get_actor_label(),'class':cls,'rotation':str(a.get_actor_rotation()),'components':[]}
   for x in a.get_components_by_class(unreal.SceneComponent):
    if 'Landscape' in x.get_class().get_name() or isinstance(x,unreal.InstancedStaticMeshComponent):
     q={'class':x.get_class().get_name(),'location':list(x.get_world_location().to_tuple())}
     for key in ['section_base_x','section_base_y','component_size_quads']:
      try:q[key]=x.get_editor_property(key)
      except:pass
     if isinstance(x,unreal.InstancedStaticMeshComponent):q['instances']=x.get_instance_count()
     d['components'].append(q)
   info['special'].append(d)
 for dx in range(-1000,1001,500):
  for dy in range(-1000,1001,500):
   x,y=c[0]+dx,c[1]+dy
   h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(x,y,2500),unreal.Vector(x,y,-1000),'BlockAll',False,[],unreal.DrawDebugTrace.NONE,True).to_tuple()
   info['ground'].append({'xy':[x,y],'hit':h[0],'location':list(h[5].to_tuple()),'component':str(h[10])})
 results.append(info)
(root/'out/source-probes.json').write_text(json.dumps(results,indent=2));print('RURAL_PROBE_PASS')
