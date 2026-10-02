"""Activate a staged Review release while leaving Explore/Evaluate services running."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def check_hashes(root, expected):
    for name, wanted in expected.items():
        if digest(root / name) != wanted:
            raise RuntimeError(f"Configuration changed concurrently: {name}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--production", type=Path, required=True)
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--start-runtime", action="store_true")
    p.add_argument("--activate", action="store_true")
    a = p.parse_args()
    receipt_path = a.release / "release.json"
    receipt = json.loads(receipt_path.read_text())
    check_hashes(a.production, receipt["protected_sha256"])
    check_hashes(a.production, receipt["expected_live_sha256"])
    qa = json.loads((a.release / "validation.json").read_text())
    if qa.get("status") != "PASS" or set(qa["tasks"]) != set(receipt["tasks"]) or qa["policy_sha256"] != receipt["policy_sha256"]:
        raise RuntimeError("Missing complete native validation for this exact policy")
    if a.start_runtime:
        unit = receipt["pool_service"]
        subprocess.run(["sudo", "-n", "install", "-m", "0644", str(a.release / unit), "/etc/systemd/system/" + unit], check=True)
        subprocess.run(["sudo", "-n", "systemctl", "daemon-reload"], check=True)
        subprocess.run(["sudo", "-n", "systemctl", "enable", "--now", unit], check=True)
        print("Independent Review runtime started; website still uses the previous release")
    if not a.activate:
        return
    smoke = json.loads((a.release / "smoke.json").read_text())
    if smoke.get("status") != "PASS":
        raise RuntimeError("Review streaming smoke test has not passed")
    lock = (a.production / "audit/.release-lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    db = sqlite3.connect("file:" + str(a.production / "audit/review.sqlite3") + "?mode=ro", uri=True)
    active = db.execute("SELECT count(*) FROM sessions WHERE status IN ('queued','starting','ready')").fetchone()[0]
    db.close()
    if active:
        raise RuntimeError(f"{active} active Review sessions: wait for them to close before switching")
    services = ["aws-unreal-pool.service", "aws-unreal-explore.service", "aws-unreal-evaluate.service", "aws-unreal-threejs.service"]
    def pids():
        return {s: subprocess.check_output(["systemctl", "show", s, "--property=MainPID", "--value"], text=True).strip() for s in services}
    protected_pids = pids()
    check_hashes(a.production, receipt["expected_live_sha256"])
    backup = a.release / "before-activation"
    backup.mkdir(exist_ok=False)
    for name in receipt["expected_live_sha256"]:
        source = a.production / name
        if source.exists():
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    def replace(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".release-tmp")
        shutil.copy2(source, temporary)
        temporary.chmod(0o600)
        temporary.replace(target)
    try:
        for name in receipt["expected_live_sha256"]:
            replace(a.release / "config" / name, a.production / name)
        subprocess.run(["sudo", "-n", "systemctl", "restart", "aws-unreal-audit.service"], check=True)
        time.sleep(2)
        subprocess.run(["systemctl", "is-active", "--quiet", "aws-unreal-audit.service"], check=True)
        check_hashes(a.production, receipt["protected_sha256"])
        if pids() != protected_pids:
            raise RuntimeError("A protected service changed during activation")
    except Exception:
        for name, old_hash in receipt["expected_live_sha256"].items():
            if old_hash is None:
                (a.production / name).unlink(missing_ok=True)
            else:
                replace(backup / name, a.production / name)
        subprocess.run(["sudo", "-n", "systemctl", "restart", "aws-unreal-audit.service"], check=True)
        raise
    receipt.update(status="published", activated_at=time.time(), protected_service_pids=protected_pids)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Published {len(receipt['tasks'])} Review Unreal tasks; protected services were not restarted")


if __name__ == "__main__":
    main()
