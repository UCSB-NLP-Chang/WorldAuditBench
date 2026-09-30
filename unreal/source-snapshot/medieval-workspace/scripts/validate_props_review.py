"""Verify revision scope, all catalog regressions and global task ordering."""
from pathlib import Path
import json,subprocess,sys

stage=Path(sys.argv[1]);state=Path('/home/ubuntu/unreal-auditor/review-service/state')
new=json.loads((stage/'tasks.json').read_text());old=json.loads((state/'tasks.json').read_text())
cfg=json.loads((stage/'candidate-runtime.json').read_text());oldcfg=json.loads((state/'runtime.json').read_text())
assert [t for t in new['tasks'] if t.get('family')!='medieval']==[t for t in old['tasks'] if t.get('family')!='medieval']
assert {k:v for k,v in cfg.items() if k!='launch_profiles'}=={k:v for k,v in oldcfg.items() if k!='launch_profiles'}
assert all(cfg['launch_profiles'][k]==v for k,v in oldcfg['launch_profiles'].items() if v.get('family')!='medieval')
ours={t['id']:t for t in new['tasks'] if t.get('family')=='medieval'}
assert set(ours)=={'MVB01','MVB02'}|{f'MV{i:02}' for i in range(1,21)}
for before in old['tasks']:
    if before.get('family')!='medieval' or before['id']=='MV18':continue
    after=ours[before['id']]
    assert {k:v for k,v in before.items() if k not in ('sha256','build_sha256')}=={k:v for k,v in after.items() if k not in ('sha256','build_sha256')},before['id']
before=next(t for t in old['tasks'] if t['id']=='MV18')
assert ours['MV18']['revision']==before['revision']+1
assert 'vending' not in json.dumps(ours['MV18']).lower()
for id in ('MV18','MV19','MV20'):
    assert ours[id]['subcategory']=='S3'
    for lang in ('en','zh'):
        assert all(ours[id]['rubrics_i18n'][lang][k].strip() for k in ('criteria','expected','steps'))
subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=stage,check=True)
subprocess.run(['/home/ubuntu/unreal-auditor/review-service/deps/node-v22.23.2-linux-x64/bin/node',str(Path(__file__).with_name('test_bug_type_order.cjs')),str(stage)],check=True)
report=dict(result='PASS',bugs=20,baselines=2,changed_cases=['MV18'],added_cases=['MV19','MV20'],all_other_case_metadata_preserved=True,other_runtime_profiles_preserved=True,bug_type_sorting=True)
(stage/'medieval-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
