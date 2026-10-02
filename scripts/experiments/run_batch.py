#!/usr/bin/env python3
"""Run a reviewed task selection on isolated GPU/SSH slots, one native client per task."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import queue
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "agent/vlm/native"


def stop(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=25)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--batch", type=Path, required=True)
    p.add_argument("--key-file", type=Path, required=True)
    p.add_argument("--resume", action="store_true", help="Run only tasks with no previous attempt directory; never replay a started episode")
    p.add_argument("--hold-exceptions", action="store_true", help="Leave zero-shot exception tasks unstarted")
    p.add_argument("--hold-task", action="append", default=[], help="Defer a task whose backend has not passed preflight")
    args = p.parse_args()
    base = args.batch.resolve()
    selection = json.loads((base / "selection.json").read_text())
    if not args.key_file.read_text().strip():
        raise SystemExit("Missing Gemini API credential")
    batch_lock = (base / "batch.lock").open("a")
    fcntl.flock(batch_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (base / "batch.started").exists() and not args.resume:
        raise SystemExit("Batch already started; --resume skips every previously attempted task")
    ids = [t["id"] for t in selection["tasks"]]
    if len(ids) != len(set(ids)) or set(ids) & set(selection.get("excluded_task_ids", [])):
        raise SystemExit("Duplicate or explicitly excluded task in selection")
    (base / "batch.started").write_text(str(os.getpid()))
    price_snapshot = base / "pricing.json"
    if not price_snapshot.exists():
        price_snapshot.write_text((SCRIPTS / "pricing.json").read_text())
    lock = threading.Lock()
    progress_path = base / "progress.json"
    state = json.loads(progress_path.read_text())["tasks"] if progress_path.exists() else {}
    pending = queue.Queue()
    for index, task in enumerate(selection["tasks"]):
        tid = task["id"]
        state.setdefault(tid, {"status": "queued", "subcategory": task["subcategory"]})
        if (base / tid).exists():
            if state[tid]["status"] not in {"completed", "failed"}:
                state[tid].update(status="interrupted", error="Existing attempt preserved; not replayed")
            continue
        if args.hold_exceptions and task.get("protocol_group") == "zero-shot-exception":
            state[tid]["status"] = "held_protocol_exception"
            continue
        if tid in args.hold_task:
            state[tid].update(status="held_backend", error="Backend compatibility pending; no model call or episode started")
            continue
        pending.put((index, task))
    stopped = threading.Event()
    def update(task, **values):
        with lock:
            state[task].update(values)
            temp = base / "progress.json.tmp"
            temp.write_text(json.dumps({"updated_at": time.time(), "tasks": state}, indent=2) + "\n")
            temp.replace(base / "progress.json")
            print(task, values, flush=True)

    progress_path.write_text(json.dumps({"updated_at": time.time(), "tasks": state}, indent=2) + "\n")

    def worker(slot):
        gpu = selection["gpus"][slot]
        gpu_slot = selection["gpus"][:slot].count(gpu)
        gpu_slots = selection["gpus"].count(gpu)
        while not stopped.is_set():
            try:
                index, task = pending.get_nowait()
            except queue.Empty:
                break
            local_port = selection.get("local_port_base", 19220) + index
            remote_port = selection.get("remote_port_base", 49220) + index
            if stopped.is_set():
                break
            tid = task["id"]
            job = base / tid
            job.mkdir()
            server = model = None
            started = time.time()
            try:
                update(tid, status="starting_environment", gpu=gpu, started_at=started)
                with (job / "environment.log").open("w") as environment_log, (job / "launcher.log").open("w") as model_log:
                    environment = task.get("environment", "unreal-http")
                    url = None
                    if environment == "unreal-http":
                        server = subprocess.Popen([
                            sys.executable, str(SCRIPTS / "connect_unreal.py"), "--task", tid,
                            "--gpu", str(gpu), "--gpu-slot", str(gpu_slot), "--gpu-slots", str(gpu_slots), "--local-port", str(local_port), "--remote-port", str(remote_port)
                        ], cwd=ROOT, stdout=environment_log, stderr=subprocess.STDOUT, start_new_session=True)
                        deadline = time.monotonic() + 180
                        url = f"http://127.0.0.1:{local_port}"
                        while time.monotonic() < deadline:
                            if server.poll() is not None:
                                raise RuntimeError("Environment process exited; inspect environment.log")
                            try:
                                with urllib.request.urlopen(url + "/health", timeout=2) as response:
                                    health = json.load(response)
                                if health.get("engine_alive") and health.get("task_id") == tid:
                                    if health.get("build_sha256") != task["build_sha256"]:
                                        raise RuntimeError("Deployed build changed since selection")
                                    break
                            except OSError:
                                pass
                            if stopped.wait(.5):
                                raise RuntimeError("Batch interrupted")
                        else:
                            raise RuntimeError("Environment health timed out")
                        update(tid, status="running", environment_ready_at=time.time())
                    else:
                        update(tid, status="running", environment_ready_at=time.time(), renderer_host="local")
                    instruction = (
                        "Inspect the assigned 3D environment for anomalies. Explore and gather visual evidence. "
                        "Report each distinct anomaly with a clear description and evidence frame references. "
                        f"Use the full {selection['max_actions']}-action budget for "
                        "exploration and verification, even after finding an initial anomaly. Finish earlier "
                        "only if the environment fails."
                    )
                    command = [sys.executable, str(SCRIPTS / "launch.py"), "gemini",
                               "--environment", environment, "--task", tid,
                               "--task-catalog", str(base / "task-subcategories.json"),
                               "--model", selection["model"], "--gemini-thinking", selection["thinking_level"],
                               "--max-actions", str(selection["max_actions"]), "--observation", "on-demand",
                               "--gemini-auth", "gemini-api-key", "--gemini-api-key-file", str(args.key_file.resolve()),
                               "--run-dir", str(job / "run"), "--instruction", instruction, "--require-full-budget"]
                    if environment == "unreal-http":
                        command += ["--env-url", url]
                    else:
                        browser = {"browser_root": str(ROOT / "out/native-agents/browser-release"),
                                   "browser_page": task["map"].split("?")[0].rsplit("/", 1)[-1],
                                   "browser_case": task["source_case"], "page_sha256": task["page_sha256"]}
                        cfg_path = job / "browser-config.json"
                        cfg_path.write_text(json.dumps(browser, indent=2) + "\n")
                        command += ["--browser-config", str(cfg_path), "--seed", "5"]
                    if task.get("protocol_group") == "zero-shot-exception":
                        command += ["--no-icl"]
                    model_started = time.time()
                    update(tid, model_started_at=model_started, worker_slot=slot)
                    model = subprocess.Popen(command, cwd=ROOT, stdout=model_log, stderr=subprocess.STDOUT,
                                             start_new_session=True)
                    deadline = time.monotonic() + 3600
                    while model.poll() is None:
                        if stopped.wait(1) or time.monotonic() > deadline:
                            raise RuntimeError("Native run interrupted or timed out")
                    update(tid, model_finished_at=time.time())
                    manifest = json.loads((job / "run/launch.json").read_text())
                    meta_path = job / "run/episode/meta.json"
                    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
                    update(tid, status=manifest["status"], native_exit_code=model.returncode,
                           actions_used=meta.get("actions_used", 0), flags=meta.get("flags", []),
                           elapsed_seconds=round(time.time() - started, 2))
            except Exception as exc:
                update(tid, status="failed", error=str(exc), elapsed_seconds=round(time.time() - started, 2))
            finally:
                stop(model)
                stop(server)
                update(tid, cleaned_up_at=time.time())
                # Serialize report writes; every finished task gets durable timing/cost.
                with lock:
                    subprocess.run([sys.executable, str(ROOT / "scripts/experiments/summarize_batch.py"), str(base)],
                                   cwd=ROOT, check=False)

    def interrupt(*unused):
        stopped.set()
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    with ThreadPoolExecutor(max_workers=len(selection["gpus"])) as pool:
        list(pool.map(worker, range(len(selection["gpus"]))))
    print("Batch finished. Results:", base / "progress.json", flush=True)


if __name__ == "__main__":
    main()
