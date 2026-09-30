"""Finish the current unpublished build, then verify its packaged artifacts."""
from pathlib import Path
import os,time,json,subprocess,shutil,concurrent.futures
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace')
checks=['test_packaged.py','test_reuse.py','render_packaged.py']
def run(script):
 with (r/'out'/('final-'+script+'.log')).open('w') as log:
  code=subprocess.run(['python3',str(r/'scripts'/script)],stdout=log,stderr=subprocess.STDOUT).returncode
 return dict(script=script,ok=code==0,exit_code=code)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,checks))
(r/'out/pipeline-result.json').write_text(json.dumps(results,indent=2));print(json.dumps(results),flush=True)
raise SystemExit(0 if all(x['ok'] for x in results) else 1)
