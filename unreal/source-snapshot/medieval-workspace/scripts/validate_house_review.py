"""Verify revision scope, all catalog regressions and global task ordering."""
from pathlib import Path
import json,re,subprocess,sys

stage=Path(sys.argv[1]);state=Path('/home/ubuntu/unreal-auditor/review-service/state')
new=json.loads((stage/'tasks.json').read_text());old=json.loads((state/'tasks.json').read_text())
cfg=json.loads((stage/'candidate-runtime.json').read_text());oldcfg=json.loads((state/'runtime.json').read_text())
assert [t for t in new['tasks'] if t.get('family')!='medieval']==[t for t in old['tasks'] if t.get('family')!='medieval']
assert {k:v for k,v in cfg.items() if k!='launch_profiles'}=={k:v for k,v in oldcfg.items() if k!='launch_profiles'}
assert all(cfg['launch_profiles'][k]==v for k,v in oldcfg['launch_profiles'].items() if v.get('family')!='medieval')
ours={t['id']:t for t in new['tasks'] if t.get('family')=='medieval'}
assert set(ours)=={'MVB01','MVB02'}|{f'MV{i:02}' for i in range(1,22)}
for before in old['tasks']:
    if before.get('family')!='medieval' or before['id']=='MV19':continue
    after=ours[before['id']]
    assert {k:v for k,v in before.items() if k not in ('sha256','build_sha256')}=={k:v for k,v in after.items() if k not in ('sha256','build_sha256')},before['id']
before=next(t for t in old['tasks'] if t['id']=='MV19')
assert ours['MV19']['revision']==before['revision']+1
assert 'vending' not in json.dumps(ours['MV18']).lower()
assert not re.search(r'replac|替换|油灯|oil lamp',json.dumps(ours['MV19']['rubrics_i18n'],ensure_ascii=False),re.I)
app=(stage/'static/app.js').read_text()
scenes=json.loads(re.search(r'const sceneDescriptions=(\[.*?\]);',app)[1])
for scene in scenes:
    if '/MedievalVillage/' in scene['map']:
        assert not re.search(r'WASD|\bE[- ]key|press E|mouse|鼠标|按 E|E 键',json.dumps(scene['description'],ensure_ascii=False),re.I)
assert sum('MV21' in s['task_ids'] for s in scenes)==1
for id in ('MV18','MV19','MV20','MV21'):
    assert ours[id]['subcategory']=='S3'
    for lang in ('en','zh'):
        assert all(ours[id]['rubrics_i18n'][lang][k].strip() for k in ('criteria','expected','steps'))
subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=stage,check=True)
subprocess.run(['/home/ubuntu/unreal-auditor/review-service/deps/node-v22.23.2-linux-x64/bin/node',str(Path(__file__).with_name('test_bug_type_order.cjs')),str(stage)],check=True)
report=dict(result='PASS',bugs=21,baselines=2,changed_cases=['MV19'],added_cases=['MV21'],all_other_case_metadata_preserved=True,other_runtime_profiles_preserved=True,bug_type_sorting=True)
(stage/'medieval-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
