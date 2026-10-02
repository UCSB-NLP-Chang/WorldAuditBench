from pathlib import Path
import json,hashlib,copy,sqlite3,sys,subprocess,shutil
c=Path(__file__).parent;p=Path('/home/ec2-user/unreal-production');r=Path('/home/ec2-user/unreal-review-releases/exploration-v2-preview-20260917');pol=json.loads((c/'policy.json').read_text());ids=set(json.loads((c/'affected.json').read_text()))
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def save(f,v):f.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');f.chmod(0o600)
for tid in ids:
 result=json.loads((c/'task-route-qa'/tid/'result.json').read_text());assert result['status']=='PASS',(tid,result)
if (c/'navigation-qa.json').exists():assert json.loads((c/'navigation-qa.json').read_text())['status']=='PASS'
files=[p/'audit/tasks.json',p/'audit/runtime.json',r/'runtime/runtime.json',r/'runtime/manifest.json',r/'runtime/scheduler.json',p/'shared/production-links/review-v2/review.json'];old=[json.loads(f.read_text()) for f in files];cat,rt,rtpool,manifest,sched,link=copy.deepcopy(old);assert rt==rtpool
snapshot=json.loads((c/'live-profiles.json').read_text())
for task in cat['tasks']:
 if task['id'] in ids:
  assert task==snapshot[task['id']]['task'],'Task changed after verification: '+task['id']
  prof=next(v for v in rt['launch_profiles'].values() if v.get('runtime_map')==task['map'])
  assert prof==snapshot[task['id']]['profile'],'Launch profile changed after verification: '+task['id']
policysha=sha(c/'policy.json');changed={}
assert json.loads((c/'qa-provenance.json').read_text())['policy_sha256']==policysha
assert json.loads((c/'original-bound-verification.json').read_text())=={'checked':143,'missing':[]}
assert json.loads((c/'qa-package-content-sha256.json').read_text())==json.loads((c/'production-package-content-sha256.json').read_text())
newbinary=c/'package/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou';newhash=sha(newbinary)
assert newhash=='09fa7b331005394cd71d087bf4c8374781c1c067ddea5ed4de052d11077dbf9b'
for tid in ['HB01','HB02','HB03','B01']:
 assert json.loads((c/'containment-qa'/tid/'result.json').read_text())['status']=='PASS',tid
for tid,e in pol['tasks'].items():
 import math
 oldarea=math.prod(e['old_bounds_max'][j]-e['old_bounds_min'][j] for j in (0,1))
 newarea=math.prod(e['bounds_max'][j]-e['bounds_min'][j] for j in (0,1))
 assert abs(newarea/oldarea-3)<1e-8,tid
 assert e['bounds_min'][2]==e['old_bounds_min'][2] and e['bounds_max'][2]==e['old_bounds_max'][2],tid
 report=json.loads((c/'task-route-qa'/tid/'validation.json').read_text())
 for k in ['spawn','bounds_min','bounds_max']:
  assert all(abs(a-b)<.01 for a,b in zip(report[k],e[k])),(tid,k)
 
for t in cat['tasks']:
 if t['id'] not in ids:continue
 prev={k:t[k] for k in ['revision','sha256','build_sha256']};aliases=t.setdefault('review_compatible_versions',[])
 if prev not in aliases:aliases.append(prev)
 if t['family']=='indoor':t['build_sha256']=newhash
 t['revision']+=1;t['exploration_revision']={'version':c.name,'policy_sha256':policysha,'previous_policy_sha256':t['exploration_revision']['policy_sha256']}
 key=next(k for k,v in rt['launch_profiles'].items() if v.get('runtime_map')==t['map']);profile=rt['launch_profiles'][key]
 if t['family']=='indoor':profile.update(binary=str(newbinary),build_sha256=newhash)
 profile['extra_args']=[('-AuditorExplorationPolicy='+str(c/'policy.json')) if a.startswith('-AuditorExplorationPolicy=') else a for a in profile['extra_args']]
 new_id='review:'+t['id']+':'+t['sha256'][:12]+':'+policysha[:12];link['task_ids'][t['id']]={'id':new_id,'sha256':t['sha256']};changed[key]=(t['id'],new_id)
for t in manifest['tasks']:
 if t['map'] in changed:t['build_sha256']=rt['launch_profiles'][t['map']]['build_sha256']
for t in sched['tasks']:
 if t['map'] in changed:
  tid,newid=changed[t['map']];t['id']=newid;t['group']=hashlib.sha256((rt['launch_profiles'][t['map']]['binary']+str(c/'policy.json')).encode()).hexdigest()
sched['clients']['review']['tasks']=[t['id'] for t in sched['tasks']]
assert [t for t in cat['tasks'] if t['id'] not in ids]==[t for t in old[0]['tasks'] if t['id'] not in ids]
assert all(v==old[1]['launch_profiles'][k] for k,v in rt['launch_profiles'].items() if k not in changed)
# Build an explicit idle scheduler migration, preserving all history.
with sqlite3.connect('file:'+str(p/'audit/review.sqlite3')+'?mode=ro',uri=True) as d:
 assert d.execute("select count(*) from sessions where status in ('queued','starting','ready','resetting','switching','closing')").fetchone()[0]==0,'Review in use'
 feedback=hashlib.sha256(json.dumps(d.execute('select id,session_id,owner,created,payload from feedback order by id').fetchall(),ensure_ascii=False).encode()).hexdigest()
(c/'feedback-before.sha256').write_text(feedback)
source=sqlite3.connect('file:'+sched['database']+'?mode=ro',uri=True)
for table,where in [('leases',"state!='ended'"),('requests',"state='waiting'"),('slots',"state!='free'")]:assert source.execute('select count(*) from '+table+' where '+where).fetchone()[0]==0,'Scheduler not idle'
newdb=r/'runtime'/('pool-'+c.name+'.sqlite3');assert not newdb.exists(),'Migration already exists'
target=sqlite3.connect(newdb);source.backup(target);source.close();digest=hashlib.sha256(json.dumps({t['id']:dict(t) for t in sched['tasks']},sort_keys=True).encode()).hexdigest();target.execute("update metadata set value=? where key='catalog'",(digest,));target.commit();target.close();sched['database']=str(newdb)
for i,v in enumerate([cat,rt,rt,manifest,sched,link]):save(c/f'config-{i}.json',v)
sys.path.insert(0,str(p/'code/explore'));from bf.cost_scheduler import Scheduler
s=Scheduler(sched['database'],sched['tasks'],**sched['limits']);s.close()
receipt={'status':'staged','files':list(map(str,files)),'tasks':sorted(ids),'policy_sha256':policysha,'expected_live_sha256':{str(f):sha(f) for f in files},'candidate_sha256':{str(i):sha(c/f'config-{i}.json') for i in range(6)}};save(c/'completion.json',receipt)
shutil.copy2(c.parent/'indoor-h01-boundary-20260918/activate_staged.py',c/'activate_staged.py')
print('STAGED',len(ids),'tasks with native routes verified; feedback and unrelated tasks retained')
