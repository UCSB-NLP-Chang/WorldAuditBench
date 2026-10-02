"""Compare current review results using isolated copies of the live database."""
from pathlib import Path
import hashlib,json,sqlite3,subprocess,sys
from revise import manifest,MATERIAL_IDS
work=Path('/home/ubuntu/unreal-auditor/material-progress-workspace');state=work.parent/'review-service/state'
proof=json.loads((work/'proof.json').read_text());stage=Path(proof['stage'])
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((state/'tasks.json').read_text());new=json.loads((stage/'tasks.json').read_text())
assert new==manifest(old)
for before,after in zip(old['tasks'],new['tasks']):
 for k in ['id','revision','sha256','build_sha256','map','review_compatible_versions','runtime_switch']:
  assert before.get(k)==after.get(k),(before['id'],k)
 if before['id'] not in MATERIAL_IDS:assert before==after

code=r'''
import hashlib,json,sqlite3,sys
from pathlib import Path
release,dbpath,state,out=sys.argv[1:];sys.path.insert(0,release)
from server import Store
env=json.loads((Path(state)/'service-env.json').read_text())
items=json.loads((Path(release)/'tasks.json').read_text())
s=Store(dbpath,items,mode='external',tokens={'isolated-test':{'id':'isolated','reviewer':'Isolated'}},runner=['/bin/false'],build_sha=env['REVIEW_BUILD_SHA256'])
users={r['owner']:r['reviewer'] for r in s.db.execute('SELECT owner,reviewer FROM logins')}
for r in s.db.execute('SELECT owner,payload FROM feedback'):users[r['owner']]=json.loads(r['payload']).get('reviewer','Reviewer')
result={}
for owner,name in users.items():
 user={'owner':owner,'reviewer':name};d=s.dashboard(user)
 result[owner]=[{k:t[k] for k in ['id','approvals','reviewers','reviews','total_reviews','accepted','my_quality']} for t in d['tasks']]
 if 'reviewer_options' in d:
  key=hashlib.sha256(('progress-reviewer:'+owner).encode()).hexdigest()
  for t in d['tasks']:
   quality=next((r['quality'] for r in t['reviewer_results'] if r['id']==key),None)
   assert quality==t['my_quality']
Path(out).write_text(json.dumps(result,sort_keys=True));Path(out).chmod(0o600)
s.db.close()
'''
for label,release in [('before',Path(proof['source_release'])),('after',stage)]:
 dbpath=work/(label+'.sqlite3');dbpath.unlink(missing_ok=True)
 with sqlite3.connect('file:'+str(state/'review.sqlite3')+'?mode=ro',uri=True) as src,sqlite3.connect(dbpath) as dst:src.backup(dst)
 dbpath.chmod(0o600)
 subprocess.run([sys.executable,'-c',code,str(release),str(dbpath),str(state),str(work/(label+'-reviews.json'))],check=True)
a=json.loads((work/'before-reviews.json').read_text());b=json.loads((work/'after-reviews.json').read_text());assert a==b,'Existing review applicability changed'
report={'result':'PASS','entries':len(new['tasks']),'reviewers_compared':len(a),'material_tasks':sorted(MATERIAL_IDS),'runtime_identities_preserved':True,'review_results_preserved':True,'candidate_hashes':{str(p.relative_to(stage)):digest(p) for p in stage.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='candidate-runtime.json'}}
(work/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='candidate_hashes'}))
