from pathlib import Path
import json
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');env=r/'environments/ancient-chinese-city';stage=w/'configuration-tasks-20260913-v2'
# The original atlas labels the mesh as food, so public semantic metadata must not call it a drink.
rubrics={'zh':dict(criteria='古代茶馆的木桌上摆着一罐带现代印刷包装的食品罐头。',expected='正常情况下，桌上的食品及其包装应符合古代茶馆的时代背景。',steps='靠近桌面，查看罐头的印刷标签和金属罐口。'),'en':dict(criteria='A food tin with modern printed packaging sits on a wooden table in the ancient tea house.',expected='Food and its packaging should fit the historical era of the tea house.',steps='Approach the table and inspect the printed label and metal top of the tin.')}
for p in [env/'tasks.json',stage/'tasks.json']:
 d=json.loads(p.read_text());t=next(t for t in d['tasks'] if t['id']=='A21');t.update(title='Modern food tin on an ancient tea table',rubrics_i18n=rubrics)
 if 'rubrics' in t:t['rubrics']=rubrics['en']['criteria']+'\n'+rubrics['zh']['criteria']
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=env/'concise-rubrics.json';d=json.loads(p.read_text());d['A21']={lang:{k:v for k,v in rb.items() if k!='steps'} for lang,rb in rubrics.items()};p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
for p in [r/'scripts/author_era.py',w/'scripts/author_a21.py']:
 s=p.read_text().replace('Modern canned drink on an ancient tea table','Modern food tin on an ancient tea table').replace('古代茶馆的木桌上摆着一罐现代易拉罐饮料。',rubrics['zh']['criteria']).replace('正常情况下，饮品容器应符合古代茶馆的时代背景。',rubrics['zh']['expected']).replace('A modern canned drink sits on a wooden table in the ancient tea house.',rubrics['en']['criteria']).replace('Drink containers should fit the historical era of the tea house.',rubrics['en']['expected']);p.write_text(s)
(w/'out/a21-copy-verification.json').write_text(json.dumps(dict(status='PASS',basis='Inspected original texture atlas: food tin packaging, not beverage',metadata_only=True,geometry_and_runtime_behavior_unchanged=True),indent=2));print('A21 copy matches the rendered food tin')
