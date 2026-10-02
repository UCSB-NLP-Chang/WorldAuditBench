from pathlib import Path
import subprocess,json,os
from concurrent.futures import ThreadPoolExecutor
r=Path('/home/ubuntu/unreal-auditor/industrial-workspace');logs=r/('out/editor-behavior-fixed' if os.getenv('INDUSTRIAL_TEST_IDS') else 'out/editor-behavior');logs.mkdir(exist_ok=True)
tasks=json.loads((r/'environments/industrial-factory/tasks.json').read_text())['tasks']
if os.getenv('INDUSTRIAL_TEST_IDS'):tasks=[t for t in tasks if t['id'] in os.environ['INDUSTRIAL_TEST_IDS'].split(',')]
def run(t):
 with (logs/(t['id']+'.log')).open('w') as f:
  try:rc=subprocess.run(['/opt/UnrealEngine_5.6/Engine/Binaries/Linux/UnrealEditor-Cmd',str(r/'project/FactoryEnvironmentCollect.uproject'),t['map']+'?Task='+t['id'],'-game','-AuditorTaskTest','-AuditorTestExit','-nullrhi','-nosound','-unattended','-stdout','-FullStdOutLogOutput','-ExecCmds=t.MaxFPS 30'],stdout=f,stderr=subprocess.STDOUT,timeout=100).returncode
  except subprocess.TimeoutExpired:rc=-1
 s=(logs/(t['id']+'.log')).read_text(errors='replace');e=[l for l in s.splitlines() if 'AUDITOR_TASK_TEST' in l];result=dict(id=t['id'],returncode=rc,evidence=e,result='PASS' if rc==0 and any('PASS id='+t['id']+' ' in l for l in e) else 'FAIL');print(json.dumps(result),flush=True);return result
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,tasks))
(logs/'results.json').write_text(json.dumps(results,indent=2))
