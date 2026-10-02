#!/usr/bin/env python3
"""Exercise region routes and invisible boundaries in the packaged factory."""
import argparse,json,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('distribution',type=Path)
a=p.parse_args();dist=a.distribution.resolve()
spec=json.loads((dist/'maps.json').read_text())
logs=ROOT/'out/industrial/runtime-tests';logs.mkdir(parents=True,exist_ok=True)
binary=dist/'Mac/FactoryEnvironmentCollect.app/Contents/MacOS/FactoryEnvironmentCollect'
if not binary.is_file():
    binary=dist/'Linux/FactoryEnvironmentCollect/Binaries/Linux/FactoryEnvironmentCollect'
if not binary.is_file():
    p.error('Distribution has neither a Mac nor a Linux industrial executable.')
def test_region(region):
    results=[]
    for kind in ['Boundary','Traversal']:
        print('Testing '+region['id']+' '+kind,flush=True)
        logfile=logs/(region['id']+'-'+kind.lower()+'.log')
        with logfile.open('w') as log:
            try:rc=subprocess.run([str(binary),region['map'],'-Auditor'+kind+'Test','-AuditorTestExit','-nullrhi','-nosound','-unattended','-stdout','-FullStdOutLogOutput','-ExecCmds=t.MaxFPS 30'],stdout=log,stderr=subprocess.STDOUT,timeout=150).returncode
            except subprocess.TimeoutExpired:rc=-1
        text=logfile.read_text(errors='replace')
        passed=rc==0 and 'AUDITOR_'+kind.upper()+'_TEST PASS map='+region['map'].rsplit('/',1)[1]+' ' in text and 'AUDITOR_OUT_OF_BOUNDS_RESET' not in text
        result=dict(region=region['id'],test=kind.lower(),result='PASS' if passed else 'FAIL',returncode=rc)
        results.append(result);print(json.dumps(result),flush=True)
    return results
with ThreadPoolExecutor(max_workers=2) as pool:
    results=[r for group in pool.map(test_region,spec['regions']) for r in group]
(dist/'runtime-verification.json').write_text(json.dumps(results,indent=2)+'\n')
if any(r['result']!='PASS' for r in results):raise SystemExit(1)
