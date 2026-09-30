from pathlib import Path
import json,os,subprocess,concurrent.futures
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');cfg=json.loads((w/'projects.json').read_text())
def run(item):
 f,s=item;env=dict(os.environ,CONFIGURATION_FAMILY=f)
 if (w/'out'/('inventory-'+f+'.json')).exists():return True
 with (w/'out'/('inspect-'+f+'.log')).open('w') as log:
  result=subprocess.run(['/opt/UnrealEngine_5.6/Engine/Binaries/Linux/UnrealEditor-Cmd',s['project'],'-run=pythonscript','-script='+str(w/'scripts/inspect_maps.py'),'-nullrhi','-nosound','-unattended'],env=env,stdout=log,stderr=subprocess.STDOUT)
 text=(w/'out'/('inspect-'+f+'.log')).read_text(errors='replace');ok=result.returncode==0 and (w/'out'/('inventory-'+f+'.json')).exists()
 print(f,ok,flush=True)
 if not ok:print('\n'.join([l for l in text.splitlines() if 'Error:' in l][-12:]),flush=True)
 return ok
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:assert all(list(pool.map(run,cfg.items())))
