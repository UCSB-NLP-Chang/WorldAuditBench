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
    if args.resources:
        for row in resources["resources"]:
            if "path" not in row:
                errors.append(f"Resource packaging pending: {row['group']}")
                continue
            p = ROOT / row["path"]
            if not p.is_file() or digest(p) != row["sha256"]:
                errors.append(f"Missing or mismatched resource: {row['path']}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Verified 213 paper tasks (126 Unreal, 87 Three.js), 5 family counts, and {checked} source files.")
    print("External resources: " + resources["status"] + " (see resources/manifest.json).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
