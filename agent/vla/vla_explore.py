"""Setting 2, stage 1: a low-cost VLA game model (Open-P2P) explores the world; we record
what it saw. The recording is later audited by a strong VLM (agent/vla/replay.py).

The explorer knows nothing about bugs - it just plays. Sim time advances in fixed 50ms ticks
(20Hz), only while the explorer acts (same paused-world principle as Setting 1).

Usage:
  .venv/bin/python -m agent.vla.vla_explore --tasks JS_SP01,JS_SP02 \
      --ticks 1200 --tag vla-p2p1200
Outputs per episode: runs/<tag>/<task>/ frames (every N ticks, full res),
poses.jsonl, meta.json (incl. bug-manifestation events), video.mp4.
"""
import argparse
import base64
import io
import json
import os
import subprocess
import time
from pathlib import Path

from PIL import Image

from agent.vla.bridge import Bridge
REPO = Path(__file__).resolve().parents[2]

P2P_ROOT = os.environ.get("P2P_ROOT", "/home/ubuntu/tools/open-p2p")     # open-p2p checkout with .venv (uv sync) + checkpoints/<size>/
P2P_PY = os.environ.get("P2P_PY", f"{P2P_ROOT}/.venv/bin/python")
HF_HOME = os.environ.get("HF_HOME", "/home/ubuntu/tools/hf_cache")
KEYMAP = {  # P2P key vocabulary -> browser KeyboardEvent.code (movement subset)
    "w": "KeyW", "a": "KeyA", "s": "KeyS", "d": "KeyD",
    "Space": "Space", "LeftShift": "ShiftLeft", "RightShift": "ShiftRight",
}
USE_KEYS = {"e"}          # E = use/interact in most 3D games -> aim-ray interact
CLICK_BUTTONS = {"0"}     # left click -> aim-ray interact
MAX_MOUSE_PX = 150        # per-tick delta cap (sanity)


class P2PClient:
    def __init__(self, gpu="0", size="1200M", eager=False, host=None):
        """host=None: local server.  host="rain2": the same server started over ssh on that machine (remote inference:
        the environment stays here, frames go out as JSON lines and actions come back; ~20 ms per tick on an 11 ms link).
        The remote needs the open-p2p checkout with .venv, checkpoints/<size>/, p2p_server.py and an HF cache
        (P2P_REMOTE_ROOT, P2P_REMOTE_HF_HOME, default /mnt/data/jingbo/open-p2p and its hf_cache)."""
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu, HF_HOME=HF_HOME,
                   PATH=os.path.expanduser("~/.local/bin") + ":" + os.environ["PATH"])
        if host:
            root = os.environ.get("P2P_REMOTE_ROOT", "/mnt/data/jingbo/open-p2p")
            hf = os.environ.get("P2P_REMOTE_HF_HOME", root + "/hf_cache")
            remote = (f"cd {root} && CUDA_VISIBLE_DEVICES={gpu} HF_HOME={hf} HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 {root}/.venv/bin/python {root}/p2p_server.py "
                      f"--config {root}/config/policy_model/{size}.yaml --checkpoint {root}/checkpoints/{size}/slim-checkpoint-step-00500000.ckpt"
                      + (" --eager" if eager else ""))
            cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", host, remote]
            self.proc = subprocess.Popen(cmd, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        else:
            cmd = [P2P_PY, str(REPO / "agent/vla" / "p2p_server.py"),
                   "--config", f"{P2P_ROOT}/config/policy_model/{size}.yaml",
                   "--checkpoint", self._find_ckpt(size)]
            if eager:
                cmd.append("--eager")
            self.proc = subprocess.Popen(cmd, cwd=P2P_ROOT, env=env, text=True,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        t0 = time.time()
        for line in self.proc.stdout:
            if line.startswith("#READY"):
                print(f"p2p server ready in {time.time() - t0:.0f}s")
                return
        raise RuntimeError("p2p server failed to start")

    @staticmethod
    def _find_ckpt(size):
        cands = sorted(Path(f"{P2P_ROOT}/checkpoints/{size}").glob("*.ckpt"))
        if not cands:
            raise FileNotFoundError(f"no checkpoint under checkpoints/{size}")
        return str(cands[-1])

    def _rpc(self, obj, expect):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()
        for line in self.proc.stdout:
            if line.startswith(expect):
                return line[len(expect):].strip()
        raise RuntimeError("p2p server died")

    def act(self, jpeg_b64, text=None):
        return json.loads(self._rpc({"img": jpeg_b64, "text": text}, "#ACT "))

    def reset(self):
        self._rpc({"cmd": "reset"}, "#OK")

    def close(self):
        try:
            self.proc.stdin.write('{"cmd":"quit"}\n')
            self.proc.stdin.flush()
        except Exception:
            pass
        self.proc.terminate()


def small_jpeg(dataurl, size=(192, 192)):
    img = Image.open(io.BytesIO(base64.b64decode(dataurl.split(",", 1)[1]))).convert("RGB")
    buf = io.BytesIO()
    img.resize(size, Image.BILINEAR).save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def run_episode(br, p2p, config, seed, ticks, dt_ms, record_every, text, out_dir,
                recover=True, idle_nudge=0):
    out_dir.mkdir(parents=True, exist_ok=True)
    # vclock: standalone pages advance exactly dt_ms of simulated time per tick (device-independent); core.js pages already do
    br.open_env(config, seed=seed, extra={"vclock": 1})
    br.page.evaluate("() => window.__env.enable()")
    p2p.reset()

    poses, frame_files = [], []
    r = br.page.evaluate("(a) => window.__env.tick(a, 50)", {})
    action = {"keys": [], "buttons": [], "dx": 0, "dy": 0}
    stuck = 0
    recovery = []      # queued scripted recovery ticks (stuck-unwedge wrapper)
    n_recoveries = 0
    idle = 0; n_nudges = 0   # idle-nudge wrapper: the policy emitted no movement key and (almost) no mouse for idle_nudge ticks
    for t in range(ticks):
        if recovery:
            act, is_rec = recovery.pop(0), True
        else:
            keys = [KEYMAP[k] for k in action["keys"] if k in KEYMAP]
            click = bool(set(action["keys"]) & USE_KEYS) or bool(set(action["buttons"]) & CLICK_BUTTONS)
            dx = max(-MAX_MOUSE_PX, min(MAX_MOUSE_PX, action["dx"]))
            dy = max(-MAX_MOUSE_PX, min(MAX_MOUSE_PX, action["dy"]))
            act, is_rec = {"keys": keys, "mouseDx": dx, "mouseDy": dy, "click": click}, False
        r = br.page.evaluate("(a) => window.__env.tick(a.act, a.dt)", {"act": act, "dt": dt_ms})
        poses.append({"t": t, "pos": r["pos"], "yaw": r["yaw"], "pitch": r["pitch"],
                      "moved": r["moved"], "respawned": r["respawned"], "keys": act["keys"],
                      "dx": act.get("mouseDx", 0), "dy": act.get("mouseDy", 0),
                      "recovery": is_rec, "nudge": bool(act.get("nudge"))})
        if t % record_every == 0:
            fn = f"f{t:05d}.jpg"
            (out_dir / fn).write_bytes(base64.b64decode(r["frame"].split(",", 1)[1]))
            frame_files.append(fn)
        # stuck-recovery wrapper: 2s of held-W with no displacement -> back up + turn ~120deg,
        # then hand control back to the policy (alternating turn direction)
        if recover and not is_rec:
            stuck = stuck + 1 if ("KeyW" in act["keys"] and r["moved"] < 0.02) else 0
            if stuck >= 40:
                sgn = 1 if n_recoveries % 2 == 0 else -1
                recovery = [{"keys": ["KeyS"], "mouseDx": 0, "mouseDy": 0}] * 10 + \
                           [{"keys": [], "mouseDx": sgn * 105, "mouseDy": 0}] * 12
                n_recoveries += 1
                stuck = 0
        # idle-nudge wrapper (paused world): a policy that stops acting sees a frozen frame and can stay idle for the
        # whole episode; after idle_nudge idle ticks a scripted look-around (12 ticks, alternating side) and, every
        # second time, a short walk (10 ticks of W) hand a changed view back to the policy.  Logged like recoveries.
        if idle_nudge and not is_rec and not recovery:
            moving = bool(set(act["keys"]) & {"KeyW", "KeyS", "KeyA", "KeyD"}) or abs(act.get("mouseDx", 0)) + abs(act.get("mouseDy", 0)) >= 4
            idle = 0 if moving else idle + 1
            if idle >= idle_nudge:
                sgn = 1 if n_nudges % 2 == 0 else -1
                recovery = [{"keys": [], "mouseDx": sgn * 105, "mouseDy": 0, "nudge": True}] * 12
                if n_nudges % 2 == 1:
                    recovery += [{"keys": ["KeyW"], "mouseDx": 0, "mouseDy": 0, "nudge": True}] * 10
                n_nudges += 1; idle = 0
                p2p.reset()   # re-sample the policy's mode: an idle mode persists through view changes (its own no-op history)
        action = p2p.act(small_jpeg(r["frame"]), text)

    probe = br.probe()
    (out_dir / "poses.jsonl").write_text("\n".join(json.dumps(p) for p in poses))
    meta = dict(task=config, config=config, seed=seed, kind="vla_explore",
                model="open-p2p", ticks=ticks, dt_ms=dt_ms, record_every=record_every,
                text=text, bug_events=probe.get("bugEvents", []),
                n_recoveries=n_recoveries, n_nudges=n_nudges, idle_nudge=idle_nudge,
                sim_seconds=round(ticks * dt_ms / 1000, 1), frames=frame_files)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1))

    try:
        import imageio.v2 as imageio
        import numpy as np
        w = imageio.get_writer(out_dir / "video.mp4", fps=int(1000 / dt_ms / record_every * 2), codec="libx264",
                               quality=7, macro_block_size=None)
        for fn in frame_files:
            w.append_data(np.asarray(Image.open(out_dir / fn)))
        w.close()
    except Exception as e:
        print("video assembly failed:", e)
    n_ev = len(meta["bug_events"])
    print(f"{out_dir.name}: {ticks} ticks, {len(frame_files)} frames, {n_ev} bug events, "
          f"{n_recoveries} recoveries, {n_nudges} nudges")


def main():
    from scripts.runtime import DEFAULT_RUNTIME, ensure_environment
    from scripts.experiments.run import task_ids
    ap = argparse.ArgumentParser(description="Record Open-P2P exploration of Three.js tasks")
    ap.add_argument("--tasks", required=True, help="Comma-separated IDs or @split.txt")
    ap.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--ticks", type=int, default=1200)
    ap.add_argument("--dt-ms", type=int, default=50)
    ap.add_argument("--record-every", type=int, default=10)
    ap.add_argument("--text", default="Explore this place. Walk around and look at everything.")
    ap.add_argument("--no-text", action="store_true")
    ap.add_argument("--tag", default="vla-threejs")
    ap.add_argument("--skip-done", action="store_true")
    ap.add_argument("--size", default="1200M")
    ap.add_argument("--gpu", default="0")
    ap.add_argument("--browser-gpu", choices=["native", "gl-egl", "vulkan", "swiftshader"], default="native")
    ap.add_argument("--eager", action="store_true")
    ap.add_argument("--p2p-host", default=None)
    ap.add_argument("--idle-nudge", type=int, default=0)
    ap.add_argument("--no-recover", action="store_true")
    args = ap.parse_args()
    tasks = task_ids(args.tasks)
    if any(not t.startswith("JS_") for t in tasks):
        ap.error("Use agent.vla.vla_ue for Unreal tasks")
    runtime = args.runtime_root.expanduser().resolve()
    for task in tasks:
        ensure_environment(task, runtime, args.download)
    p2p = P2PClient(gpu=args.gpu, size=args.size, eager=args.eager, host=args.p2p_host)
    try:
        with Bridge(gpu=args.browser_gpu, serve_dir=runtime, profiles=runtime / "browser-profiles") as br:
            for task in tasks:
                out_dir = REPO / "runs" / args.tag / task
                if (out_dir / "meta.json").exists() and args.skip_done:
                    continue
                if out_dir.exists():
                    raise ValueError("Recording already exists; choose a new --tag: " + str(out_dir))
                run_episode(br, p2p, task, 5, args.ticks, args.dt_ms, args.record_every,
                            None if args.no_text else args.text, out_dir,
                            recover=not args.no_recover, idle_nudge=args.idle_nudge)
    finally:
        p2p.close()


if __name__ == "__main__":
    main()
