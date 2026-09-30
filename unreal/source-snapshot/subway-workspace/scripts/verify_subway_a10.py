#!/usr/bin/env python3
"""Verify the Linux package using its actual runtime, including escalator motion."""
from pathlib import Path
import subprocess,json
root=Path(__file__).resolve().parents[1];dist=root/'dist/subway-linux';logs=root/'out/verification';logs.mkdir(parents=True,exist_ok=True)
results=[]
def run(name,args,timeout=900):
 print(name+' started',flush=True)
 with (logs/(name+'.log')).open('w') as f:
  try:rc=subprocess.run(list(map(str,args)),stdout=f,stderr=subprocess.STDOUT,timeout=timeout).returncode
  except subprocess.TimeoutExpired:rc=-1
 results.append(dict(test=name,returncode=rc,result='PASS' if rc==0 else 'FAIL'))
 print(json.dumps(results[-1]),flush=True)
run('baseline-escalators',[dist/'Linux/Subway.sh','/Game/Auditor/Subway/Platform','-AuditorEscalatorBaselineTest','-AuditorTaskTest','-AuditorTestExit','-nullrhi','-nosound','-unattended'],120)
text=(logs/'baseline-escalators.log').read_text(errors='replace')
if 'Measured tread-bone motion on 8 escalators: 4 up, 4 down; playing=1' not in text:results[-1]['result']='FAIL'
run('tasks',['python3',root/'scripts/test_subway_tasks.py',dist],1600)
run('routes',['python3',root/'scripts/test_subway_build.py',dist],1000)
(logs/'summary.json').write_text(json.dumps(results,indent=2))
raise SystemExit(any(r['result']!='PASS' for r in results))
