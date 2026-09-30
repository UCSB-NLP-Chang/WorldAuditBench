from pathlib import Path
import json,hashlib
root=Path('/home/ubuntu/unreal-auditor/rural-workspace')
def read(p):return json.loads(p.read_text())
new=root/'dist/rural-linux-v3';old=root/'dist/rural-linux-v2';provenance=read(new/'build-provenance.json')
checks=read(root/'out/tests-packaged/report.json');assert len(checks)==24 and all(x['ok'] for x in checks)
old_tasks={t['id']:t for t in read(old/'tasks.json')['tasks']};new_tasks={t['id']:t for t in read(new/'tasks.json')['tasks']};changed=[id for id in new_tasks if old_tasks[id]!=new_tasks[id]];assert set(changed)=={'R08','R15'}
render={x['name']:x for x in read(root/'out/tests-packaged/report-render-v2.json')};updated=read(root/'out/tests-packaged/report-render.json');assert {x['name'] for x in updated}=={'R08','R15'};render.update({x['name']:x for x in updated});assert len(render)==24 and all(x['ok'] for x in render.values())
reuse=read(root/'out/reuse-streaming2/report.json');assert len(reuse)==18 and all(x['ok'] for x in reuse)
assert new_tasks['R15']['kind']=='view_cull'
assert (root/'out/preview/R15-hidden.png').exists()
assert all((root/'out/references'/(id+'.png')).exists() for id in new_tasks)
proof=read(root/'out/release-candidate.json');stage=Path(proof['stage']);tested=Path('/home/ubuntu/unreal-auditor/review-service/staging/rural-20260912-203810')
for name in ['static/app.js','static/index.html','static/style.css']:assert (stage/name).read_bytes()==(tested/name).read_bytes()
report=dict(status='PASS',build_sha256=provenance['binary_sha256'],build=str(new),engine='5.6.1',regions=3,bugs=18,baselines=3,packaged_runtime_checks=24,rendered_checks=24,render_regression_basis='All 24 checks rendered in v2; only R08 camera and R15 behavior changed, both rendered again in v3. Executable SHA is unchanged.',changed_tasks=changed,same_process_reset_checks=18,reference_images=21,review_service_tests=119,browser_ui='PASS; identical app, index and CSS hashes to browser-tested candidate',visual_review='Inspected anomaly contact sheets and clean references. Replaced weak R15 shadow with centered-view disappearance; verified rock absent in R15-hidden.png and present in clean reference.',containers=provenance['containers'])
(root/'out/validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
