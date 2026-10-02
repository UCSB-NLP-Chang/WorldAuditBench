from pathlib import Path
import json,hashlib,subprocess
w=Path('/home/ubuntu/unreal-auditor/review-save-on-navigation');proof=json.loads((w/'proof.json').read_text());live=Path(subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip());assert str(live)==proof['release'];check=json.loads((w/'out/candidate-report.json').read_text());assert check['status']=='PASS' and len(check['scenarios'])==7
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for n,h in proof['hashes'].items():assert sha(live/'static'/n)==h,('Live asset changed',n)
for n in ['app.js','index.html']:
 dest=live/'static'/n;tmp=dest.with_name(n+'.save-navigation-new');tmp.write_bytes((w/'candidate'/n).read_bytes());tmp.chmod(dest.stat().st_mode & 0o777);tmp.replace(dest)
report=dict(status='PASS',release=str(live),changed_files=['app.js','index.html'],service_restarted=False,production_feedback_written=False,browser_scenarios=7,hashes={n:sha(live/'static'/n) for n in proof['hashes']});(w/'out/deployment-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
