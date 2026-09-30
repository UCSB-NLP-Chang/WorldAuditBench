"""Create an immutable Review-only release, without changing any live configuration."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import secrets
import subprocess


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def preserve_review_versions(previous, updated):
    """Keep annotation validity for an exploration-only update, never copy votes."""
    for key in ("id", "family", "case_type", "map"):
        if previous.get(key) != updated.get(key):
            raise ValueError(f"Cannot inherit approvals after changing {key}")
    for language in ("zh", "en"):
        for field in ("criteria", "expected"):
            before = previous.get("rubrics_i18n", {}).get(language, {}).get(field)
            after = updated.get("rubrics_i18n", {}).get(language, {}).get(field)
            if before != after:
                raise ValueError("Changed bug rubric requires independent review")
    versions = copy.deepcopy(previous.get("review_compatible_versions", []))
    original = {key: previous[key] for key in ("revision", "sha256", "build_sha256")}
    if original not in versions:
        versions.append(original)
    updated["review_compatible_versions"] = versions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--production", type=Path, required=True)
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--compiled", type=Path, required=True)
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--source-catalog", type=Path, required=True)
    p.add_argument("--allow-partial", action="store_true", help="Publish only fully validated policy tasks; preserve every other task")
    a = p.parse_args()
    a.release.mkdir(parents=True, exist_ok=True)
    config = a.release / "config"
    if config.exists():
        raise SystemExit("Release configuration already exists; use a fresh release directory")
    catalog = json.loads((a.production / "audit/tasks.json").read_text())
    runtime = json.loads((a.production / "shared/runtime-prod.json").read_text())
    manifest = json.loads((a.production / "shared/manifest.json").read_text())
    scheduler = json.loads((a.production / "shared/scheduler-prod.json").read_text())
    policy = json.loads(a.policy.read_text())
    if not policy.get("frozen"):
        raise SystemExit("Only a completely frozen, validated policy may be staged")
    source = {t["id"]: t for t in json.loads(a.source_catalog.read_text())["tasks"]}
    unreal = {t["id"]: t for t in catalog["tasks"] if t.get("map", "").startswith("/Game/") and t.get("runtime_kind") != "browser"}
    if (not a.allow_partial and set(unreal) != set(policy["tasks"])) or not set(policy["tasks"]).issubset(unreal) or set(unreal) != set(source):
        raise SystemExit("Live Unreal catalog coverage changed; rebase and validate again")
    for key, task in unreal.items():
        if task != source[key]:
            raise SystemExit(f"Live Unreal task changed since preparation: {key}")
    all_unreal = dict(unreal)
    unreal = {k: t for k, t in unreal.items() if k in policy["tasks"]}
    before_catalog, before_runtime = copy.deepcopy(catalog), copy.deepcopy(runtime)
    shutil.copy2(a.policy, a.release / "policy.json")
    policy_path = a.release / "policy.json"
    policy_path.chmod(0o600)
    policy_sha = digest(policy_path)
    packages, profiles_changed = {}, {}
    binaries = {}
    for task_id, task in unreal.items():
        matches = [(key, prof) for key, prof in runtime["launch_profiles"].items()
                   if key.startswith("/Shared/review/") and prof.get("runtime_map") == task["map"]]
        if len(matches) != 1:
            raise SystemExit(f"Expected exactly one Review launch profile: {task_id}")
        key, profile = matches[0]
        assert profile["build_sha256"] == task["build_sha256"]
        family = task["family"]
        if family not in binaries:
            receipt = json.loads((a.compiled / family / "compile-v2.json").read_text())
            executable = a.compiled / family / Path(receipt["binary"]).name
            assert receipt["status"] == "PASS" and digest(executable) == receipt["sha256"]
            binaries[family] = (executable, receipt["sha256"])
        executable, build_sha = binaries[family]
        old_binary = Path(profile["binary"])
        old_root = old_binary.parents[4]
        if str(old_root) not in packages:
            suffix = hashlib.sha256(str(old_root).encode()).hexdigest()[:12]
            dest = a.release / "packages" / f"{family}-{suffix}"
            dest.parent.mkdir(exist_ok=True)
            if dest.exists():
                raise SystemExit(f"Candidate package already exists: {dest}")
            assert not old_root.is_symlink(), "Package root must be a real directory"
            subprocess.run(["cp", "-al", str(old_root), str(dest)], check=True)
            assert not dest.is_symlink()
            # Runtime settings and logs must never share hard links with production.
            for saved in dest.glob("Linux/*/Saved"):
                if saved.is_dir() and not saved.is_symlink():
                    shutil.rmtree(saved)
                    saved.mkdir()
            new_binary = dest / old_binary.relative_to(old_root)
            original_sha = digest(old_binary)
            new_binary.unlink()  # Break the hard link before writing the candidate.
            shutil.copy2(executable, new_binary)
            assert digest(old_binary) == original_sha, "Published binary was modified"
            packages[str(old_root)] = {"binary": str(new_binary), "source_binary": str(old_binary), "source_sha256": original_sha, "build_sha256": build_sha}
        package = packages[str(old_root)]
        assert package["build_sha256"] == build_sha
        profile["binary"] = package["binary"]
        profile["build_sha256"] = build_sha
        profile["extra_args"] = [x for x in profile.get("extra_args", []) if not x.startswith("-AuditorExploration")]
        profile["extra_args"] += [f"-AuditorExplorationPolicy={policy_path}", f"-AuditorExplorationTask={task_id}"]
        profiles_changed[key] = task_id
        task["build_sha256"] = build_sha
        task["exploration_revision"] = {"version": policy["version"], "policy_sha256": policy_sha,
                                        "previous_build_sha256": source[task_id]["build_sha256"]}
        # Keep original map revision (it is part of Urban cooked map paths).
        # Changed build identity separates the new start from historical reviews.
        preserve_review_versions(source[task_id], task)
        for language, text in task.get("rubrics_i18n", {}).items():
            steps = text.get("steps", "")
            for old, new in [
                ("You start near and facing the target.", "Locate and approach the target."),
                ("You start facing both posters.", "Locate the two wall posters."),
                ("开始时已在近处面向目标。", "先找到并走近目标。"),
                ("开始时正对两张海报，", "找到墙上的两张海报后，"),
                ("走近出生点旁最近的圆形咖啡桌", "找到并走近圆形咖啡桌"),
                ("Approach the nearest round café table", "Find and approach the round café table"),
            ]:
                steps = steps.replace(old, new)
            text["steps"] = steps
        if task.get("rubrics_i18n") != source[task_id].get("rubrics_i18n"):
            # Preserve every other part of the bilingual rubric verbatim.
            for lang, old in source[task_id]["rubrics_i18n"].items():
                task["rubrics"] = task["rubrics"].replace(old["steps"], task["rubrics_i18n"][lang]["steps"])
    for row in manifest["tasks"]:
        if row["map"] in profiles_changed:
            row["build_sha256"] = runtime["launch_profiles"][row["map"]]["build_sha256"]
    for row in scheduler["tasks"]:
        if row.get("map") in profiles_changed:
            profile = runtime["launch_profiles"][row["map"]]
            row["group"] = hashlib.sha256((profile["binary"] + profile["build_sha256"] + policy_sha).encode()).hexdigest()
    # Explicit invariants: the shared service may change Review profiles only.
    for key, profile in before_runtime["launch_profiles"].items():
        if key not in profiles_changed:
            assert runtime["launch_profiles"][key] == profile
    for old, new in zip(before_catalog["tasks"], catalog["tasks"]):
        if old["id"] not in unreal:
            assert new == old, "Non-Unreal task changed"
    # A separate Review supervisor avoids restarting the live Explore GPU pool.
    # Model experiments are stopped; GPUs 2 and 3 are dedicated to this new pool.
    runtime_dir = a.release / "runtime"
    runtime["launch_profiles"] = {k: v for k, v in runtime["launch_profiles"].items() if k.startswith("/Shared/review/")}
    manifest["tasks"] = [t for t in manifest["tasks"] if t["map"] in runtime["launch_profiles"]]
    scheduler["tasks"] = [t for t in scheduler["tasks"] if t.get("map") in runtime["launch_profiles"]]
    gpu_rows = subprocess.check_output(["nvidia-smi", "--query-gpu=index,uuid,memory.used,memory.total", "--format=csv,noheader,nounits"], text=True)
    gpu_info = {int(row.split(",")[0]): [x.strip() for x in row.split(",")[1:]] for row in gpu_rows.strip().splitlines()}
    for gpu in [2, 3]:
        if gpu not in gpu_info or int(gpu_info[gpu][1]) > 128:
            raise SystemExit(f"Review GPU {gpu} is not idle; do not take over another workload")
    runtime.update(manifest=str(runtime_dir / "manifest.json"), state_dir=str(runtime_dir / "sessions"),
                   supervisor_port=19592, secret=secrets.token_urlsafe(32), player_port=18482,
                   streamer_port=19482, sfu_port=20482, own_turn=False,
                   scheduler_config=str(runtime_dir / "scheduler.json"), capacity=6,
                   slot_gpus=[2, 3, 2, 3, 2, 3], allowed_gpus=[2, 3])
    scheduler.update(database=str(runtime_dir / "pool.sqlite3"), port=19593,
                     runtime_config=str(runtime_dir / "runtime.json"))
    scheduler.pop("history_file", None)
    scheduler["limits"].update(slots=6, slot_gpus=runtime["slot_gpus"],
                               gpu_devices=[{"index": g, "uuid": gpu_info[g][0], "memory_mb": 21000} for g in [2, 3]],
                               submission_targets={})
    client = copy.deepcopy(scheduler["clients"]["review"])
    client["token"] = secrets.token_urlsafe(32)
    client["tasks"] = [t["id"] for t in scheduler["tasks"]]
    scheduler["clients"] = {"review": client}
    # SupervisorDriver reads these two keys; retain any optional driver fields.
    scheduler["supervisor"].update(supervisor_url="http://127.0.0.1:19592", secret=runtime["secret"], namespace="review-v2-20260917")
    link = json.loads((a.production / "shared/production-links/review.json").read_text())
    link.update(url="http://127.0.0.1:19593", token=client["token"], player_port=18482)
    env = json.loads((a.production / "audit/service-env.json").read_text())
    link_relative = "shared/production-links/review-v2/review.json"
    env.update(REVIEW_SHARED_SCHEDULER=str(a.production / link_relative),
               REVIEW_STREAM_PORTS=json.dumps(list(range(18482, 18488))))
    files = {"audit/tasks.json": catalog, "audit/runtime.json": runtime, "audit/service-env.json": env, link_relative: link}
    expected = {name: digest(a.production / name) if (a.production / name).exists() else None for name in files}
    for name, value in files.items():
        write(config / name, value)
    for name, value in {"runtime.json": runtime, "manifest.json": manifest,
                        "scheduler.json": scheduler}.items():
        write(runtime_dir / name, value)
    (runtime_dir / "sessions").mkdir()
    code = a.production / "code/explore"
    unit = f"""[Unit]
Description=Independent Unreal Review environment v2
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory={code}
ExecStart=/usr/bin/python3.12 -m bf.shared_runtime_main {runtime_dir / 'runtime.json'}
Restart=on-failure
RestartSec=3
KillMode=control-group
TimeoutStopSec=90
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ReadWritePaths={runtime_dir}
LimitNOFILE=65536
[Install]
WantedBy=multi-user.target
"""
    (a.release / "aws-unreal-review-pool-v2.service").write_text(unit)
    protected = ["shared/runtime-prod.json", "shared/manifest.json", "shared/scheduler-prod.json",
                 "shared/exploration-prod.json", "config/evaluation.json", "shared/production-links/explore.json",
                 "shared/production-links/review.json"]
    protected_hashes = {name: digest(a.production / name) for name in protected if (a.production / name).exists()}
    write(a.release / "release.json", {"status": "staged_not_published", "scope": "Review Unreal only",
          "policy_sha256": policy_sha, "tasks": list(unreal), "profiles": profiles_changed,
          "packages": packages, "expected_live_sha256": expected, "protected_sha256": protected_hashes,
          "unchanged_unreal_tasks": sorted(set(all_unreal)-set(unreal)), "dedicated_gpus": [2, 3], "pool_service": "aws-unreal-review-pool-v2.service"})
    print(f"Staged {len(unreal)} Review tasks; Explore, Evaluate and Three.js are unchanged")


if __name__ == "__main__":
    main()
