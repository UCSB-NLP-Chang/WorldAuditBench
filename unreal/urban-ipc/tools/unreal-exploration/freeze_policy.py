"""Freeze native collision-planned poses; reject partial or unsafe releases."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path


def validate_entry(task_id, entry, report):
    if entry["id"] != task_id or report.get("id") != task_id:
        raise ValueError(f"{task_id}: report identity mismatch")
    if report.get("status") != "planned":
        raise ValueError(f"{task_id}: no successful planning report")
    if entry["family"].startswith("threejs") or not entry["map"].startswith("/Game/"):
        raise ValueError(f"{task_id}: only Unreal tasks may be revised")
    spawn = report["spawn"]
    if len(spawn) != 3 or not all(math.isfinite(v) for v in spawn):
        raise ValueError(f"{task_id}: invalid spawn")
    for axis in (0, 1):
        if not entry["bounds_min"][axis] + 34 <= spawn[axis] <= entry["bounds_max"][axis] - 34:
            raise ValueError(f"{task_id}: spawn touches boundary")
        if entry["bounds_min"][axis] > entry["old_bounds_min"][axis] or entry["bounds_max"][axis] < entry["old_bounds_max"][axis]:
            raise ValueError(f"{task_id}: exploration area shrank")
    if report["bounds_min"] != entry["bounds_min"] or report["bounds_max"] != entry["bounds_max"]:
        raise ValueError(f"{task_id}: planning report used different bounds")
    distance = math.dist(spawn[:2], entry["focus"][:2])
    old_distance = math.dist(report["old_spawn"][:2], entry["focus"][:2])
    if abs(distance - report["distance_cm"]) > .1 or abs(old_distance - report["old_distance_cm"]) > .1:
        raise ValueError(f"{task_id}: stale focus or distance report")
    if distance + .1 < old_distance + entry["gain_cm"]:
        raise ValueError(f"{task_id}: spawn is not far enough from the target")
    bearing = math.degrees(math.atan2(entry["focus"][1] - spawn[1], entry["focus"][0] - spawn[0]))
    offset = abs((report["yaw"] - bearing + 180) % 360 - 180)
    if not 109.9 <= offset <= 150.1:
        raise ValueError(f"{task_id}: initial camera faces the target")
    route = report.get("route_to_old_spawn", [])
    if len(route) < 2 or math.dist(route[0], spawn) > .1:
        raise ValueError(f"{task_id}: missing connected collision-planned route")
    return {"old_distance_cm": old_distance, "distance_cm": distance,
            "yaw_offset_deg": offset, "route_length_cm": sum(math.dist(a, b) for a, b in zip(route, route[1:])),
            "used_region_route_anchor": report.get("used_region_route_anchor", False)}


def freeze(policy, catalog, report_dir):
    expected = {t["id"] for t in catalog["tasks"] if t.get("runtime_kind") != "browser" and t.get("map", "").startswith("/Game/")}
    if set(policy["tasks"]) != expected:
        raise ValueError("Policy must cover every current Unreal task, and no browser task")
    result = copy.deepcopy(policy)
    audit = {}
    for task_id, entry in result["tasks"].items():
        report = json.loads((report_dir / f"{task_id}.json").read_text())
        audit[task_id] = validate_entry(task_id, entry, report)
        entry["spawn"] = report["spawn"]
        entry["yaw"] = report["yaw"]
        entry["route_to_old_spawn"] = report["route_to_old_spawn"]
    result["version"] = "unreal-exploration-v2-20260917"
    result["frozen"] = True
    return result, audit


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--reports", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result, audit = freeze(json.loads(a.policy.read_text()), json.loads(a.catalog.read_text()), a.reports)
    encoded = (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode()
    a.out.write_bytes(encoded)
    audit_path = a.out.with_suffix(".audit.json")
    audit_path.write_text(json.dumps({"policy_sha256": hashlib.sha256(encoded).hexdigest(), "tasks": audit}, indent=2) + "\n")
    print(f"Frozen {len(audit)} tasks; sha256={hashlib.sha256(encoded).hexdigest()}")
