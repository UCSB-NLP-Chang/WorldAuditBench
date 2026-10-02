#!/usr/bin/env python3
"""Build the authoritative Subway project on A10; never regenerates authored maps."""
import json,subprocess,hashlib,shutil,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=Path('/home/ubuntu/unreal-auditor/projects/Subway/Subway.uproject')

import argparse
args=argparse.ArgumentParser();args.add_argument('--output',type=Path);options=args.parse_args()

# The published executables share one coordinator; prevent replacement during review.
import sqlite3
review_state=Path('/home/ubuntu/unreal-auditor/review-service/state')
if options.output is None and (review_state/'review.sqlite3').exists():
 db=sqlite3.connect('file:'+str(review_state/'review.sqlite3')+'?mode=ro',uri=True)
 active=db.execute("SELECT COUNT(*) FROM sessions WHERE status IN ('queued','starting','ready','resetting','switching','closing')").fetchone()[0];db.close()
 if active:raise SystemExit('Finish active unified review sessions before replacing a published executable.')
 subprocess.run(['sudo','systemctl','stop','urban-review-pilot.service'],check=True)
 print('Unified review paused during build. Publish after verification to restart.',flush=True)
e=Path('/opt/UnrealEngine_5.6/Engine');out=options.output.resolve() if options.output else root/'dist/subway-linux';logs=root/'out/build';logs.mkdir(parents=True,exist_ok=True)
spec=json.loads((root/'environments/subway/regions.json').read_text())
def run(name,args):
 print(name+' started',flush=True)
 with (logs/(name+'.log')).open('w') as f:subprocess.run(list(map(str,args)),stdout=f,stderr=subprocess.STDOUT,check=True)
 print(name+' PASS',flush=True)
run('editor',[e/'Build/BatchFiles/Linux/Build.sh','SubwayEditor','Linux','Development',p,'-NoHotReloadFromIDE','-MaxParallelActions=20','-NoUBA'])
map_report=p.parent/'Saved/subway-map-verification.json'
map_report.unlink(missing_ok=True)
run('maps',[e/'Binaries/Linux/UnrealEditor-Cmd',p,'-run=pythonscript','-script='+str(root/'scripts/unreal_verify_subway_regions.py'),'-nullrhi','-nosound','-unattended'])
assert json.loads(map_report.read_text())['result']=='PASS', 'Map verification did not succeed'
run('package',[e/'Build/BatchFiles/RunUAT.sh','BuildCookRun','-project='+str(p),'-platform=Linux','-clientconfig=Development','-build','-cook','-stage','-pak','-package','-archive','-archivedirectory='+str(out),'-map='+'+'.join(r['map'] for r in spec['regions']),'-nop4','-utf8output','-unattended','-UbtArgs=-MaxParallelActions=20 -NoUBA'])
shutil.copy2(root/'environments/subway/regions.json',out/'maps.json')
shutil.copy2(root/'environments/subway/tasks.json',out/'tasks.json')
binary=out/'Linux/Subway/Binaries/Linux/Subway'
(out/'build-provenance.json').write_text(json.dumps({'project':str(p),'engine':'5.6.1','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'maps_regenerated':False},indent=2))
print('BUILD COMPLETE '+str(out),flush=True)
