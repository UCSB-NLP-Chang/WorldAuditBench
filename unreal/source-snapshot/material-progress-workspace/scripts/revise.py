"""Material taxonomy and reviewer-specific progress, applied to a fresh live copy."""
import copy, json, re
from pathlib import Path

VERSION='user-2026-09-13-material'
MATERIAL_IDS={'U045','JS_SP09','JS_CT09','JS_AF09','JS_HS09','JS_WT09','JS_WL09'}
DEFINITION={'zh':'物体表面的质感、纹理或反光特性与其应有材质明显不符；异常持续存在，不依赖视角、距离或时间变化。仅凭颜色少见或个人审美不足以判错。','en':'An object’s surface character, pattern or reflectance clearly conflicts with its expected material. The anomaly persists independently of viewpoint, distance or time; unusual color or aesthetic preference alone is insufficient.'}
def taxonomy(data):
    data=copy.deepcopy(data)
    data['taxonomy_version' if 'taxonomy_version' in data else 'version']=VERSION
    visual=next(c for c in data['categories'] if c['id']=='visual')
    sub={'code':'V4','id':'visual.material','name':{'zh':'材质异常','en':'Material anomalies'},'definition':DEFINITION}
    if isinstance(visual['name'],str):sub.update(name='材质异常',name_en='Material anomalies')
    assert not any(s.get('code')=='V4' for s in visual['subcategories'])
    visual['subcategories'].append(sub)
    visual['definition']={'zh':'物体的可见性、外观、光照与场景条件一致，表面质感与其应有材质相符。','en':'Object visibility, appearance and illumination are coherent with scene conditions, and surface character matches the expected material.'}
    if 'version_notes' in data:
        data['version_notes']['basis']='按用户确认保留五大类，新增视觉一致性子类 V4 材质异常，共 16 小类。语义类保持场景不相容、配置不合理、时代不相容。'
        data['version_notes']['out_of_scope']=[s for s in data['version_notes'].get('out_of_scope',[]) if s!='固定不变的材质损坏']
    return data

SURFACES={
 'JS_SP09':('石质花盆呈现均匀的亮洋红色，缺少应有的石材纹理与质感。','The stone planter has a uniform bright magenta surface without the expected stone pattern and surface character.'),
 'JS_CT09':('西侧山坡上的石井呈现均匀的亮洋红色，缺少应有的石材纹理与质感。','The stone well on the western hill has a uniform bright magenta surface without the expected stone pattern and surface character.'),
 'JS_AF09':('东北侧箱堆中的木箱呈现均匀的亮洋红色，缺少应有的木纹与木质质感。','The wooden crate in the northeast cluster has a uniform bright magenta surface without the expected wood grain and surface character.'),
 'JS_HS09':('电视柜呈现均匀的亮洋红色，缺少应有的家具表面细节与质感。','The TV cabinet has a uniform bright magenta surface without the expected furniture surface detail and character.'),
 'JS_WT09':('一块大岩石呈现均匀的亮洋红色，缺少应有的岩石纹理与质感。','A large rock has a uniform bright magenta surface without the expected rock pattern and surface character.'),
 'JS_WL09':('出生点旁的大岩石呈现均匀的亮洋红色，缺少应有的岩石纹理与质感。','The large boulder beside the starting point has a uniform bright magenta surface without the expected rock pattern and surface character.')}
def manifest(data):
    data=copy.deepcopy(data)
    if 'taxonomy_version' in data:data['taxonomy_version']=VERSION
    for t in data['tasks']:
        if t['id'] not in MATERIAL_IDS:continue
        t['subcategory']='V4';t.pop('taxonomy',None);t.pop('taxonomy_mapping',None)
        t['taxonomy_label']='视觉一致性 · 材质异常'
        if t['id'] in SURFACES:
            zh,en=SURFACES[t['id']]
            t['title']='Material anomaly';t['description']=en;t['description_i18n']={'zh':zh,'en':en}
            t['rubrics_i18n']['zh'].update(criteria=zh,expected='物体表面应具有与其材质相符的纹理和质感。')
            t['rubrics_i18n']['en'].update(criteria=en,expected='The object should have surface detail and character consistent with its material.')
            t['rubrics']=zh+'\n'+en
    return data

def replace(source,old,new):
    assert source.count(old)==1,old[:100]
    return source.replace(old,new)

def patch(stage):
    p=stage/'taxonomy.json';definition=taxonomy(json.loads(p.read_text()));p.write_text(json.dumps(definition,ensure_ascii=False,indent=2)+'\n')
    p=stage/'tasks.json';p.write_text(json.dumps(manifest(json.loads(p.read_text())),ensure_ascii=False,indent=2)+'\n')
    p=stage/'taxonomy.py';p.write_text(p.read_text().replace('fifteen observable bug types','sixteen observable bug types'))
    p=stage/'server.py';s=p.read_text()
    s=replace(s,'            total_reviews={}\n','''            # Public stable selectors contain no login credentials or internal owner values.
            reviewer_key=lambda owner: hashlib.sha256(('progress-reviewer:'+owner).encode()).hexdigest()
            names={owner:v.get('reviewer','Reviewer') for (_,owner),v in latest.items()}
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='participants'").fetchone():
                names.update({r['id']:r['name'] for r in self.db.execute('SELECT id,name FROM participants')})
            names[user['owner']]=user['reviewer']
            reviewer_options=[{'id':reviewer_key(owner),'name':name,'mine':owner==user['owner']} for owner,name in names.items()]
            reviewer_options.sort(key=lambda r:(not r['mine'],r['name'].casefold(),r['id']))
            total_reviews={}
''')
    s=replace(s,"'accepted':len(approvals)>=2,'my_quality':", "'reviewer_results':[{'id':reviewer_key(owner),'quality':v['quality']} for (tid,owner),v in latest.items() if tid==task['id']],\n                    'accepted':len(approvals)>=2,'my_quality':")
    s=replace(s,"'queue':queue,'tasks':progress,'taxonomy'", "'queue':queue,'tasks':progress,'reviewer_options':reviewer_options,'taxonomy'")
    p.write_text(s)
    p=stage/'tests/test_semantic_compatibility.py';p.write_text(p.read_text().replace('user-2026-09-13-visibility',VERSION))
    p=stage/'static/app.js';s=p.read_text()
    s,n=re.subn(r'^const taxonomyDefinition=.*?;$',lambda _: 'const taxonomyDefinition='+json.dumps(definition,ensure_ascii=False,separators=(',',':'))+';',s,count=1,flags=re.M);assert n==1
    start=s.index('function renderProgress(){');end=s.index('function taxonomyShort',start)
    s=s[:start]+(Path(__file__).with_name('progress.js').read_text())+'\n'+s[end:]
    s=replace(s,"if($('progress-engine'))$('progress-engine').value=taxonomyEngine;$('progress-taxonomy').value=sub.code;", "if($('progress-engine'))$('progress-engine').value=taxonomyEngine;$('progress-environment').value='';$('progress-reviewer').value='';$('progress-taxonomy').value=sub.code;")
    p.write_text(s)
    p=stage/'static/index.html';s=p.read_text()
    anchor='<label class="sr-only" for="progress-taxonomy">Type</label>'
    s=replace(s,anchor,'<label class="sr-only" for="progress-environment">Environment</label><select id="progress-environment" aria-label="Environment"><option value="">All environments</option></select><label class="sr-only" for="progress-reviewer">Reviewer</label><select id="progress-reviewer" aria-label="Reviewer"><option value="">All reviewers</option></select>'+anchor)
    s=replace(s,'<select id="progress-filter">','<select id="progress-filter" aria-label="Task status"><option value="">All tasks</option>')
    s=replace(s,'<th>Your review</th>','<th id="progress-review-heading">Your review</th>')
    s=replace(s,'Each reviewer’s latest review of the current version counts.','Each reviewer’s latest review of the current version counts. Select a reviewer to see their reviewed tasks and latest results.')
    p.write_text(s)
    p=stage/'static/style.css'
    if not p.exists():p=next((stage/'static').glob('*.css'))
    with p.open('a') as f:f.write('\n/* The visual category has four subtypes. */\n@media(min-width:601px){.taxonomy-card[data-category=visual] .taxonomy-types{grid-template-columns:repeat(2,minmax(0,1fr))}}\n.progress-filters{justify-content:flex-end;max-width:750px}.progress-quality{font-weight:600}.progress-quality.pass{color:#256341}.progress-quality.fail{color:#a33434}.progress-quality.uncertain{color:#826417}\n')
    p=stage/'tests/test_taxonomy.py';s=p.read_text().replace('five_categories_fifteen_types','five_categories_sixteen_types').replace("len(category['subcategories']),3","len(category['subcategories']),4 if category['id']=='visual' else 3").replace('len(set(codes)),15','len(set(codes)),16')
    s=s.replace("{'U045','JS_SP09','JS_CT09','JS_AF09','JS_HS09','JS_WT09','JS_WT16','JS_WT17','JS_WL09'}","{'JS_WT16','JS_WT17'}")
    s=s.replace("self.assertEqual(s.tasks['U045']['taxonomy_mapping']['status'],'no_exact_service_subcategory')","self.assertEqual(s.tasks['U045']['taxonomy']['code'],'V4')")
    s=s.replace("),225)","),232)")
    p.write_text(s)
