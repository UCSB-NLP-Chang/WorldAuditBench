"""Apply only the approved indoor AC and three cola bottles, preserving other cases."""
import unreal,json,copy,shutil
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');env=r/'environments/ancient-chinese-city';out=r/'out/indoor-cola-v3';dest='/Game/Auditor/AncientCity/EraProps/IndoorCola'
lev=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);ed=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);sm=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem) or unreal.new_object(unreal.StaticMeshEditorSubsystem)
backup=r/'backups/indoor-cola-v3';backup.mkdir(exist_ok=True)
for p in [env/'tasks.json',env/'concise-rubrics.json',env/'rubrics.bilingual.json',*[r/'project/Content/Auditor/AncientCity'/(n+'.umap') for n in ['Market','TeaHouse','Courtyard']]]:
 if p.exists() and not (backup/p.name).exists():shutil.copy2(p,backup/p.name)
assert lev.load_level('/Game/Auditor/AncientCity/TeaHouse');w=ed.get_editor_world();unreal.AuditorSceneSetup.prepare_editor_collision(w)
catalog=json.loads((env/'tasks.json').read_text());before=copy.deepcopy(catalog);report=[]
def source(tag,mesh,scale,yaw):
 a=next(a for a in actors.get_all_level_actors() if unreal.Name('auditor_actor:'+tag) in a.tags)
 a.static_mesh_component.set_static_mesh(mesh);a.static_mesh_component.set_editor_property('override_materials',[]);a.static_mesh_component.set_collision_profile_name('BlockAll');a.set_actor_scale3d(unreal.Vector(scale,scale,scale));a.set_actor_rotation(unreal.Rotator(yaw=yaw),False);a.set_actor_location(unreal.Vector(0,0,0),False,False);a.set_actor_hidden_in_game(True);a.set_actor_enable_collision(False);return a
def trace(start,end,ignore):
 h=unreal.SystemLibrary.line_trace_single_by_profile(w,unreal.Vector(*start),unreal.Vector(*end),'BlockAll',True,ignore,unreal.DrawDebugTrace.NONE,True)
 assert h and h.to_tuple()[0],(start,end)
 return h.to_tuple()
def finish(a,t,texts):
 a.set_actor_location(unreal.Vector(0,0,-10000),False,False)
 for lang,(criteria,expected) in texts.items():t['rubrics_i18n'][lang].update(criteria=criteria,expected=expected,steps='靠近并观察物体的外形与标签。' if lang=='zh' else 'Approach and inspect the object and its details.')
 report.append(dict(id=t['id'],mesh=a.static_mesh_component.static_mesh.get_path_name(),scale=list(a.get_actor_scale3d().to_tuple()),task=copy.deepcopy(t)))

# The original FBX has glass in slot 0 and the label in slot 1 (verified connections).
bottle=unreal.load_asset(dest+'/SM_ColaBottle');bottle.set_material(0,unreal.load_asset(dest+'/M_ColaGlass'));bottle.set_material(1,unreal.load_asset(dest+'/M_ColaLabel'));unreal.EditorAssetLibrary.save_loaded_asset(bottle,False)
scale=28/(2*bottle.get_bounds().box_extent.z)
a=source('EraDrinkCan',bottle,scale,45)
for i in [0,1]:a.static_mesh_component.set_material(i,unreal.load_asset(dest+('/M_ColaGlass' if i==0 else '/M_ColaLabel')))
c,e=a.get_actor_bounds(False);x,y=-1656,5688
h=trace([x,y,115],[x,y,90],[a]);floor=h[5].z;assert 95<floor<115,(floor,h[9].get_name())
for dx,dy in [(-15,-6),(0,6),(15,-6)]:
 for ex,ey in [(-4,-4),(4,4),(-4,4),(4,-4)]:assert abs(trace([x+dx+ex,y+dy+ey,115],[x+dx+ex,y+dy+ey,90],[a])[5].z-floor)<.3
t=next(t for t in catalog['tasks'] if t['id']=='A21');t.update(title='Three cola bottles on an ancient tea table',position=[x-c.x,y-c.y,floor-c.z+e.z],yaw=45,additional_positions=[[x+dx-c.x,y+dy-c.y,floor-c.z+e.z] for dx,dy in [(-15,-6),(15,-6)]],probe=[-1530,5520,120.125],review_aim=[x,y,floor+14])
finish(a,t,{'zh':['古代茶馆的木桌上摆着三瓶带红色现代标签的可乐。','正常情况下，桌上的饮品及其包装应符合古代茶馆的时代背景。'],'en':['Three cola bottles with modern red labels sit on a wooden table in the ancient tea house.','Drinks and their packaging should fit the historical era of the tea house.']})

mesh=unreal.load_asset(dest+'/SM_IndoorAC');a=source('EraAirConditioner',mesh,1.1,0);b=mesh.get_bounds()
# Render inspection confirms the front faces local +Y; the rear -Y meets the wall.
anchor=unreal.Vector(b.origin.x,b.origin.y-b.box_extent.y,b.origin.z);p=unreal.Vector(-1850,5232.999999775887,345);n=unreal.Vector(0,1,0);gap=.2
for dx in [-44,0,44]:
 for dz in [-15,0,15]:assert abs(trace([p.x+dx,p.y+5,p.z+dz],[p.x+dx,p.y-8,p.z+dz],[a])[5].y-p.y)<.5
offset=a.get_actor_transform().transform_location(anchor);position=p+n*gap-offset
t=next(t for t in catalog['tasks'] if t['id']=='A24');t.update(title='Wall-mounted indoor air conditioner in an ancient tea house',position=list(position.to_tuple()),yaw=0,pitch=0,roll=0,support_local=list(anchor.to_tuple()),support_point=list(p.to_tuple()),support_normal=list(n.to_tuple()),support_gap=gap,probe=[-1530,5520,120.125],review_aim=list((p+n*10).to_tuple()))
finish(a,t,{'zh':['古代茶馆的墙上装着一台白色壁挂式室内空调，带有出风口和温度显示。','正常情况下，茶馆的设施应符合古代城市的时代背景。'],'en':['A white indoor air conditioner with an air vent and temperature display is mounted on the wall of the ancient tea house.','Facilities at the tea house should fit the historical era of the ancient city.']})
assert [t for t in before['tasks'] if t['id'] not in ['A21','A24']]==[t for t in catalog['tasks'] if t['id'] not in ['A21','A24']]
assert lev.save_current_level()
for reg in json.loads((env/'regions.json').read_text())['regions']:
 assert lev.load_level(reg['map']);ctrl=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks)];assert len(ctrl)==1;ctrl[0].set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False));assert lev.save_current_level()
(env/'tasks.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
for filename in ['concise-rubrics.json','rubrics.bilingual.json']:
 path=env/filename;data=json.loads(path.read_text())
 for t in catalog['tasks']:
  if t['id'] not in ['A21','A24']:continue
  if filename=='concise-rubrics.json':data[t['id']]={l:{k:rb[k] for k in ['criteria','expected']} for l,rb in t['rubrics_i18n'].items()}
  elif t['id'] in data:data[t['id']]=t['rubrics_i18n']
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2))
(out/'authored.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
