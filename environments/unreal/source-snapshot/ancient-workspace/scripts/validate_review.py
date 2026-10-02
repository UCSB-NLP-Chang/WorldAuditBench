"""Verify isolated scope, all catalog regressions, copy and global type ordering."""
from pathlib import Path
import json,re,subprocess,sys
stage=Path(sys.argv[1]);state=Path('/home/ubuntu/unreal-auditor/review-service/state')
new=json.loads((stage/'tasks.json').read_text());old=json.loads((state/'tasks.json').read_text());cfg=json.loads((stage/'candidate-runtime.json').read_text());oldcfg=json.loads((state/'runtime.json').read_text())
assert [t for t in new['tasks'] if t.get('family')!='ancient']==[t for t in old['tasks'] if t.get('family')!='ancient']
assert {k:v for k,v in cfg.items() if k!='launch_profiles'}=={k:v for k,v in oldcfg.items() if k!='launch_profiles'}
assert all(cfg['launch_profiles'][k]==v for k,v in oldcfg['launch_profiles'].items() if v.get('family')!='ancient')
ours={t['id']:t for t in new['tasks'] if t.get('family')=='ancient'};assert set(ours)=={'AB01','AB02','AB03'}|{f'A{i:02}' for i in range(1,25)}
for b in old['tasks']:
 if b.get('family')=='ancient':assert {k:v for k,v in b.items() if k not in ('sha256','build_sha256')}=={k:v for k,v in ours[b['id']].items() if k not in ('sha256','build_sha256')},b['id']
scenes=json.loads(re.search(r'const sceneDescriptions=(\[.*?\]);',(stage/'static/app.js').read_text())[1])
source=Path(json.loads((stage/'ancient-provenance.json').read_text())['source_release'])
before_scenes=json.loads(re.search(r'const sceneDescriptions=(\[.*?\]);',(source/'static/app.js').read_text())[1])
assert [s for s in scenes if '/AncientCity/' not in s['map']]==[s for s in before_scenes if '/AncientCity/' not in s['map']]
for s in scenes:
 if '/AncientCity/' in s['map']:assert not re.search(r'WASD|\bE[- ]key|press E|mouse|鼠标|按 E|E 键',json.dumps(s['description'],ensure_ascii=False),re.I)
for id in ['A21','A22','A23','A24']:
 assert sum(id in s['task_ids'] for s in scenes)==1 and ours[id]['subcategory']=='S3'
 assert not re.search(r'replac|替换|keyboard|键盘',json.dumps(ours[id]['rubrics_i18n'],ensure_ascii=False),re.I)
 for lang in ['en','zh']:
  assert all(ours[id]['rubrics_i18n'][lang][k].strip() for k in ['criteria','expected','steps'])
subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=stage,check=True)
subprocess.run(['/home/ubuntu/unreal-auditor/review-service/deps/node-v22.23.2-linux-x64/bin/node',str(Path(__file__).with_name('test_bug_type_order.cjs')),str(stage)],check=True)
report=dict(result='PASS',bugs=24,baselines=3,added_cases=['A21','A22','A23','A24'],existing_case_metadata_preserved=True,other_runtime_profiles_preserved=True,bug_type_sorting=True)
(stage/'ancient-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
