"""Run a fresh, private episode from an AWS review build; do not change production."""
import argparse
import atexit
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time
import threading
import xml.etree.ElementTree as ET
import uuid

from environment_server import APIError, Environment, UnrealBackend, serve


def select_profile(runtime, task, map_name):
    matches = [v for v in runtime["launch_profiles"].values()
               if v.get("build_sha256") == task["build_sha256"]
               and v.get("runtime_map") in (task["map"], map_name)]
    exact = [v for v in matches if f"-AuditorExplorationTask={task['id']}" in v.get("extra_args", [])]
    if exact:
        matches = exact
    elif any(any(a.startswith("-AuditorExplorationTask=") for a in v.get("extra_args", [])) for v in matches):
        raise RuntimeError("No exploration profile for the assigned task")
    if not matches:
        raise RuntimeError("No matching immutable build profile")
    if any(v != matches[0] for v in matches[1:]):
        raise RuntimeError("Ambiguous immutable build profile")
    return matches[0]


def review_headroom_limit(total_mb, slots, maximum_slot_mb):
    # Reserve every human slot at its worst-case allocation, plus 1 GiB for
    # driver/system use. The scheduler budget is not the physical GPU capacity.
    return total_mb - slots * maximum_slot_mb - 1024


class IdleReviewGPU:
    """Temporary maintenance fence for an otherwise free Review GPU.

    The existing scheduler counts a quarantined slot as the whole GPU budget.
    Its transactional DB therefore prevents new admissions on that GPU without
    restarting the service or touching any live lease. Only our sentinel is
    restored; another GPU remains available to human Review users.
    """
    def __init__(self, database, slot_gpus, gpu, journal):
        self.database = database
        self.slots = [i for i, g in enumerate(slot_gpus) if g == gpu]
        self.journal = Path(journal)
        self.owner = "native-agent-exclusive:" + uuid.uuid4().hex
        self.saved = None
        if not self.slots or len(set(slot_gpus)) < 2:
            raise RuntimeError("Exclusive mode must leave another Review GPU available")

    def acquire(self):
        with sqlite3.connect(self.database, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            rows = [dict(r) for r in db.execute("SELECT * FROM slots")]
            if any(str(r.get("last_owner") or "").startswith("native-agent-exclusive:") for r in rows):
                raise RuntimeError("Another Review GPU already has a private maintenance reservation")
            chosen = [r for r in rows if r["id"] in self.slots]
            if len(chosen) != len(self.slots) or any(r["state"] != "free" or r["task"] or r["lease"] for r in chosen):
                raise RuntimeError("Review GPU has an active/warm/reserved slot; no human session may be interrupted")
            if db.execute("SELECT 1 FROM requests WHERE state='waiting' LIMIT 1").fetchone():
                raise RuntimeError("Human requests are waiting; private exclusive admission deferred")
            placeholders = ",".join("?" for _ in self.slots)
            if db.execute(f"SELECT 1 FROM commands WHERE state='pending' AND slot IN ({placeholders})", self.slots).fetchone():
                raise RuntimeError("Review GPU has pending runtime commands")
            saved = chosen[0]
            # Write recovery information before committing the maintenance fence.
            self.journal.write_text(json.dumps({"pid": os.getpid(), "owner": self.owner,
                "database": str(self.database), "saved_slot": saved, "status": "acquiring"}, indent=2))
            self.saved = saved
            atexit.register(self.release)
            db.execute("UPDATE slots SET state='quarantined',last_owner=? WHERE id=?", (self.owner, saved["id"]))

    def owned(self):
        if self.saved is None:
            return False
        with sqlite3.connect(self.database, timeout=5) as db:
            return db.execute("SELECT 1 FROM slots WHERE id=? AND state='quarantined' AND last_owner=? AND task IS NULL AND lease IS NULL",
                              (self.saved["id"], self.owner)).fetchone() is not None

    def release(self):
        if self.saved is None:
            return
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("UPDATE slots SET state=?,last_owner=? WHERE id=? AND state='quarantined' AND last_owner=? AND task IS NULL AND lease IS NULL",
                (self.saved["state"], self.saved["last_owner"], self.saved["id"], self.owner)).rowcount
        data = json.loads(self.journal.read_text())
        data.update(status="released" if count else "ownership_changed", released_at=time.time())
        self.journal.write_text(json.dumps(data, indent=2))
        self.saved = None


class PinnedBackend(UnrealBackend):
    def __init__(self, binary, map_name, task, arguments, game_env, state_root):
        self.map_name, self.task = map_name, task
        self.consumed = False
        self.root = Path(tempfile.mkdtemp(prefix="episode-", dir=state_root))
        self.log = (self.root / "unreal.log").open("wb")
        self.process = subprocess.Popen([
            binary, map_name + "?Task=" + task, "-RenderOffscreen", "-windowed",
            "-ResX=960", "-ResY=540", "-unattended", "-nosound", "-AuditorServe",
            "-AuditorIPC=" + str(self.root), "-abslog=" + str(self.root / "native.log"),
            "-forcelogflush", *arguments,
        ], stdout=self.log, stderr=subprocess.STDOUT, env={**os.environ, **game_env}, start_new_session=True)

    def exchange(self, action, **fields):
        if action != "reset":
            return super().exchange(action, **fields)
        if self.consumed:
            raise APIError(409, "Start a fresh private server for each model episode")
        if fields != {"map": self.map_name, "task": self.task, "seed": 0}:
            raise APIError(400, "Pinned task supports only its assigned task and seed slot 0")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if not self.alive():
                raise APIError(503, "Unreal exited during startup")
            try:
                state = json.loads((self.root / "response.json").read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                state = {}
            if state.get("result") == "ready":
                if not state.get("paused") or state.get("task_id") != self.task:
                    raise APIError(503, "Initial observation does not match the assigned task")
                if state.get("map") != self.map_name.rsplit("/", 1)[1]:
                    raise APIError(503, "Initial map does not match")
                log = self.root / "native.log"
                if log.exists() and f"AUDITOR_TASK_READY id={self.task} " in log.read_text(errors="replace"):
                    self.consumed = True
                    return state
            if state.get("result") in {"capture_failed", "capture_timeout", "not_ready"}:
                raise APIError(503, "Native screenshot capture failed")
            time.sleep(.1)
        raise APIError(504, "Native observation startup timed out")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--production", type=Path, default=Path.home() / "unreal-production")
    p.add_argument("--task", required=True)
    p.add_argument("--port", type=int, default=49100)
    p.add_argument("--gpu", type=int, default=2)
    p.add_argument("--state-root", type=Path, required=True)
    p.add_argument("--gpu-slot", type=int, default=0)
    p.add_argument("--gpu-slots", type=int, choices=[1, 2], default=1)
    p.add_argument("--review-headroom", action="store_true")
    p.add_argument("--review-exclusive-idle", action="store_true", help="Fence one wholly idle Review GPU; leave the other GPU available")
    a = p.parse_args()
    def stop(*unused):
        raise KeyboardInterrupt
    for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]:
        signal.signal(sig, stop)
    if a.review_headroom and a.review_exclusive_idle:
        raise SystemExit("Choose either headroom or exclusive Review allocation")
    if not 0 <= a.gpu_slot < a.gpu_slots:
        raise SystemExit("Invalid GPU slot")
    runtime = json.loads((a.production / "audit/runtime.json").read_text())
    shared = json.loads((a.production / "shared/runtime-prod.json").read_text())
    reserved = set(shared.get("allowed_gpus", shared.get("slot_gpus", []))) | set(runtime.get("allowed_gpus", runtime.get("slot_gpus", [])))
    headroom_mb = None
    exclusive = None
    if a.review_headroom or a.review_exclusive_idle:
        if a.gpu_slots != 1 or a.gpu not in runtime.get("slot_gpus", []) or a.gpu in shared.get("slot_gpus", []):
            raise SystemExit("Headroom mode requires one private episode on a Review-only GPU")
        scheduler = json.loads(Path(runtime["scheduler_config"]).read_text())
        if not any(d["index"] == a.gpu for d in scheduler["limits"]["gpu_devices"]):
            raise SystemExit("Review GPU is absent from the scheduler device inventory")
        maximum = max(t["memory_mb"] for t in scheduler["tasks"] if t["kind"] == "unreal")
        total_mb = int(subprocess.check_output([
            "nvidia-smi", f"--id={a.gpu}", "--query-gpu=memory.total", "--format=csv,noheader,nounits"], text=True).strip())
        headroom_mb = min(maximum, total_mb - 1536) if a.review_exclusive_idle else review_headroom_limit(total_mb, runtime["slot_gpus"].count(a.gpu), maximum)
        if headroom_mb < 3000:
            raise SystemExit("Insufficient memory beyond every production slot reservation")
    elif a.gpu in reserved:
        raise SystemExit("Chosen GPU belongs to production; choose a spare GPU")
    # Check the port before launching a game, and serialize ownership of our spare GPU.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", a.port))
    a.state_root.mkdir(parents=True, exist_ok=True)
    import fcntl
    gpu_lock = (a.state_root / f"gpu-{a.gpu}.lock").open("a")
    # An exclusive old-style owner blocks sharing; each new slot also has its own lease.
    fcntl.flock(gpu_lock, (fcntl.LOCK_EX if a.gpu_slots == 1 else fcntl.LOCK_SH) | fcntl.LOCK_NB)
    admission = (a.state_root / f"gpu-{a.gpu}-admission.lock").open("a")
    fcntl.flock(admission, fcntl.LOCK_EX)
    slot_lock = (a.state_root / f"gpu-{a.gpu}-slot-{a.gpu_slot}.lock").open("a")
    fcntl.flock(slot_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if a.review_exclusive_idle:
        exclusive = IdleReviewGPU(scheduler["database"], runtime["slot_gpus"], a.gpu,
                                  a.state_root / f"exclusive-gpu-{a.gpu}-{os.getpid()}.json")
        exclusive.acquire()
    sibling_active = False
    if a.gpu_slots == 2:
        with (a.state_root / f"gpu-{a.gpu}-slot-{1 - a.gpu_slot}.lock").open("a") as sibling:
            try:
                fcntl.flock(sibling, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sibling_active = True
    rows = subprocess.check_output(["nvidia-smi", f"--id={a.gpu}", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], text=True)
    used, total = map(int, rows.strip().split(","))
    if used > 128 and not sibling_active and (headroom_mb is None or a.review_exclusive_idle):
        raise SystemExit("Chosen GPU is already busy outside this runner")
    if total - used < 6144:
        raise SystemExit("GPU has less than 6 GiB free for another private episode")
    tasks = json.loads((a.production / "audit/tasks.json").read_text())["tasks"]
    task = next((t for t in tasks if t["id"] == a.task), None)
    if task is None or "?Task=" not in task["map"]:
        raise SystemExit("Expected an existing Unreal bug task with a native ?Task= map")
    map_name, native_task = task["map"].split("?Task=", 1)
    if native_task != a.task:
        raise SystemExit("Public/native task IDs differ; resolve explicitly before running")
    profile = select_profile(runtime, task, map_name)
    binary = Path(profile["binary"])
    checksum = hashlib.sha256()
    with binary.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    digest = checksum.hexdigest()
    if digest != task["build_sha256"]:
        raise SystemExit("Binary hash differs from catalog")
    arguments = [x for x in profile.get("game_args", []) + profile.get("extra_args", [])
                 if not x.lower().startswith(("-pixelstreaming", "-graphicsadapter", "-auditoripc", "-abslog"))]
    arguments.append(f"-graphicsadapter={a.gpu}")
    policy_paths = [x.split("=", 1)[1] for x in arguments if x.startswith("-AuditorExplorationPolicy=")]
    policy_sha256 = hashlib.sha256(Path(policy_paths[0]).read_bytes()).hexdigest() if policy_paths else None
    game_env = {k: v for k, v in runtime.get("game_env", {}).items() if k in {"VK_ICD_FILENAMES"}}
    game_env["XDG_CACHE_HOME"] = str(a.state_root / "cache")
    backend = PinnedBackend(str(binary), map_name, a.task, arguments, game_env, a.state_root)
    guard_stop = threading.Event()
    if headroom_mb is not None:
        def guard():
            while not guard_stop.wait(1):
                try:
                    if exclusive is not None and not exclusive.owned():
                        raise RuntimeError("Private GPU maintenance ownership changed")
                    data = subprocess.check_output(["nvidia-smi", "-q", "-x", "-i", str(a.gpu)], text=True, timeout=5)
                    rows = ET.fromstring(data).findall(".//process_info")
                    own = [r for r in rows if r.findtext("pid") == str(backend.process.pid)]
                    if not own and (backend.root / "response.json").exists() and backend.alive():
                        raise RuntimeError("Cannot verify private GPU memory after initial capture")
                    memory = sum(int(r.findtext("used_memory").split()[0]) for r in own)
                    if memory > headroom_mb:
                        raise RuntimeError("Private episode exceeded reserved Review headroom")
                except Exception as exc:
                    (backend.root / "memory-guard-error.txt").write_text(str(exc))
                    backend.close()
                    return
        threading.Thread(target=guard, daemon=True).start()
    admission.close()
    class IdentifiedEnvironment(Environment):
        def health(self):
            return {**super().health(), "task_id": a.task, "build_sha256": digest,
                    "policy_sha256": policy_sha256,
                    "sampling_interval_seconds": 0.5, "startup_rng_seeded": False}
    env = IdentifiedEnvironment(backend, {"regions": [{"id": "scene", "map": map_name}]},
                                {"tasks": [{"id": a.task, "region": "scene"}]})
    (backend.root / "launch.json").write_text(json.dumps({"task": a.task, "build_sha256": digest,
                                                          "map": map_name, "gpu": a.gpu,
                                                          "runtime_config": str(a.production / "audit/runtime.json"),
                                                          "review_revision": task.get("exploration_revision"),
                                                          "policy_sha256": policy_sha256,
                                                          "private_memory_limit_mb": headroom_mb,
                                                          "exclusive_review_gpu": bool(exclusive),
                                                          "seed_slot": 0, "startup_rng_seeded": False}, indent=2))
    def stop(*unused):
        raise KeyboardInterrupt
    for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]:
        signal.signal(sig, stop)
    print(json.dumps({"environment_url": f"http://127.0.0.1:{a.port}", "task": a.task,
                      "state": str(backend.root), "gpu": a.gpu}), flush=True)
    try:
        serve(env, a.port)
    except KeyboardInterrupt:
        pass
    finally:
        guard_stop.set()
        backend.close()
        if exclusive is not None:
            exclusive.release()
        slot_lock.close()
        gpu_lock.close()


if __name__ == "__main__":
    main()
