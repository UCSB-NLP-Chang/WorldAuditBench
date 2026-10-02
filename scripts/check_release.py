#!/usr/bin/env python3
"""Check the paper cohort and imported source hashes without external resources."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", action="store_true", help="also require and hash the external files with known restore paths")
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "out/runtime")
    args = parser.parse_args()
    cohort = json.loads((ROOT / "benchmark/paper-tasks.json").read_text())
    tasks = cohort["tasks"]
    errors = []
    ids = {t["id"] for t in tasks}
    if len(tasks) != 213 or len(ids) != 213:
        errors.append("Paper cohort must contain 213 unique tasks")
    engines = Counter("threejs" if t["family"].startswith("threejs_") else "unreal" for t in tasks)
    if engines != {"unreal": 126, "threejs": 87}:
        errors.append(f"Engine counts differ from paper: {dict(engines)}")
    expected = {"Static physics": 59, "Interactive physics": 41, "Spatial consistency": 51,
                "Temporal consistency": 40, "Semantic consistency": 22}
    if Counter(t["paper_family"] for t in tasks) != expected:
        errors.append("Family counts differ from paper")
    for split in ("all", "unreal", "threejs"):
        actual = (ROOT / f"benchmark/splits/{split}.txt").read_text().splitlines()
        wanted = {t["id"] for t in tasks if split == "all" or
                  ("threejs" if t["family"].startswith("threejs_") else "unreal") == split}
        if set(actual) != wanted or len(actual) != len(wanted):
            errors.append(f"Invalid split: {split}")
    receipt = json.loads((ROOT / "docs/migration/aws-source-files.json").read_text())
    checked = 0
    for row in receipt["files"]:
        if row["status"] not in ("unchanged", "adapted"):
            continue
        p = ROOT / row["path"]
        if not p.is_file() or digest(p) != row["released_sha256"]:
            errors.append(f"Source hash mismatch: {row['path']}")
        checked += 1
    resources = json.loads((ROOT / "resources/manifest.json").read_text())
    release = json.loads((ROOT / 'resources/releases.json').read_text())
    runtime_ids = []
    for package in release['packages']:
        if len(package['revision']) != 40 or any(c not in '0123456789abcdef' for c in package['revision']):
            errors.append('Unpinned resource revision: ' + package['id'])
        if len(package['sha256']) != 64 or package['bytes'] <= 0:
            errors.append('Invalid resource identity: ' + package['id'])
        if package['group'] == 'unreal-runtime':
            runtime_ids.extend(package['tasks'])
            if 'variants' in package:
                variant_tasks = [t for v in package['variants'] for t in v['tasks']]
                if sorted(variant_tasks) != sorted(package['tasks']):
                    errors.append('Variant task coverage differs: ' + package['id'])
    expected_unreal = set((ROOT / 'benchmark/splits/unreal.txt').read_text().splitlines())
    if set(runtime_ids) != expected_unreal or len(runtime_ids) != len(expected_unreal):
        errors.append('Runtime packages must cover each Unreal paper task exactly once')
    if args.resources:
        for row in resources["resources"]:
            if row['status'] != 'available' or 'path' not in row:
                continue
            p = ((args.runtime_root / 'threejs-builds' / Path(row['path']).name)
                 if row['group'] == 'threejs-builds' else ROOT / row["path"])
            if not p.is_file() or digest(p) != row["sha256"]:
                errors.append(f"Missing or mismatched resource: {row['path']}")
        for package in release['packages']:
            directory = args.runtime_root / package['id']
            marker = directory / '.worldauditbench-release.json'
            try:
                if json.loads(marker.read_text())['sha256'] != package['sha256']:
                    errors.append('Installed release differs: ' + package['id'])
            except (OSError, ValueError, KeyError):
                errors.append('Missing installed release: ' + package['id'])
            for build in package.get('variants', [package] if package.get('binary') else []):
                binary = directory / build['binary']
                if not binary.is_file() or digest(binary) != build['binary_sha256']:
                    errors.append('Missing or mismatched executable: ' + build['id'])
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Verified 213 paper tasks (126 Unreal, 87 Three.js), 5 family counts, and {checked} source files.")
    print("External resources: " + resources["status"] + " (see resources/manifest.json).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
