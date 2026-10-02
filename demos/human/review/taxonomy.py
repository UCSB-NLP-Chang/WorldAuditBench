"""Canonical user taxonomy: five categories, fifteen observable bug types."""
import json
from pathlib import Path
TAXONOMY=json.loads(Path(__file__).with_name('taxonomy.json').read_text())
LOOKUP={}
for category in TAXONOMY['categories']:
    for sub in category['subcategories']:
        value={'version':TAXONOMY['version'],'category_id':category['id'],'category':category['name'],
               'code':sub['code'],'subcategory_id':sub['id'],'subcategory':sub['name']}
        LOOKUP[sub['id']]=LOOKUP[sub['code']]=value

def classify(task):
    if task.get('case_type')=='baseline':return None
    return LOOKUP.get(TAXONOMY.get('task_overrides',{}).get(task.get('id'),task.get('subcategory')))

def summarize(tasks):
    categories=[]
    for category in TAXONOMY['categories']:
        children=[]
        for sub in category['subcategories']:
            matching=[t for t in tasks if t.get('taxonomy',{}).get('code')==sub['code'] and t['case_type']!='baseline']
            children.append({**sub,'tasks':len(matching),'accepted':sum(t['accepted'] for t in matching)})
        categories.append({**category,'subcategories':children,'tasks':sum(s['tasks'] for s in children),'accepted':sum(s['accepted'] for s in children)})
    return {'version':TAXONOMY['version'],'categories':categories,
            'unclassified':sum(t['case_type']!='baseline' and not t.get('taxonomy') for t in tasks)}
