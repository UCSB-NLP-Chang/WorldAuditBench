from pathlib import Path
import hashlib,json,shutil,subprocess
from revise import patch
root=Path('/home/ubuntu/unreal-auditor');work=root/'material-progress-workspace';state=root/'review-service/state'
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip())
stage=work/'material-progress-20260913-v1'
assert not stage.exists()
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copy2(state/'tasks.json',stage/'tasks.json')
proof={'source_release':str(source),'stage':str(stage),'source_state_sha256':{n:digest(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},'source_files':{n:digest(source/n) for n in ['server.py','taxonomy.py','taxonomy.json','tasks.json','static/app.js','static/index.html']}}
patch(stage)
shutil.copy2(state/'runtime.json',stage/'candidate-runtime.json')
(stage/'candidate-runtime.json').chmod(0o600)
shutil.copy2(Path(__file__).with_name('test_material_progress.py'),stage/'tests/test_material_progress.py')
(work/'proof.json').write_text(json.dumps(proof,indent=2))
print('Prepared',stage)
