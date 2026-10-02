"""Finish the current unpublished build, then verify its packaged artifacts."""
from pathlib import Path
import os,time,json,subprocess,shutil,concurrent.futures
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');first=Path('/proc/517644/cmdline')
while first.exists() and b'/medieval-workspace/scripts/build_linux.py' in first.read_bytes():time.sleep(5)
assert (r/'dist/medieval-linux-v1/build-provenance.json').exists(),'Initial package did not finish successfully'
shutil.copy2(r/'out/build/package.log',r/'out/build/package-first.log')
# Incorporate the view-direction correction authored while the first full compile ran.
with (r/'out/build/final-driver.log').open('w') as log:
 subprocess.run(['python3',str(r/'scripts/build_linux.py')],env=os.environ|{'MEDIEVAL_SKIP_COOK':'1'},stdout=log,stderr=subprocess.STDOUT,check=True)
checks=['test_packaged.py','test_reuse.py','render_packaged.py']
def run(script):
 with (r/'out'/('final-'+script+'.log')).open('w') as log:
  code=subprocess.run(['python3',str(r/'scripts'/script)],stdout=log,stderr=subprocess.STDOUT).returncode
 return dict(script=script,ok=code==0,exit_code=code)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,checks))
(r/'out/pipeline-result.json').write_text(json.dumps(results,indent=2));print(json.dumps(results),flush=True)
raise SystemExit(0 if all(x['ok'] for x in results) else 1)
