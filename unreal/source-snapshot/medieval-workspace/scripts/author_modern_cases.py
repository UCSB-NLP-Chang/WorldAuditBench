"""Add two market anachronisms and update the parked-car case after asset import."""
import json, math
from pathlib import Path
import unreal

ROOT=Path('/home/ubuntu/unreal-auditor/medieval-workspace')
ENV=ROOT/'environments/medieval-village'
OUT=ROOT/'out/house-v3';OUT.mkdir(exist_ok=True)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
vec=lambda p:unreal.Vector(*p)
catalog=json.loads((ENV/'tasks.json').read_text())
tasks={t['id']:t for t in catalog['tasks']}
regions=json.loads((ENV/'regions.json').read_text())['regions']
grid=json.loads((ROOT/'out/walk-grid.json').read_text())
report=[]

def spawn(cls,p=(0,0,-10000)):
    return unreal.AuditorSceneSetup.spawn_editor_actor(editor.get_editor_world(),cls,unreal.Transform(location=vec(p)))

def source(alias,path,scale=1):
    matches=[a for a in actors.get_all_level_actors() if unreal.Name('auditor_actor:'+alias) in a.tags]
    assert len(matches)<=1
    a=matches[0] if matches else spawn(unreal.StaticMeshActor)
    mesh=unreal.load_asset(path);assert mesh,path
    a.static_mesh_component.set_static_mesh(mesh)
    a.static_mesh_component.set_collision_profile_name('BlockAll')
    a.set_actor_scale3d(vec([scale]*3))
    a.tags=[unreal.Name('auditor_actor:'+alias)]
    a.set_actor_hidden_in_game(True);a.set_actor_enable_collision(False)
    return a

def rubrics(zh,en):
    result={}
    for lang,text in [('zh',zh),('en',en)]:
        first,sep,last=text.partition('。' if lang=='zh' else '. ')
        assert sep and last
        result[lang]=dict(criteria=first+('。' if lang=='zh' else '.'),expected=last,
                          steps='靠近并从不同角度观察物体。' if lang=='zh' else 'Approach and inspect the object from different viewpoints.')
    return result

for reg in regions:
    assert level.load_level(reg['map'])
    world=editor.get_editor_world()
    unreal.AuditorSceneSetup.prepare_editor_collision(world)
    def floor(p):
        hit=unreal.SystemLibrary.line_trace_single_by_profile(world,vec([p[0],p[1],-3580]),vec([p[0],p[1],-4000]),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
        assert hit and hit.to_tuple()[0],p
        return hit.to_tuple()[5].z
    def probe(center,target=None,lo=250,hi=450,nearest_to=None):
        candidates=[]
        for p in grid[reg['id']]['points'].values():
            if not lo<math.dist(p[:2],center[:2])<hi:continue
            hit=unreal.SystemLibrary.capsule_trace_single_by_profile(world,vec(p),vec([p[0],p[1],p[2]+.1]),30,90,'Pawn',False,[],unreal.DrawDebugTrace.NONE,True)
            if hit and hit.to_tuple()[0]:continue
            hit=unreal.SystemLibrary.line_trace_single_by_profile(world,vec([p[0],p[1],p[2]+70]),vec(center),'BlockAll',True,[],unreal.DrawDebugTrace.NONE,True)
            if hit and hit.to_tuple()[0] and not (target and hit.to_tuple()[10] in target.get_components_by_class(unreal.PrimitiveComponent)):continue
            candidates.append(p)
        assert candidates,('no probe',center)
        return min(candidates,key=lambda p:math.dist(p[:2],(nearest_to or reg['spawn'])[:2]))
    def semantic_add(id,alias,path,position,yaw,title,zh,en,scale=1,lo=250,hi=450,near_target=False):
        a=source(alias,path,scale)
        bounds=a.get_actor_bounds(False)
        bottom=bounds[0].z-bounds[1].z-a.get_actor_location().z
        position=[*position[:2],floor(position)-bottom]
        center=[*position[:2],floor(position)+bounds[1].z]
        t=dict(id=id,region=reg['id'],map=reg['map'],kind='semantic_add',target=alias,subcategory='S3',title=title,
               position=position,yaw=yaw,review_aim=center,probe=probe(center,lo=lo,hi=hi,nearest_to=center if near_target else None),rubrics_i18n=rubrics(zh,en))
        tasks[id]=t;report.append(t)
    if reg['id']=='market':
        lamp=next(a for a in actors.get_all_level_actors() if a.get_name()=='StaticMeshActor_383')
        tag=unreal.Name('auditor_actor:MarketOilLamp')
        if tag not in lamp.tags:lamp.tags=list(lamp.tags)+[tag]
        source('ModernDeskLamp','/Game/Auditor/MedievalVillage/ModernProps/DeskLamp/SM_DeskLamp',1.5)
        center=list(lamp.get_actor_bounds(False)[0].to_tuple())
        tasks['MV19']=dict(id='MV19',region='market',map=reg['map'],kind='semantic_replace',target='MarketOilLamp',source='ModernDeskLamp',
                          subcategory='S3',title='Modern electric desk lamp in the medieval market',probe=probe(center,lamp),review_aim=center,
                          rubrics_i18n=rubrics('中世纪市场里出现了现代电台灯。正常情况下照明器具应符合中世纪村庄的时代背景。',
                          'A modern electric desk lamp stands in the medieval market. Lighting equipment should fit the medieval setting.'))
        report.append(tasks['MV19'])
        semantic_add('MV20','ModernExtinguisher','/Game/Auditor/MedievalVillage/ModernProps/FireExtinguisher/SM_FireExtinguisher',[44200,26230],-90,
                     'Modern fire extinguisher beside a medieval stall',
                     '中世纪市场的摊位旁出现带压力表和软管的现代灭火器。正常情况下市场中的器具应符合中世纪的时代背景。',
                     'A modern fire extinguisher with a pressure gauge and hose stands beside a medieval market stall. Equipment in the market should fit its medieval era.',1.25)
    elif (ENV/'modern-props.json').exists():
        car=json.loads((ENV/'modern-props.json').read_text())['car']
        for a in list(actors.get_all_level_actors()):
            if unreal.Name('auditor_actor:ModernVending') in a.tags:actors.destroy_actor(a)
        semantic_add('MV18','ModernCar',car['mesh'],car.get('position',[41400,30550]),car.get('yaw',90),
                     'Automobile parked beyond the medieval courtyard',
                     '中世纪村庄庭院远处停着一辆现代汽车。正常情况下这里的交通工具应符合中世纪的时代背景。',
                     'A modern automobile is parked in the distance beyond the medieval courtyard. Vehicles here should fit the medieval era.',car.get('scale',1),650,950)
        house=json.loads((ENV/'modern-props.json').read_text()).get('house')
        if house:
            semantic_add('MV21','ModernHouse',house['mesh'],house['position'],house['yaw'],
                         'Modern apartment building in the medieval village',
                         '中世纪村庄里出现了一栋带玻璃橱窗的现代住宅楼。正常情况下建筑应符合中世纪村庄的时代背景。',
                         'A modern apartment building with glass storefront windows stands in the medieval village. Buildings should fit the medieval setting.',house.get('scale',1),1400,4500,True)
            if house.get('probe'):
                tasks['MV21']['probe']=house['probe']
    assert level.save_current_level()

catalog['tasks']=sorted(tasks.values(),key=lambda t:t['id'])
(ENV/'tasks.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
for reg in regions:
    assert level.load_level(reg['map'])
    controllers=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.AuditorTasks)]
    assert len(controllers)==1
    controllers[0].set_editor_property('catalog_json',json.dumps(catalog,ensure_ascii=False))
    assert level.save_current_level()
scenes=json.loads((ENV/'scene-descriptions.json').read_text())
for scene in scenes:
    scene['task_ids']=list(dict.fromkeys(scene['task_ids']+[t['id'] for t in catalog['tasks'] if t['map']==scene['map']]))
(ENV/'scene-descriptions.json').write_text(json.dumps(scenes,ensure_ascii=False,indent=2))
(OUT/'authored-cases.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('MODERN_CASES_AUTHORED',','.join(t['id'] for t in report),flush=True)
