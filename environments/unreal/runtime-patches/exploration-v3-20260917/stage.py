"""Stage a policy-only Review release; preserve other websites and map assets."""
import copy,hashlib,json,pathlib,sys,shutil,time
work=pathlib.Path(sys.argv[1]);release=pathlib.Path(sys.argv[2]);prod=pathlib.Path('/home/ec2-user/unreal-production');base=pathlib.Path('/home/ec2-user/unreal-review-releases/exploration-v2-preview-20260917')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
qa=json.loads((work/'validation.json').read_text());policy=json.loads((work/'policy.json').read_text());assert qa['status']=='PASS' and len(qa['tasks'])==len(policy['tasks'])==155 and qa['policy_sha256']==sha(work/'policy.json')
release.mkdir(exist_ok=False);shutil.copy2(work/'policy.json',release/'policy.json');(release/'policy.json').chmod(0o600);shutil.copy2(work/'validation.json',release/'validation.json')
files=[prod/'audit/tasks.json',prod/'audit/runtime.json',base/'runtime/runtime.json',base/'runtime/manifest.json',base/'runtime/scheduler.json',prod/'shared/production-links/review-v2/review.json']
before=[json.loads(p.read_text()) for p in files];cat,ar,rt,manifest,sc,link=copy.deepcopy(before);assert ar==rt
snapshot=json.loads((work/'live-snapshot.json').read_text());assert cat['tasks']==snapshot['tasks'] and rt['launch_profiles']==snapshot['profiles'],'Live catalog/profile changed during preparation'
changed={}
for t in cat['tasks']:
 if t['id'] not in policy['tasks']:continue
 tid=t['id'];matches=[(k,v) for k,v in rt['launch_profiles'].items() if '-AuditorExplorationTask='+tid in v.get('extra_args',[])];assert len(matches)==1
 key,profile=matches[0];assert key.startswith('/Shared/review/')
 profile['extra_args']=[x for x in profile['extra_args'] if not x.startswith('-AuditorExplorationPolicy=')]+['-AuditorExplorationPolicy='+str(release/'policy.json')]
 old=copy.deepcopy(t.get('exploration_revision'));t['revision']+=1;t['exploration_revision']={'version':policy['version'],'policy_sha256':qa['policy_sha256'],'previous_policy_sha256':(old or {}).get('policy_sha256')};t.pop('review_compatible_versions',None);changed[key]=tid
 # Keep the real cooked-map checksum while giving the scheduler a distinct task identity.
 link['task_ids'][tid]['id']='review:'+tid+':'+t['sha256'][:12]+':'+qa['policy_sha256'][:12]
for t in sc['tasks']:
 if t.get('map') in changed:
  tid=changed[t['map']];t['id']=link['task_ids'][tid]['id'];t['group']=hashlib.sha256((rt['launch_profiles'][t['map']]['binary']+qa['policy_sha256']).encode()).hexdigest()
sc['clients']['review']['tasks']=[t['id'] for t in sc['tasks']];sc['database']=str(base/'runtime/pool-exploration-v3-20260917.sqlite3');assert not pathlib.Path(sc['database']).exists()
# Preserve browser entries, every cooked asset and executable, and all unrelated profiles.
for old,new in zip(before[0]['tasks'],cat['tasks']):
 if old['id'] not in policy['tasks']:assert old==new
 else:
  for key in ['map','sha256','build_sha256','rubrics','rubrics_i18n']:assert old.get(key)==new.get(key),(old['id'],key)
for key,old in before[2]['launch_profiles'].items():
 if key not in changed:assert rt['launch_profiles'][key]==old
assert manifest==before[3]
protected=['shared/runtime-prod.json','shared/manifest.json','shared/scheduler-prod.json','shared/exploration-prod.json','config/evaluation.json','shared/production-links/explore.json','shared/production-links/review.json']
protected_hashes={n:sha(prod/n) for n in protected if (prod/n).exists()}
write(release/'release.json',{'pool_service':'aws-unreal-review-pool-v2.service','protected_sha256':protected_hashes,'scope':'Review only'})
for i,value in enumerate([cat,rt,rt,manifest,sc,link]):write(release/f'config-{i}.json',value)
sys.path.insert(0,str(prod/'code/explore'));from bf.cost_scheduler import Scheduler
state=Scheduler(sc['database'],sc['tasks'],**sc['limits'])
write(release/'completion.json',{'status':'staged','files':[str(f) for f in files],'tasks':sorted(policy['tasks']),'policy_sha256':qa['policy_sha256'],'expected_live_sha256':{str(f):sha(f) for f in files},'candidate_sha256':{str(i):sha(release/f'config-{i}.json') for i in range(len(files))},'prepared_at':time.time()})
print('STAGED',len(changed),'Review policies. No live configuration replaced.')
