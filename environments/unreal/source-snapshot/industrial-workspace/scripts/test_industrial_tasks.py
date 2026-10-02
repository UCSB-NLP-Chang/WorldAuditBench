#!/usr/bin/env python3
"""Run the packaged industrial task behaviors at the review service's tick rate."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('distribution', type=Path)
    args = parser.parse_args()
    dist = args.distribution.resolve()
    binary = dist / 'Linux/FactoryEnvironmentCollect/Binaries/Linux/FactoryEnvironmentCollect'
    tasks = json.loads((dist / 'tasks.json').read_text())['tasks']
    logs = dist / 'behavior-tests'
    logs.mkdir(exist_ok=True)

    def test(task):
        log = logs / (task['id'] + '.log')
        with log.open('w') as stream:
            try:
                rc = subprocess.run([str(binary), task['map'] + '?Task=' + task['id'],
                                     '-AuditorTaskTest', '-AuditorTestExit', '-nullrhi', '-nosound',
                                     '-unattended', '-stdout', '-FullStdOutLogOutput',
                                     '-ExecCmds=t.MaxFPS 30'], stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=90).returncode
            except subprocess.TimeoutExpired:
                rc = -1
        text = log.read_text(errors='replace')
        evidence = [line for line in text.splitlines() if 'AUDITOR_TASK_TEST ' in line]
        passed = rc == 0 and any('PASS id=' + task['id'] + ' ' in line for line in evidence)
        result = dict(id=task['id'], result='PASS' if passed else 'FAIL', returncode=rc, evidence=evidence)
        print(json.dumps(result), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(test, tasks))
    (logs / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    if any(result['result'] != 'PASS' for result in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
