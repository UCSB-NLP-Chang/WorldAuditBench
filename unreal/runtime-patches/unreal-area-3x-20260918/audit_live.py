from pathlib import Path
import json,math,sys
from collections import Counter
root=Path(__file__).parent
prod=Path('/home/ec2-user/unreal-production/audit')
catalog=json.loads((prod/'tasks.json').read_text())['tasks']
profiles=json.loads((prod/'runtime.json').read_text())['launch_profiles']
by_map={p['runtime_map']:p for p in profiles.values()}
rows=[];missing=[]
for task in catalog:
 if task.get('family') not in {'ancient','indoor','industrial','medieval','rural','subway','urban'}:continue
 p=by_map.get(task['map'])
 if p is None:missing.append(task['id']);continue
 path=next((a.split('=',1)[1] for a in p.get('extra_args',[]) if a.startswith('-AuditorExplorationPolicy=')),None)
 if not path:missing.append(task['id']);continue
 e=json.loads(Path(path).read_text())['tasks'].get(task['id'])
 if not e:missing.append(task['id']);continue
 old=math.prod(e['old_bounds_max'][i]-e['old_bounds_min'][i] for i in (0,1))/10000
 area=math.prod(e['bounds_max'][i]-e['bounds_min'][i] for i in (0,1))/10000
 excluded=sum(math.prod(b['max'][i]-b['min'][i] for i in (0,1))/10000 for b in e.get('excluded_bounds',[]))
 rows.append({'id':task['id'],'family':p['family'],'map':task['map'].split('?')[0],'old_area_m2':old,'area_m2':area,'ratio':area/old,'excluded_area_m2':excluded,'net_ratio':(area-excluded)/old,'old_height_cm':e['old_bounds_max'][2]-e['old_bounds_min'][2],'height_cm':e['bounds_max'][2]-e['bounds_min'][2],'bounds_min':e['bounds_min'],'bounds_max':e['bounds_max'],'revision':task['revision'],'policy_path':path})
assert len(rows)==143 and not missing,(len(rows),missing)
result={'rows':rows,'missing':missing,'count':len(rows),'families':dict(Counter(x['family'] for x in rows))}
if '--strict' in sys.argv:
 for x in rows:
  assert abs(x['ratio']-3)<1e-8,x
  assert 2.85<=x['net_ratio']<=3.05,x
  assert x['height_cm']==x['old_height_cm'],x
result['min_ratio']=min(x['ratio'] for x in rows);result['max_ratio']=max(x['ratio'] for x in rows)
name='after-audit.json' if '--strict' in sys.argv else 'before-audit.json'
(root/name).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
