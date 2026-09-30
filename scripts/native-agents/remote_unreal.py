"""Run a fresh, private episode from an AWS review build; do not change production."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

from environment_server import APIError, Environment, UnrealBackend, serve


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
    a = p.parse_args()
    if not 0 <= a.gpu_slot < a.gpu_slots:
        raise SystemExit("Invalid GPU slot")
    runtime = json.loads((a.production / "shared/runtime-prod.json").read_text())
    if a.gpu in runtime.get("allowed_gpus", runtime.get("slot_gpus", [])):
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
    sibling_active = False
    if a.gpu_slots == 2:
        with (a.state_root / f"gpu-{a.gpu}-slot-{1 - a.gpu_slot}.lock").open("a") as sibling:
            try:
                fcntl.flock(sibling, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sibling_active = True
    rows = subprocess.check_output(["nvidia-smi", f"--id={a.gpu}", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], text=True)
    used, total = map(int, rows.strip().split(","))
    if used > 128 and not sibling_active:
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
    matches = [v for v in runtime["launch_profiles"].values()
               if v.get("build_sha256") == task["build_sha256"] and v.get("runtime_map") == map_name]
    if not matches:
        raise SystemExit("No matching immutable build profile")
    profile = matches[0]
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
    game_env = {k: v for k, v in runtime.get("game_env", {}).items() if k in {"VK_ICD_FILENAMES"}}
    game_env["XDG_CACHE_HOME"] = str(a.state_root / "cache")
    backend = PinnedBackend(str(binary), map_name, a.task, arguments, game_env, a.state_root)
    admission.close()
    class IdentifiedEnvironment(Environment):
        def health(self):
            return {**super().health(), "task_id": a.task, "build_sha256": digest,
                    "sampling_interval_seconds": 0.5, "startup_rng_seeded": False}
    env = IdentifiedEnvironment(backend, {"regions": [{"id": "scene", "map": map_name}]},
                                {"tasks": [{"id": a.task, "region": "scene"}]})
    (backend.root / "launch.json").write_text(json.dumps({"task": a.task, "build_sha256": digest,
                                                          "map": map_name, "gpu": a.gpu,
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
        backend.close()
        slot_lock.close()
        gpu_lock.close()


if __name__ == "__main__":
    main()
