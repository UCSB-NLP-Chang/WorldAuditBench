from pathlib import Path
import json,subprocess,sqlite3,sys,hashlib,importlib.util
root=Path('/home/ubuntu/unreal-auditor');w=root/'indoor-cabinet-range-workspace';out=w/'out'
read=lambda p:json.loads(p.read_text())
proof=read(out/'proof.json');stage=Path(proof['stage']);sys.path.insert(0,str(stage))
with (out/'service-tests.log').open('w') as f:subprocess.run(['python3','-m','unittest','discover','-s','tests','-q'],cwd=stage,stdout=f,stderr=subprocess.STDOUT,check=True)
from server import Store
old=read(root/'review-service/state/tasks.json');new=read(stage/'tasks.json');oldby={t['id']:t for t in old['tasks']};newby={t['id']:t for t in new['tasks']}
assert set(newby)==set(oldby)
for tid,t in oldby.items():
 if t.get('family')!='indoor':assert newby[tid]==t,tid
 else:
  for k,v in t.items():
   if k not in ('sha256','build_sha256','review_compatible_versions'):assert newby[tid].get(k)==v,(tid,k)
before_store=None;after_store=None
for name,manifest in [('before',old),('after',new)]:
 path=out/(name+'-verification.sqlite3')
 src=sqlite3.connect('file:'+str(root/'review-service/state/review.sqlite3')+'?mode=ro',uri=True)
 with sqlite3.connect(path) as dst:src.backup(dst)
 src.close();path.chmod(0o600)
 store=Store(path,manifest,mode='external',tokens={'qa':{'id':'qa','reviewer':'Technical QA'}},runner=['/usr/bin/true'],build_sha='f'*64)
 if name=='before':before_store=store
 else:after_store=store
owners={r[0] for r in before_store.db.execute('select distinct owner from sessions')}
for owner in owners:
 a=before_store.reviews({'owner':owner});b=after_store.reviews({'owner':owner})
 assert set(a) <= set(b),(owner,set(a)-set(b))
assert [tuple(r) for r in before_store.db.execute('select * from feedback order by rowid')]==[tuple(r) for r in after_store.db.execute('select * from feedback order by rowid')]
before_store.db.close();after_store.db.close()
spec=importlib.util.spec_from_file_location('sup',stage/'runtime/mac_supervisor.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);cfg=read(stage/'candidate-runtime.json');cfg.update(manifest=str(stage/'tasks.json'),state_dir=str(out/'runtime'));sup=mod.Supervisor(cfg);assert sup.capacity==3
hashes={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.json','.html','.css') and '__pycache__' not in p.parts}
report=dict(result='PASS',entries=len(newby),reviewers_checked=len(owners),unchanged_reviews_retained=True,feedback_unmodified=True,capacity=3,candidate_hashes=hashes)
(out/'validation.json').write_text(json.dumps(report,indent=2));print({k:v for k,v in report.items() if k!='candidate_hashes'})

