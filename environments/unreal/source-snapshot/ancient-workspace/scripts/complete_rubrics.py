import json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace/environments/ancient-chinese-city');p=r/'tasks.json';data=json.loads(p.read_text())
normal={
'A01':('The bench legs rest on the ground.','木凳的凳脚应落在地面上。'),
'A02':('The stone lion rests on its supporting surface.','石狮底座应落在支撑面上。'),
'A03':('Each tea table occupies its own space without intersecting another table.','各张茶桌应有独立位置，彼此不应穿插。'),
'A04':('The stall has one aligned canopy frame.','摊位应只有一套正常对齐的棚架。'),
'A05':('The bench seat is below the matching tabletop at a usable adult seating height.','凳面应低于配套桌面，高度适合成人就座。'),
'A06':('The dining tabletop is above the surrounding matching bench seats.','用餐桌面应高于周围配套凳子的凳面。'),
'A07':('The solid wooden table blocks the player.','实体木桌应阻挡人物。'),
'A08':('The visibly empty passage allows the player to walk through.','清晰可见的空通道应允许人物经过。'),
'A09':('The basket falls, contacts the ground and settles after release.','藤筐被释放后应落地并逐渐停止运动。'),
'A10':('The stone lion remains visible while the camera turns around it.','转动视角时，石狮应保持可见。'),
'A11':('The canopy stays visible over the short viewing distances inside this scene.','在场景内短距离移动观察时，棚架应保持可见。'),
'A12':('The same bench retains its shape and scale as viewing distance changes.','观察距离改变时，同一木凳的外形与尺寸应保持一致。'),
'A13':('The lion shadow is consistent with its location and the light direction.','石狮的阴影应与其位置和光照方向一致。'),
'A14':('An untouched basket remains in place after leaving and returning.','未被操作的藤筐在离开再返回后应仍然存在。'),
'A15':('An untouched bench remains at the same position between visits.','无人搬动时，木凳在两次观察之间应保持原位。'),
'A16':('The lantern keeps the same colour between visits.','灯笼在两次观察之间应保持相同颜色。'),
'A17':('The door remains closed until the reviewer opens it with E.','门扇应保持关闭，直到评审人按 E 打开。'),
'A18':('Furniture placement leaves the tea-house passage usable.','家具摆放应保留茶馆通道的正常通行空间。'),
'A19':('The open half of the entrance remains passable.','大门打开的一侧应保留正常通行空间。'),
'A20':('Props match the ancient Chinese setting.','场景物品应符合中国古代背景设定。')}
steps={
'A01':('Approach the market bench and inspect the space beneath its legs.','靠近集市木凳，查看凳脚下方。'),
'A02':('Approach the stone lion on the left of the residence entrance and inspect its base.','靠近宅院入口左侧石狮，查看其底座。'),
'A03':('Walk around the tea table and inspect its tabletop and legs.','绕茶桌观察桌面和桌腿。'),
'A04':('Approach the market stall and inspect its canopy posts and roof.','靠近集市摊位，查看棚架立柱与顶棚。'),
'A05':('Compare the tea-house bench seat with its matching table.','对比茶馆木凳凳面与配套桌面的高度。'),
'A06':('Compare the market tabletop with the surrounding bench seats.','对比集市木桌桌面与周围凳面的高度。'),
'A07':('Walk directly toward the market table and attempt to cross its footprint.','朝集市木桌直走，尝试穿过桌子占据的区域。'),
'A08':('Walk along the clear passage beside the tea-house entrance.','沿茶馆入口旁清晰可见的通道行走。'),
'A09':('Aim at the loose wicker basket, press E once, then watch it after it lands.','对准单独摆放的藤筐按一次 E，观察它落地后的运动。'),
'A10':('Center the left stone lion in view, then turn slightly left or right.','把左侧石狮置于视野中央，再稍微左右转动视角。'),
'A11':('Observe the stall canopy nearby, back away several metres, then approach again.','近距离观察摊位棚架，后退几米，再靠近。'),
'A12':('Observe the tea-house bench nearby, walk farther away, then approach again.','近距离观察茶馆木凳，走远一些，再靠近。'),
'A13':('Inspect the left stone lion and the surrounding ground shadow from several angles.','从几个角度查看左侧石狮及周围地面的阴影。'),
'A14':('Observe the basket without pressing E, turn away and walk several metres away, then return.','先观察藤筐，不按 E，转身走远几米后再返回。'),
'A15':('Observe the tea-house bench, turn away and walk to the far end of the passage, then return.','先观察茶馆木凳，转身走到通道远端，再返回。'),
'A16':('Observe the right entrance lantern, walk away while looking away, then return.','先观察入口右侧灯笼，背向它走远，再返回。'),
'A17':('Observe the closed door leaf, walk away from the entrance while facing away, then return without pressing E.','先观察关闭的门扇，背向入口走远，不按 E，再返回。'),
'A18':('Approach the table in the tea-house passage and try to walk past it.','靠近茶馆通道中的木桌，尝试从通道经过。'),
'A19':('Approach the open half of the residence doorway and try to pass through.','靠近宅院大门打开的一侧，尝试穿过门口。'),
'A20':('Explore the market stalls and inspect the machine placed beside them.','沿集市摊位行走，观察摊位旁摆放的机器。')}
# Current interaction rubric overrides are kept beside the catalog.
overrides=json.loads((r/'interaction-rubric-overrides.json').read_text())
for t in data['tasks']:
 if t['id'] not in normal:
  assert t['id'] in ('A21','A22','A23','A24');continue
 for i,lang in enumerate(['en','zh']):t['rubrics_i18n'][lang].update(expected=normal[t['id']][i],steps=steps[t['id']][i])
for t in data['tasks']:
 if t['id'] in overrides:
  for lang in ['en','zh']:t['rubrics_i18n'][lang].update(overrides[t['id']][lang])
concise=json.loads((r/'concise-rubrics.json').read_text())
for t in data['tasks']:
 for lang in ['en','zh']:t['rubrics_i18n'][lang].update(concise[t['id']][lang])
p.write_text(json.dumps(data,ensure_ascii=False,indent=2));(r/'rubrics.bilingual.json').write_text(json.dumps({t['id']:t['rubrics_i18n'] for t in data['tasks']},ensure_ascii=False,indent=2))
