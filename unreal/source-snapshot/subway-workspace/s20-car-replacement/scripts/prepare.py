from pathlib import Path
import json,copy,shutil,hashlib,subprocess,importlib.util
r=Path('/home/ubuntu/unreal-auditor');w=r/'subway-workspace/s20-car-replacement';state=r/'review-service/state'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=w/'subway-s20-coupe-20260913-v1';assert not stage.exists()
proof=dict(source_release=str(source),stage=str(stage),state_hashes={n:sha(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},source_hashes={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__'));stage.chmod(0o700)
m=read(state/'tasks.json');old=copy.deepcopy(m);runtime=read(state/'runtime.json');b=read(w/'out/build.json');assert sha(Path(b['binary']))==b['binary_sha256']
for t in m['tasks']:
 if t.get('family')!='subway':continue
 if t['id']=='S20':t.pop('review_compatible_versions',None)
 else:
  previous={k:t[k] for k in ('revision','sha256','build_sha256')};versions=t.setdefault('review_compatible_versions',[])
  if previous not in versions:versions.append(previous)
 t['revision']+=1;t['build_sha256']=b['binary_sha256'];t['sha256']=sha(r/'projects/Subway/Content'/(t['map'].split('?')[0][6:]+'.umap'));runtime['launch_profiles'][t['map']].update(binary=b['binary'],build_sha256=b['binary_sha256'])
assert [t for t in m['tasks'] if t.get('family')!='subway']==[t for t in old['tasks'] if t.get('family')!='subway']
assert 'prop credits' not in (stage/'static/index.html').read_text()
write(stage/'tasks.json',m);write(stage/'candidate-runtime.json',runtime);(stage/'candidate-runtime.json').chmod(0o600)
spec=importlib.util.spec_from_file_location('candidate_supervisor',stage/'runtime/mac_supervisor.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);c=copy.deepcopy(runtime);c.update(manifest=str(stage/'tasks.json'),state_dir=str(w/'out/runtime-validation'));sup=module.Supervisor(c);assert sup.capacity==3
write(w/'out/runtime-validation.json',dict(status='PASS',profiles=len(sup.allowed),capacity=sup.capacity));proof['entries']=len(m['tasks']);write(w/'out/review-proof.json',proof)
with (w/'out/service-tests.log').open('w') as f:subprocess.run(['python3','-m','unittest','discover','-s','tests','-q'],cwd=stage,stdout=f,stderr=subprocess.STDOUT,check=True)
print('CANDIDATE_PASS',len(m['tasks']),flush=True)
