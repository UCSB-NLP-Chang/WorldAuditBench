#!/usr/bin/env python3
"""Exercise real collision and routes in each map of the packaged application."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('distribution', type=Path)
    args = parser.parse_args()
    dist = args.distribution.resolve()
    spec = json.loads((dist / 'maps.json').read_text())
    binary = dist / 'Linux/AtmosphericResidentialHou.sh'
    if not binary.is_file():
        binary = dist / 'Mac/AtmosphericResidentialHou.app/Contents/MacOS/AtmosphericResidentialHou'
    logs = ROOT / 'out/playtest/region-tests'
    logs.mkdir(parents=True, exist_ok=True)
    results = []
    for scene in spec['regions']:
        for kind, marker in [('Boundary', 'AUDITOR_BOUNDARY_TEST'), ('Traversal', 'AUDITOR_TRAVERSAL_TEST')]:
            output = logs / f"{scene['id']}-{kind.lower()}.log"
            print(f"Testing {scene['id']} {kind}...", flush=True)
            with output.open('w') as log:
                try:
                    process = subprocess.run([str(binary), scene['map'], f'-Auditor{kind}Test', '-AuditorTestExit',
                                              '-nullrhi', '-nosound', '-unattended'],
                                             stdout=log, stderr=subprocess.STDOUT, timeout=100)
                    returncode = process.returncode
                except subprocess.TimeoutExpired:
                    returncode = -1
            text = output.read_text(errors='replace')
            expected_result = marker + ' PASS map=' + scene['map'].rsplit('/', 1)[1] + ' '
            passed = returncode == 0 and expected_result in text and 'AUDITOR_OUT_OF_BOUNDS_RESET' not in text
            result = {'region': scene['id'], 'test': kind.lower(), 'result': 'PASS' if passed else 'FAIL',
                      'returncode': returncode}
            results.append(result)
            print(json.dumps(result), flush=True)
            (dist / 'runtime-verification.json').write_text(json.dumps(results, indent=2) + '\n')
    if any(r['result'] != 'PASS' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
