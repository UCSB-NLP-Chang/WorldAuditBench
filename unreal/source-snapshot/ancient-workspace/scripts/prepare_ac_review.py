"""Rebase the A24 household condenser revision on the current live review release."""
import ast,copy,json,re,shutil,subprocess
from pathlib import Path
import hashlib
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 w=Path('/home/ubuntu/unreal-auditor/ancient-workspace');svc=w.parent/'review-service';state=svc/'state';env=w/'environments/ancient-chinese-city'
 proof=json.loads((w/'out/ac-v2/acceptance.json').read_text());assert proof['result']=='PASS';binary=Path(proof['binary']);assert digest(binary)==proof['binary_sha256']
 source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());stage=svc/'staging'/proof['release_name'];assert not stage.exists()
 shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','prepared-state'));stage.chmod(0o700)
 manifest=json.loads((state/'tasks.json').read_text());config=json.loads((state/'runtime.json').read_text());before=copy.deepcopy(manifest)
 ours={t['id']:t for t in manifest['tasks'] if t.get('family')=='ancient'};assert len(ours)==27 and ours['A24']['revision']==1
 authored={t['id']:t for t in json.loads((env/'tasks.json').read_text())['tasks']};assert len(authored)==24
 regs={g['id']:g for g in json.loads((env/'regions.json').read_text())['regions']};template=copy.deepcopy(ours['A20']);profile_template=copy.deepcopy(config['launch_profiles'][template['map']])
 t=authored['A24'];e=ours['A24'];e.update(revision=e['revision']+1,title=t['title'],rubrics_i18n=t['rubrics_i18n'],rubrics='\n'.join(' '.join(t['rubrics_i18n'][l][k] for k in ['criteria','expected']) for l in ['en','zh']))
 for e in ours.values():
  e['build_sha256']=proof['binary_sha256'];e['sha256']=digest(w/'project/Content'/(e['map'].split('?')[0][6:]+'.umap'))
  p=copy.deepcopy(config['launch_profiles'].get(e['map'],profile_template));p.update(binary=str(binary),build_sha256=proof['binary_sha256'],game_args=proof['game_args']);config['launch_profiles'][e['map']]=p
 (stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));(stage/'candidate-runtime.json').write_text(json.dumps(config,indent=2));(stage/'candidate-runtime.json').chmod(0o600)
 provenance=dict(source_release=str(source),source_files_sha256={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css') and '__pycache__' not in p.parts},source_state_sha256={n:digest(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},binary_sha256=proof['binary_sha256'],previous_entries=len(before['tasks']),added_entries=0,changed_cases=["A24"],acceptance=proof)
 (stage/'ancient-provenance.json').write_text(json.dumps(provenance,indent=2));print(stage,flush=True)
if __name__=='__main__':main()
