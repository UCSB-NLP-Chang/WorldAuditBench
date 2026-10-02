"""Stage the validated Concourse-only package against the current Review catalog."""
from pathlib import Path
import json,hashlib,copy,sys
p=Path('/home/ec2-user/unreal-production');r=Path('/home/ec2-user/unreal-review-releases/exploration-v2-preview-20260917');c=Path('/home/ec2-user/unreal-review-releases/concourse-cleanup-20260918')
def sha(f):
 h=hashlib.sha256()
 with Path(f).open('rb') as s:
  for block in iter(lambda:s.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
def save(f,v):f.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');f.chmod(0o600)
files=[p/'audit/tasks.json',p/'audit/runtime.json',r/'runtime/runtime.json',r/'runtime/manifest.json',r/'runtime/scheduler.json',p/'shared/production-links/review-v2/review.json']
old=[json.loads(f.read_text()) for f in files];cat,rt,rt_pool,manifest,scheduler,link=copy.deepcopy(old)
assert rt==rt_pool
build=json.loads((c/'build.json').read_text());binary=c/'package-v2/Linux/Subway/Binaries/Linux/Subway';assert sha(binary)==build['binary_sha256']
qa=json.loads((c/'qa.json').read_text());assert qa['status']=='PASS' and qa['build_sha256']==build['binary_sha256'] and qa['map_sha256']==build['map_sha256']
ids={t['id'] for t in cat['tasks'] if t.get('family')=='subway' and '/Concourse' in t['map']};assert ids=={'B01','S01','S07','S09','S12','S14','S22'}
changed={}
for t in cat['tasks']:
 if t['id'] not in ids:continue
 previous={k:t[k] for k in ['revision','sha256','build_sha256']};aliases=t.setdefault('review_compatible_versions',[])
 if previous not in aliases:aliases.append(previous)
 t.update(revision=t['revision']+1,sha256=build['map_sha256'],build_sha256=build['binary_sha256'],scene_repair={'release':'concourse-cleanup-20260918','target_and_rubrics_unchanged':True})
 key=next(k for k,v in rt['launch_profiles'].items() if v.get('runtime_map')==t['map']);v=rt['launch_profiles'][key];v.update(binary=str(binary),build_sha256=build['binary_sha256']);changed[key]=t['id'];link['task_ids'][t['id']]={'id':'review:'+t['id']+':'+build['map_sha256'][:12],'sha256':build['map_sha256']}
for t in manifest['tasks']:
 if t['map'] in changed:t['build_sha256']=build['binary_sha256']
for t in scheduler['tasks']:
 if t['map'] in changed:
  tid=changed[t['map']];profile=rt['launch_profiles'][t['map']];policy=next(a for a in profile['extra_args'] if a.startswith('-AuditorExplorationPolicy='));t.update(id=link['task_ids'][tid]['id'],group=hashlib.sha256((str(binary)+policy).encode()).hexdigest())
scheduler['clients']['review']['tasks']=[t['id'] for t in scheduler['tasks']];scheduler['database']=str(r/'runtime/pool-concourse-cleanup-20260918.sqlite3')
previous={t['id']:t for t in old[0]['tasks']}
for t in cat['tasks']:
 if t['id'] not in ids:assert t==previous[t['id']]
 else:
  assert t['rubrics_i18n']==previous[t['id']]['rubrics_i18n']
  key=next(k for k,v in rt['launch_profiles'].items() if v.get('runtime_map')==t['map']);assert rt['launch_profiles'][key]['extra_args']==old[1]['launch_profiles'][key]['extra_args']
for key,v in rt['launch_profiles'].items():
 if key not in changed:assert v==old[1]['launch_profiles'][key]
for i,v in enumerate([cat,rt,rt,manifest,scheduler,link]):save(c/f'config-{i}.json',v)
sys.path.insert(0,str(p/'code/explore'));from bf.cost_scheduler import Scheduler
Scheduler(scheduler['database'],scheduler['tasks'],**scheduler['limits'])
receipt={'status':'staged','files':[str(f) for f in files],'tasks':sorted(ids),'description':'Repair Concourse background geometry and surface rendering, preserve task targets and frozen starts','expected_live_sha256':{str(f):sha(f) for f in files},'candidate_sha256':{str(i):sha(c/f'config-{i}.json') for i in range(len(files))}}
save(c/'completion.json',receipt);print('Staged',sorted(ids),'total catalog',len(cat['tasks']))
