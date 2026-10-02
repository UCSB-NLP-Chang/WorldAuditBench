"""Publish the independently verified UI ordering without changing any cases/builds."""
import json,shutil,subprocess,sys
from pathlib import Path
from prepare_review import digest
from patch_bug_type_order import patch

work=Path('/home/ubuntu/unreal-auditor/medieval-workspace')
root=work.parent/'review-service';state=root/'state'
name='bug-type-order-20260912-v1'
source=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip())
stage=root/'staging'/name
node=root/'deps/node-v22.23.2-linux-x64/bin/node'
if stage.exists():
    assert '--resume' in sys.argv
    assert '\nOK\n' in (stage/'ordering-tests.log').read_text()
    subprocess.run([str(node),str(Path(__file__).with_name('test_bug_type_order.cjs')),str(stage)],check=True)
    proof=json.loads((stage/'medieval-provenance.json').read_text())
    (stage/'medieval-validation.json').write_text(json.dumps(dict(result='PASS',scope='UI ordering',tasks_and_profiles_unchanged=True,browser=proof['acceptance']['browser']),indent=2))
    import publish_review
    publish_review.RELEASE_NAME=name;publish_review.STAGE=stage;publish_review.RELEASE=root/'releases'/name
    publish_review.main()
    raise SystemExit(0)
browser_proof=json.loads((work/'out/props-v2/browser-order-report.json').read_text());assert browser_proof['result']=='PASS'
shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','prepared-state'));stage.chmod(0o700)
patch(stage)
shutil.copy2(state/'tasks.json',stage/'tasks.json');shutil.copy2(state/'runtime.json',stage/'candidate-runtime.json');(stage/'candidate-runtime.json').chmod(0o600)
manifest=json.loads((state/'tasks.json').read_text());binary_sha=next(t['build_sha256'] for t in manifest['tasks'] if t['id']=='MVB01')
proof=dict(source_release=str(source),source_files_sha256={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css') and '__pycache__' not in p.parts},
           source_state_sha256={n:digest(state/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},binary_sha256=binary_sha,
           acceptance=dict(result='PASS',scope='UI ordering only; all native packages and task metadata unchanged',browser=browser_proof))
assert digest(stage/'tasks.json')==digest(state/'tasks.json')
assert digest(stage/'candidate-runtime.json')==digest(state/'runtime.json')
(stage/'medieval-provenance.json').write_text(json.dumps(proof,indent=2))
with (stage/'ordering-tests.log').open('w') as log:
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=stage,stdout=log,stderr=subprocess.STDOUT,check=True)
subprocess.run([str(node),str(Path(__file__).with_name('test_bug_type_order.cjs')),str(stage)],check=True)
(stage/'medieval-validation.json').write_text(json.dumps(dict(result='PASS',scope='UI ordering',tasks_and_profiles_unchanged=True,browser=browser_proof),indent=2))
import publish_review
publish_review.RELEASE_NAME=name
publish_review.STAGE=stage
publish_review.RELEASE=root/'releases'/name
publish_review.main()
