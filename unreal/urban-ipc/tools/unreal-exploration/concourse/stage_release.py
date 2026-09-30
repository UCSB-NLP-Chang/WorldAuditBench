from pathlib import Path
import json,hashlib,copy,sys,sqlite3
p=Path('/home/ec2-user/unreal-production');r=Path('/home/ec2-user/unreal-review-releases/exploration-v2-preview-20260917');c=Path('/home/ec2-user/unreal-review-releases/exploration-v2-medieval-20260917')
def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as stream:
  for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
def write(f,d):f.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');f.chmod(0o600)
receipt=json.loads((c/'completion.json').read_text());assert receipt['status']=='held_for_concourse_fixes'
for f,h in receipt['expected_live_sha256'].items():assert sha(Path(f))==h,f
build=json.loads((c/'concourse-build.json').read_text());binary=c/'concourse-package-v1/Linux/Subway/Binaries/Linux/Subway';assert sha(binary)==build['binary_sha256'];qa=json.loads((c/'concourse-validation.json').read_text());policy=c/'concourse-policy.json';assert qa['status']=='PASS' and qa['policy_sha256']==sha(policy) and qa['binary_sha256']==sha(binary)
ids={t['id'] for t in qa['tasks']};assert ids=={'B01','S01','S05','S07','S09','S12','S14','S22'}
cat=json.loads((c/'config-0.json').read_text());runtime=json.loads((c/'config-2.json').read_text());manifest=json.loads((c/'config-3.json').read_text());scheduler=json.loads((c/'config-4.json').read_text());link_path=p/'shared/production-links/review-v2/review.json';link=json.loads(link_path.read_text());live={t['id']:t for t in json.loads((p/'audit/tasks.json').read_text())['tasks']};spec=json.loads((c/'concourse-S22-draft.json').read_text());draft=copy.deepcopy(live['S01']);draft.update(id='S22',case_id='S22',revision=1,map='/Game/Auditor/Subway/Concourse?Task=S22',case_path='/?case=S22',title=spec['title']+'（候选）',subcategory='V1',taxonomy_label=live['S21']['taxonomy_label'],rubrics_i18n=spec['rubrics_i18n'],candidate_status='draft');draft.pop('review_compatible_versions',None)
z=spec['rubrics_i18n']['zh'];en=spec['rubrics_i18n']['en'];draft['rubrics']=f"中文\n正常预期: {z['expected']}\n复现步骤: {z['steps']}\n判定标准: {z['criteria']}\nEnglish\nExpected behavior: {en['expected']}\nReview steps: {en['steps']}\nAcceptance criteria: {en['criteria']}";cat['tasks'].append(draft)
profiles=runtime['launch_profiles'];s01key=next(k for k,v in profiles.items() if v.get('runtime_map')==live['S01']['map']);newkey='/Shared/review/'+hashlib.sha256(b'review-concourse-20260917:S22').hexdigest()[:24];assert newkey not in profiles;profiles[newkey]=copy.deepcopy(profiles[s01key]);profiles[newkey]['runtime_map']=draft['map'];manifest['tasks'].append({'map':newkey,'build_sha256':build['binary_sha256']});s22=copy.deepcopy(next(t for t in scheduler['tasks'] if t['case_key']=='S01'));s22.update(case_key='S22',map=newkey,runtime_map=draft['map'],category=draft['taxonomy_label']);scheduler['tasks'].append(s22)
changed_keys={}
for task in cat['tasks']:
 if task['id'] not in ids:continue
 task['revision']=live[task['id']]['revision']+1 if task['id'] in live else 1
 task.update(sha256=build['map_sha256'],build_sha256=build['binary_sha256'],exploration_revision={'version':'unreal-review-concourse-20260917-v1','policy_sha256':qa['policy_sha256'],'previous_build_sha256':live.get(task['id'],{}).get('build_sha256')});task.pop('review_compatible_versions',None)
 key=next(k for k,v in profiles.items() if v.get('runtime_map')==task['map']);v=profiles[key];v.update(binary=str(binary),build_sha256=build['binary_sha256']);v['extra_args']=[a for a in v['extra_args'] if not a.startswith('-AuditorExploration')]+['-AuditorExplorationPolicy='+str(policy),'-AuditorExplorationTask='+task['id']];changed_keys[key]=task['id'];link['task_ids'][task['id']]={'id':'review:'+task['id']+':'+build['map_sha256'][:12],'sha256':build['map_sha256']}
for task in manifest['tasks']:
 if task['map'] in changed_keys:task['build_sha256']=build['binary_sha256']
for task in scheduler['tasks']:
 if task['map'] in changed_keys:
  id=changed_keys[task['map']];task.update(id=link['task_ids'][id]['id'],group=hashlib.sha256((str(binary)+qa['policy_sha256']).encode()).hexdigest())
scheduler['clients']['review']['tasks']=[t['id'] for t in scheduler['tasks']];scheduler['database']=str(r/'runtime/pool-concourse-complete.sqlite3')
for name in ids:assert name in link['task_ids']
# Three.js and all previously revised unrelated cases remain byte-for-byte equal as data.
previous={t['id']:t for t in json.loads((c/'config-0.json').read_text())['tasks']}
for t in cat['tasks']:
 if t['id'] not in ids:assert t==previous[t['id']]
files=[p/'audit/tasks.json',p/'audit/runtime.json',r/'runtime/runtime.json',r/'runtime/manifest.json',r/'runtime/scheduler.json',link_path]
for i,value in enumerate([cat,runtime,runtime,manifest,scheduler,link]):write(c/f'config-{i}.json',value)
sys.path.insert(0,str(p/'code/explore'))
from bf.cost_scheduler import Scheduler
state=Scheduler(scheduler['database'],scheduler['tasks'],**scheduler['limits'])
receipt.update(status='staged',files=[str(f) for f in files],tasks=sorted(set(receipt['tasks'])|ids),description='Complete Medieval release; repair Concourse, grass starts, lower stairs; add S22 unaccepted draft',candidate_sha256={str(i):sha(c/f'config-{i}.json') for i in range(len(files))});receipt['expected_live_sha256'][str(link_path)]=sha(link_path);write(c/'completion.json',receipt)
print('Ready: 154 original Unreal entries plus S22 draft; 8 Concourse entries verified')
d=sqlite3.connect('file:'+str(p/'audit/review.sqlite3')+'?mode=ro',uri=True);print('Active Review:',d.execute("select task_id,status from sessions where status in ('queued','starting','ready')").fetchall())
