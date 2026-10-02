from pathlib import Path
import json,subprocess,sys
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');cfg=json.loads((w/'projects.json').read_text())
for f in sys.argv[1:]:
 p=Path(cfg[f]['project']);log=w/'out'/('editor-'+f+'.log');print('EDITOR_START',f,flush=True)
 with log.open('w') as out:r=subprocess.run(['/opt/UnrealEngine_5.6/Engine/Build/BatchFiles/Linux/Build.sh',p.stem+'Editor','Linux','Development',str(p),'-WaitMutex','-MaxParallelActions=8','-NoUBA','-NoHotReloadFromIDE'],stdout=out,stderr=subprocess.STDOUT)
 if r.returncode:print(log.read_text()[-5000:],flush=True);raise SystemExit(r.returncode)
 print('EDITOR_PASS',f,flush=True)
