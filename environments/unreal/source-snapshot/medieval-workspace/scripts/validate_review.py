"""Validate the additive catalog against the latest complete service implementation."""
from pathlib import Path
import json,subprocess,sys,hashlib
stage=Path(sys.argv[1]);state=Path('/home/ubuntu/unreal-auditor/review-service/state')
new=json.loads((stage/'tasks.json').read_text());old=json.loads((state/'tasks.json').read_text());cfg=json.loads((stage/'candidate-runtime.json').read_text());oldcfg=json.loads((state/'runtime.json').read_text())
assert [t for t in new['tasks'] if t.get('family')!='medieval']==old['tasks']
assert {k:v for k,v in cfg.items() if k!='launch_profiles'}=={k:v for k,v in oldcfg.items() if k!='launch_profiles'}
assert all(cfg['launch_profiles'][k]==v for k,v in oldcfg['launch_profiles'].items())
ours=[t for t in new['tasks'] if t.get('family')=='medieval'];assert len(ours)==20
assert {t['id'] for t in ours}=={'MVB01','MVB02'}|{f'MV{i:02}' for i in range(1,19)}
for t in ours:
 assert t['map'] in cfg['launch_profiles']
 assert Path(cfg['launch_profiles'][t['map']]['binary']).is_file()
 assert set(t['rubrics_i18n'])=={'en','zh'}
 for rub in t['rubrics_i18n'].values():assert len(rub['criteria'])>5
 assert t['runtime_switch']
subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=stage,check=True)
report=dict(result='PASS',new_entries=20,bugs=18,baselines=2,previous_entries_preserved=len(old['tasks']),runtime_profiles_preserved=True)
(stage/'medieval-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
