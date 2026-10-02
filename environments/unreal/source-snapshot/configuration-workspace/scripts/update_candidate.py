from pathlib import Path
import json,shutil,hashlib,importlib.util,copy
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');old=w/'configuration-tasks-20260913-v1';stage=w/'configuration-tasks-20260913-v2';assert not stage.exists();shutil.copytree(old,stage,ignore=shutil.ignore_patterns('__pycache__'))
def read(p):return json.loads(p.read_text())
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(stage/'tasks.json');runtime=read(stage/'candidate-runtime.json');build=read(w/'out/build-ancient.json');root=Path('/home/ubuntu/unreal-auditor/ancient-workspace');recipes={t['id']:t for t in read(root/'environments/ancient-chinese-city/tasks.json')['tasks']}
for t in manifest['tasks']:
 if t.get('family')!='ancient':continue
 t['sha256']=sha(root/'project/Content'/(t['map'].split('?')[0][6:]+'.umap'));t['build_sha256']=build['binary_sha256'];runtime['launch_profiles'][t['map']].update(binary=build['binary'],build_sha256=build['binary_sha256'])
 if t['id'] in ['A21','A24']:
  recipe=recipes[t['id']];t.update(title=recipe['title'],rubrics_i18n=recipe['rubrics_i18n'],rubrics=recipe['rubrics_i18n']['en']['criteria']+'\n'+recipe['rubrics_i18n']['zh']['criteria']);assert t['revision']==2
runtime['launch_profiles']={t['map']:runtime['launch_profiles'][t['map']] for t in manifest['tasks'] if t.get('runtime_kind')!='browser'}
write(stage/'tasks.json',manifest);write(stage/'candidate-runtime.json',runtime);(stage/'candidate-runtime.json').chmod(0o600)
spec=importlib.util.spec_from_file_location('candidate_supervisor',stage/'runtime/mac_supervisor.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);c=copy.deepcopy(runtime);c.update(manifest=str(stage/'tasks.json'),state_dir=str(w/'out/runtime-validation'));supervisor=module.Supervisor(c);assert len(supervisor.allowed)==148
proof=read(w/'out/review-proof.json');proof.update(stage=str(stage));proof['builds']['ancient']=build;proof['additional_changed']=['A21','A24'];write(w/'out/review-proof.json',proof);write(w/'out/runtime-validation.json',dict(status='PASS',profiles=len(supervisor.allowed),capacity=supervisor.capacity));print('Candidate v2: reconciled runtime and revised A21')
