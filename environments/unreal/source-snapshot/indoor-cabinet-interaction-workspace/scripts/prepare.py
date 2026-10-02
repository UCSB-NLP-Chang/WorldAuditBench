from pathlib import Path
import json,hashlib,subprocess,shutil,copy
root=Path('/home/ubuntu/unreal-auditor');w=root/'indoor-cabinet-interaction-workspace';out=w/'out';out.mkdir(parents=True,exist_ok=True);svc=root/'review-service';state=svc/'state';indoor=root/'indoor-workspace'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=w/'indoor-cabinet-interaction-20260913-v1';assert not stage.exists()
source_hashes={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css') and '__pycache__' not in p.parts}
state_hashes={n:sha(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']}
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','prepared-state'));stage.chmod(0o700)
manifest=read(state/'tasks.json');before=copy.deepcopy(manifest);runtime=read(state/'runtime.json')
binary=indoor/'dist/indoor-cabinet-interaction-20260913-v1/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou';bh=sha(binary)
ours=[e for e in manifest['tasks'] if e.get('family')=='indoor'];assert len(ours)==17
for e in ours:
 old={k:e[k] for k in ['revision','sha256','build_sha256']};aliases=e.setdefault('review_compatible_versions',[])
 if old not in aliases:aliases.append(old)
 e['build_sha256']=bh;e['sha256']=sha(indoor/'project/Content'/(e['map'].split('?')[0][6:]+'.umap'))
 profile=runtime['launch_profiles'][e['map']];profile.update(binary=str(binary),build_sha256=bh)
 assert '-sm5' in profile['game_args'] and '-sm6' not in profile['game_args']
(stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(stage/'candidate-runtime.json').write_text(json.dumps(runtime,indent=2));(stage/'candidate-runtime.json').chmod(0o600)
for n,h in source_hashes.items():assert sha(source/n)==h,n
for n,h in state_hashes.items():assert sha(state/n)==h,n
proof=dict(source_release=str(source),stage=str(stage),entries=len(manifest['tasks']),changed_cases=[],added_cases=[],state_hashes=state_hashes,source_hashes=source_hashes,binary_sha256=bh)
(out/'proof.json').write_text(json.dumps(proof,indent=2));print(stage,flush=True)

