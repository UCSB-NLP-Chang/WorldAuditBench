#!/usr/bin/env python3
"""Run each authored task's behavioral checks in the packaged UE executable."""
import argparse
import json
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('distribution', type=Path)
p.add_argument('--ids', nargs='*')
p.add_argument('--catalog', type=Path, help='Private task catalog used by the operator for verification')
a = p.parse_args()
dist = a.distribution.resolve()
catalog = a.catalog or (dist/'tasks.json')
if not a.catalog and not catalog.is_file():
    catalog = ROOT/'environments/subway/tasks.json'
tasks = json.loads(catalog.read_text())['tasks']
regions = {r['id']: r['map'] for r in json.loads((dist/'maps.json').read_text())['regions']}
binary = dist/'Linux/Subway.sh'
if not binary.is_file():
    binary = dist/'Mac/Subway.app/Contents/MacOS/Subway'
logs = ROOT/'out/subway/task-tests'
logs.mkdir(parents=True, exist_ok=True)
results = []
for t in tasks:
    if a.ids and t['id'] not in a.ids: continue
    logfile = logs/(t['id']+'.log')
    print('Testing '+t['id']+' '+t['kind'], flush=True)
    with logfile.open('w') as log:
        try:
            rc = subprocess.run([str(binary), regions[t['region']], '-AuditorTask='+t['id'],
                '-AuditorTaskTest', '-AuditorTestExit', '-nullrhi', '-nosound', '-unattended'],
                stdout=log, stderr=subprocess.STDOUT, timeout=75).returncode
        except subprocess.TimeoutExpired: rc = -1
    text = logfile.read_text(errors='replace')
    ready = 'AUDITOR_TASK_READY id='+t['id']+' map='+regions[t['region']].rsplit('/',1)[1]
    passed = rc == 0 and ready in text and 'AUDITOR_TASK_TEST PASS id='+t['id']+' ' in text and 'AUDITOR_OUT_OF_BOUNDS_RESET' not in text
    marker = next((line.split('AUDITOR_TASK_TEST ',1)[1] for line in text.splitlines() if 'AUDITOR_TASK_TEST ' in line),'No result')
    result = dict(id=t['id'], category=t['category'], subcategory=t['subcategory'], region=t['region'], result='PASS' if passed else 'FAIL', detail=marker)
    results.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    output = 'task-verification-subset.json' if a.ids else 'task-verification.json'
    (dist/output).write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
if any(r['result'] != 'PASS' for r in results): raise SystemExit(1)
