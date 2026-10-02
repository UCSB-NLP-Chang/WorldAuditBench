"""Export current authored Lambda source without assets, state or credentials."""
from pathlib import Path
import argparse,collections,datetime,hashlib,json,re,shutil,subprocess,tarfile
p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);args=p.parse_args()
root=Path('/home/ubuntu/unreal-auditor');out=args.output.resolve();assert not out.exists();out.mkdir(parents=True,mode=0o700)
release=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());state=root/'review-service/state'
allowed={'.py','.cpp','.h','.inl','.cs','.uproject','.uplugin','.ini','.json','.md','.txt','.sh','.js','.cjs','.html','.css','.service','.conf','.yaml','.yml','.toml','.patch','.bat'}
blocked={'__pycache__','out','backup','backups','Content','Binaries','Intermediate','DerivedDataCache','Saved','node_modules','.git','state','sessions','evidence'}
files=[]
def add(src,dest=None):
 if not src.is_file() or src.is_symlink() or src.suffix not in allowed or src.stat().st_size>5*1024**2:return
 if any(x in blocked for x in src.relative_to(root).parts) and not (src.parent==state and src.name in {'tasks.json','taxonomy.json','rubrics.bilingual.json','review-scene-descriptions.json','urban-public-ids.json','scene-context-provenance.json'}):return
 if any(x in src.name.lower() for x in ['.before','source-before','cookie.json','service-env.json','participants.json','runtime.json']):return
 dest=out/(dest or src.relative_to(root));dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest);files.append((src,dest))
def tree(src,dest=None):
 if not src.exists():return
 for f in sorted(src.rglob('*')):add(f,(Path(dest)/f.relative_to(src)) if dest else None)
projects={
 'ancient':'ancient-workspace/project','indoor':'indoor-workspace/project','industrial':'industrial-workspace/project','medieval':'medieval-workspace/project','rural':'rural-workspace/project','subway':'projects/Subway','urban':'builds/core18-ue561-20260911'}
for family,rel in projects.items():
 project=root/rel
 for name in ['Source','Config','Plugins/AuditorRuntime']:tree(project/name)
 for f in project.glob('*.uproject'):add(f)
 if family!='urban':
  ws=root/('subway-workspace' if family=='subway' else rel.split('/')[0])
  for name in ['scripts','environments']:tree(ws/name)
  for f in ws.glob('*.md'):add(f)
 else:
  for f in project.iterdir():
   if f.suffix in ['.py','.md']:add(f)
  tree(project/'baselines')
# Recipe workspaces hold authored revisions used by the currently deployed binaries.
for rel in ['configuration-workspace','operational-workspace','indoor-cabinet-range-workspace','indoor-cabinet-interaction-workspace','indoor-h09-cabinet-workspace','indoor-h10-start-workspace','indoor-door-workspace','indoor-h03-pot-workspace','material-progress-workspace','review-continuity-workspace','review-save-confirmation','review-save-on-navigation','subway-workspace/s20','subway-workspace/s20-car-replacement']:
 ws=root/rel
 tree(ws/'scripts')
 for f in ws.glob('*.md'):add(f)
 for f in ws.glob('*.py'):add(f)
 for f in ws.glob('projects.json'):add(f)
# Common older authoring/API tools are dependencies of current build scripts.
for name in ['auditor','scripts','tests','docs','environments']:tree(root/'repository'/name)
# Capture the entire live review source and test suite, omitting historical reports.
for f in release.iterdir():
 if f.suffix=='.py':add(f,Path('review-service/current')/f.name)
for name in ['static','runtime','tests','deploy']:tree(release/name,Path('review-service/current')/name)
for name in ['tasks.json','taxonomy.json','rubrics.bilingual.json','review-scene-descriptions.json','urban-public-ids.json','scene-context-provenance.json','configuration-backup-cases.json','industrial-runtime-profiles.json']:
 src=state/name if (state/name).exists() else release/name
 add(src,Path('review-service/current')/name)
for f in release.glob('*scene-descriptions.json'):add(f,Path('review-service/current')/f.name)
# The Three.js HTML files embed large assets; track serving code and file receipts.
th=root/'threejs/releases/envs-2026-09-12'
for f in th.iterdir():
 if f.suffix in ['.py','.service']:add(f)
for f in (th/'site').glob('index.html'):add(f)
for f in (th/'site').glob('bugs.html'):add(f)
artifacts=[]
for f in (th/'site').glob('*.html'):
 if f.name not in ['index.html','bugs.html']:artifacts.append({'path':str(f.relative_to(root)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
# Known live secrets are read only in memory to prevent accidental inclusion.
runtime=json.loads((state/'runtime.json').read_text());env=json.loads((state/'service-env.json').read_text());participants=json.loads((state/'participants.json').read_text());secrets=set()
def collect(value,key=''):
 if isinstance(value,dict):
  for k,v in value.items():collect(v,str(k))
 elif isinstance(value,list):
  for v in value:collect(v,key)
 elif isinstance(value,str):
  if re.search('secret|password|credential|access.?code|admin.?token|group.?code',key,re.I) and len(value)>=4:secrets.add(value)
  try:
   data=json.loads(value)
   if isinstance(data,(dict,list)):
    if key=='REVIEW_TOKENS_JSON':secrets.update(x for x in data if len(x)>=8)
    collect(data,key)
  except (ValueError,TypeError):pass
collect(runtime);collect(env);collect(participants)
# TURN user arguments may contain user:password without a named credential key.
for arg in runtime.get('turn_argv',[]):
 if isinstance(arg,str) and arg.startswith(('--user=','-u=')):
  credential=arg.split('=',1)[1].split(':',1)
  if len(credential)==2:secrets.add(credential[1])
def redact(value):
 if isinstance(value,dict):return {k:('REPLACE_AT_DEPLOY_TIME' if re.search('secret|password|credential|token',k,re.I) else redact(v)) for k,v in value.items()}
 if isinstance(value,list):return [redact(v) for v in value]
 if isinstance(value,str):
  for secret in sorted(secrets,key=len,reverse=True):value=value.replace(secret,'REPLACE_AT_DEPLOY_TIME')
 return value
example=redact(runtime);ep=out/'review-service/current/runtime.example.json';ep.write_text(json.dumps(example,indent=2))
# Existing catalog tests expect this optional file; it is the same redacted fixture.
(out/'review-service/current/candidate-runtime.json').write_text(json.dumps(example,indent=2))
# Source map and runtime lock deliberately contain no review records or identities.
manifest=json.loads((state/'tasks.json').read_text());lock={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'live_release':str(release),'task_count':len(manifest['tasks']),'families':dict(collections.Counter(t['family'] for t in manifest['tasks'])),'projects':projects,'artifact_status':'HF upload pending; no binary or editor content included','threejs_artifacts':artifacts,'launch_profiles':{k:{x:v[x] for x in ['binary','build_sha256','game_args'] if x in v} for k,v in runtime['launch_profiles'].items()},'manifest_sha256':hashlib.sha256((state/'tasks.json').read_bytes()).hexdigest(),'source_files':[{'path':str(dst.relative_to(out)),'source_path':str(src),'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()} for src,dst in files]}
(out/'snapshot.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2))
assert (out/'review-service/current/tasks.json').is_file(), 'Current task manifest missing'
(out/'tools').mkdir(exist_ok=True)
shutil.copy2(Path(__file__),out/'tools/export_sources.py')
# Abort with paths only; never print credential values or matched lines.
hits=[]
for f in out.rglob('*'):
 if not f.is_file():continue
 data=f.read_text(errors='replace')
 for secret in secrets:
  if (len(secret)>=8 and secret in data) or ('"'+secret+'"') in data or ("'"+secret+"'") in data:
   hits.append(str(f.relative_to(out)));break
 if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|hf_[A-Za-z0-9]{25,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)',data):hits.append(str(f.relative_to(out)))
if hits:raise RuntimeError('Sensitive content detected in: '+', '.join(sorted(set(hits))))
assert subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip()==str(release)
for src,dst in files:assert hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(dst.read_bytes()).digest(),str(src)
assert hashlib.sha256((state/'tasks.json').read_bytes()).hexdigest()==lock['manifest_sha256']
print(json.dumps({'result':'PASS','source_files':len(files),'total_bytes':sum(f.stat().st_size for f in out.rglob('*') if f.is_file()),'tasks':lock['task_count'],'live_release':str(release),'known_live_secrets_scan':'PASS','output':str(out)}))
