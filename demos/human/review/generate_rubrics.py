from pathlib import Path
import json
r=Path('/home/ubuntu/unreal-auditor/review-service/releases/unified-20260911')
# English text is authored against the current task definitions; the UI shows both languages together.
en={
'S01':('A waiting bench rests on the floor with supported legs.','Approach the concourse bench and inspect the gap from several angles.','The entire bench floats about 60 cm above its support surface.'),
'S02':('A single complete bench occupies the waiting area.','Inspect the trackside bench from the front and side.','Two solid bench frames and seats overlap and intersect.'),
'S03':('An adult waiting seat has a usable seat height, about 45 cm.','Compare the trackside bench with nearby normal seating.','The bench is stretched vertically to roughly three times its height; its seat is about 135 cm high.'),
'S04':('Bench legs rest on top of the platform floor.','Inspect the platform bench where its legs meet the floor.','The legs and lower structure are embedded about 30 cm into the solid floor.'),
'S05':('Under the same gentle contact, the bin should tip onto its side and settle.', 'Walk into the bin in the open area, then step back and observe its rotation and final pose.', 'Contact makes the bin overturn vertically by about 180 degrees and settle upside down on its rim; the clean control tips about 90 degrees and rests on its side.'),
'S06':('The solid vending machine blocks the player.','Walk directly toward and through the platform vending machine; compare with the baseline.','The player can pass through the visible machine.'),
'S07':('An open corridor wide enough for the player is traversable.','Try to cross the middle of the concourse corridor in both directions.','An invisible obstruction blocks the interior corridor, away from the environment boundary.'),
'S08':('The open trackside walkway is traversable.','Walk along the trackside passage and attempt to cross the obstructed area.','An invisible wall blocks movement without matching visible geometry; it is not the task boundary.'),
'S09':('An unobstructed bench remains visible as the viewing angle changes.','Look directly at the concourse bench, then turn slightly aside.','The bench disappears when viewed directly and reappears at a slightly different angle.'),
'S10':('The bin maintains a consistent shape across nearby viewing distances.','Move toward and away from the trackside bin across a distance of about 3 m.','Its visible size jumps abruptly at the distance threshold while its collision shape stays unchanged.'),
'S11':('A vending machine remains visible from a few metres away.','Move beyond about 3.6 m from the platform machine, then approach it again.','The machine disappears prematurely at the threshold and reappears when approached.'),
'S12':('The bench and its shadow align consistently with the fixed lighting.','Compare the concourse bench with its shadow on the floor.','The shadow is displaced by about 180 cm while the physical bench stays in place.'),
'S13':('The same bench still exists after looking away and back.','Observe the trackside bench clearly, turn away, then look back and vary the viewing angle.','The bench remains absent after returning; changing the viewing angle does not restore it.'),
'S14':('The bin keeps its position when the player leaves and returns.','Observe it within about 2.5 m, turn away and move beyond 4.5 m, then return.','The same bin has moved about 250 cm and stays at the new position.'),
'S15':('The marked ventilation fan continues rotating in its fixed direction.','Watch its continuous rotation, turn away, then look back without operating any control.','The fan reverses direction and continues rotating in reverse without player input.'),
'S16':('Posters fixed to the wall should remain present.', 'You start facing both posters. Watch for about 15 seconds to see whether one disappears.', 'One wall poster disappears after a short time without anyone touching it.'),
'S17':('Waiting-bench seats remain available for passengers to sit on.','Inspect the concourse bench and the object occupying its seat.','A supported, fixed bin occupies the seating surface and prevents its intended use.'),
'S18':('The vending machine faces an accessible passenger area.','Walk around the platform machine and locate its controls and product display.','The machine stands on the floor without intersecting the wall, but its operating face points into the wall and is inaccessible.'),
'S19':('This station uses fixed pairs of up and down escalators.','Watch the moving treads; compare with the Platform baseline using the task selector.','All eight escalators run upwards, leaving no down escalator. Check motion over time, not a single still frame.'),
'H01':('The armchair rests on the living-room floor.','Approach the armchair and inspect its feet from different angles.','The armchair floats about 45 cm above the floor without support.'),
'H02':('The dining chair and tabletop do not intersect.','Inspect the chair back and tabletop from the side.','The chair back passes through the solid tabletop.'),
'H03':('A dining chair has proportions compatible with sitting at its table.','Compare the affected chair with the dining table and matching chairs.','The chair is stretched vertically and its seat is above the tabletop, preventing normal use.'),
'H04':('The refrigerator blocks the player as a solid object.','Walk directly into the refrigerator; compare with the clean baseline.','The player passes through the visible refrigerator.'),
'H05':('The open kitchen passage allows the player through.','Attempt to cross the internal kitchen/dining passage.','An invisible wall blocks an otherwise open passage away from the task boundary.'),
'H06':('A released cup lands on the table and settles.','Approach and aim at the dining-table cup, then press E to lift and release it.','After actual contact with the table, the cup repeatedly bounces without further input; compare with the cup settling in the clean control.'),
'H07':('The unobstructed television stays visible from nearby viewing angles.','Face the living-room television, then change the viewing angle slightly.','The television disappears and reappears depending on the angle, without being occluded.'),
'H08':('The pot keeps its physical proportions as viewing distance changes.','Walk between the dining-table area and the far end of the kitchen, crossing about 2.6 m from the pot.','The pot abruptly changes visible size at the distance threshold.'),
'H09':('The armchair casts a shadow consistent with its position and fixed lighting.','Compare the armchair and its floor shadow while moving the viewpoint slightly.','The cast shadow is displaced from the chair; the chair itself stays in place.'),
'H10':('The floor plant remains present when the player leaves and returns.','Observe the plant near the television, turn away, walk to the far end of the living room, then return.','The plant is missing on return and remains absent when the original viewpoint is restored.'),
'H11':('The cup keeps its colour when left alone.','Observe the dining-table cup, turn away, walk to the other end of the kitchen, then return.','The same cup has changed colour and retains that colour under comparable lighting.'),
'H12':('The bedroom fan starts switched off and stays off without an operation.','Watch the stationary blades, enter the bathroom, then return and observe the fan continuously.','The fan has started rotating without any fan-control input; sustained motion is required as evidence.'),
'H13':('The cabinet door has enough clearance to open in the normal layout.','Approach the bedroom/bathroom cabinet, aim at its door and press E; compare with the clean control.','Furniture occupies the door swing area and prevents the cabinet door from opening normally.')}
zh_h={
'H01':('单人沙发支撑在客厅地面上。','走近沙发，从不同角度检查椅脚与地面的关系。','沙发无支撑地悬空约 45 cm。'),
'H02':('餐椅与桌面不应相互穿插。','从侧面检查餐椅椅背与桌面的交界。','椅背穿过实体桌面。'),
'H03':('餐椅的比例应允许人在餐桌旁正常落座。','对比异常餐椅、同套餐椅与餐桌的高度。','餐椅纵向拉长，座面高于桌面，无法正常使用。'),
'H04':('冰箱作为实体应阻挡人物。','朝冰箱正面行走，并与正常基准对照。','人物可以穿过可见的冰箱实体。'),
'H05':('厨房内部开放通道应可通行。','尝试穿过厨房与餐区之间的内部通道。','没有对应可见物体的空气墙阻挡通行，且不位于任务边界。'),
'H06':('松手后的杯子落到桌面并稳定下来。','走近并瞄准餐桌杯子，按 E 执行抬起再松手。','杯子真实接触桌面后，无后续操作仍反复异常弹跳；正常对照会落稳。'),
'H07':('无遮挡的电视随相邻视角变化保持可见。','正对客厅电视，再略微改变观察角度。','电视在没有遮挡的情况下随角度消失、恢复。'),
'H08':('锅的比例随观察距离变化保持一致。','在餐桌附近与厨房远端往返，跨过距锅约 2.6 m 的位置。','锅的外观尺寸在距离阈值处突然改变。'),
'H09':('固定照明下，沙发与地板投影的位置应相互对应。','比较沙发实体与地面阴影，并略微移动视角核验。','沙发实体位置不变，投影却明显错位。'),
'H10':('无人操作时，离开再返回后落地盆栽仍应存在。','看清电视旁的落地盆栽，背向它走到客厅另一端，再返回。','盆栽在返回后消失，恢复原视角也不恢复。'),
'H11':('无人操作时，杯子的颜色应保持不变。','看清餐桌杯子，背向餐桌走到厨房另一端，再返回。','在可比较的光照下，同一杯子颜色改变并持续保持。'),
'H12':('卧室风扇初始关闭，未操作时应保持关闭。','先连续观察扇叶静止，进入浴室，再返回连续观察风扇。','没有风扇控制输入，扇叶却自行开始持续旋转；需观察连续运动。'),
'H13':('正常家具布局应留出柜门开启空间。','走到卧室／浴室连接处的柜子，瞄准柜门按 E，并与正常对照比较。','家具占据柜门开启空间，使柜门无法正常打开。')}
sub=json.loads(Path('/home/ubuntu/unreal-auditor/subway-workspace/environments/subway/tasks.json').read_text())['tasks']
out={}
for t in sub:
 z=(t['expected_behavior'],t['trigger'],t['observable_failure'])
 if t['id']=='S06':z=(z[0],'朝站台售货机实体直走，尝试穿过，并与正常基准对照。',z[2])
 if t['id'] in ('S07','S08'):z=(z[0],'沿开放通道行走并尝试穿过受阻位置，确认它不位于任务边界。',z[2])
 if t['id']=='S12':z=(z[0],'比较大厅长椅实体与地面投影的位置。','长椅实体位置不变，投影明显错开约 180 cm。')
 if t['id']=='S19':z=(z[0],'连续观察扶梯踏步；通过任务选择器切换至站台基准，对比成对反向运行。','8 部扶梯全部上行，不再提供下行通行；需观察连续运动，不能只看静态截图。')
 out[t['id']]={'zh':dict(zip(('expected','steps','criteria'),z)),'en':dict(zip(('expected','steps','criteria'),en[t['id']]))}
for id,z in zh_h.items():out[id]={'zh':dict(zip(('expected','steps','criteria'),z)),'en':dict(zip(('expected','steps','criteria'),en[id]))}
for id,zh,label in [('B01','地铁站厅','Subway concourse'),('B02','地铁站台与扶梯','Subway platform and escalators'),('B03','列车旁站台','Train-side platform'),('HB01','客厅','Living room'),('HB02','厨房与餐区','Kitchen and dining room'),('HB03','卧室与浴室','Bedroom and bathroom')]:
 out[id]={'zh':{'expected':zh+'为无任务异常注入的正常对照。','steps':'在规定范围内探索，观察物体与通道；与对应异常任务执行相同检查。','criteria':'正常对照不应出现相应任务的异常。发现其他问题时记录位置、操作及证据，不自动判定任务通过。'},'en':{'expected':label+' is a clean control with no task-specific bug injected.','steps':'Explore within the region and repeat the same observations or interactions used for the matching bug task.','criteria':'The control should not show the matching injected anomaly. Record any other issue with its location, steps and evidence; do not automatically approve the task.'}}
out['B02']['zh']['criteria']='8 部扶梯应为 4 部上行、4 部下行，成对提供双向通行；对照 S19 观察踏步连续运动。'
out['B02']['en']['criteria']='The eight escalators comprise four up and four down, paired for both directions. Compare continuous tread motion with S19.'
out['U018']={'zh':{'expected':'建筑阴影中的金属桶应保留纹理，并正常响应环境光照。','steps':'比较阴影中的左侧金属桶与旁边同款桶，从相近角度观察明暗。','criteria':'左侧桶保留纹理，却异常均匀明亮、不正常响应光照；旁边同款桶保持正常明暗。'},'en':{'expected':'Metal drums in the building shadow retain their textures and respond normally to lighting.','steps':'Compare the left metal drum in the shadow with the matching drum beside it from similar viewing angles.','criteria':'The left drum retains its texture but appears abnormally bright and evenly lit, while the neighbouring matching drum shows normal light and shade.'}}
assert len(out)==39
(r/'rubrics.bilingual.json').write_text(json.dumps({'schema_version':1,'rubrics':out},ensure_ascii=False,indent=2)+'\n')
print('Authored Chinese and English rubrics for all 39 entries: 33 bug tasks and 6 baselines.')