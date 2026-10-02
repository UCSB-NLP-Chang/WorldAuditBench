"""Episode runner: single episode + parallel batches (episode-level, one Chrome per worker).

Single:
  python -m agent.vla.runner --task ring_visible --steps 40 --proprio 1 --seed 0
Batch (model x task x proprio x seeds grid):
  python -m agent.vla.runner --grid ring_visible,ring_search --episodes 10 \
      --proprio 0,1 --parallel 6 --tag s1-qwen8b
Output: runs/<tag or timestamp>/<task>-p<proprio>-s<seed>/
"""
import argparse
import base64
import json
import math
import os
import time
import traceback
from pathlib import Path

from agent.vla.bridge import Bridge
from agent.vla.tasks import TASKS
from agent.vla.vlm import VLMClient
from agent.vla.policies import vlm_policy

REPO = Path(__file__).resolve().parents[2]


def _save_frame(run_dir, name, dataurl, caption):
    (run_dir / name).write_bytes(base64.b64decode(dataurl.split(",", 1)[1]))
    with open(run_dir / "frames.jsonl", "a") as f:
        f.write(json.dumps({"file": name, "caption": caption}, ensure_ascii=False) + "\n")


def _dist(pos, tgt):
    return math.hypot(pos[0] - tgt[0], pos[2] - tgt[2])


def run_episode(task_name, run_dir, model=None, base_url=None, proprio=1, seed=0,
                steps=None, gpu="gl-egl", temperature=0.4, video=True,
                obs="single", blocked_hint=1, film_dt=0.5, film_max=8):
    task = TASKS[task_name]
    steps = steps or task["steps"]
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "frames.jsonl").write_text("")
    traj = open(run_dir / "trajectory.jsonl", "w")
    client = VLMClient(base_url=base_url, model=model, temperature=temperature)

    meta = dict(task=task_name, config=task["config"], model=client.model, proprio=proprio,
                seed=seed, steps_budget=steps, gpu=gpu, temperature=temperature,
                obs=obs, blocked_hint=blocked_hint, film_dt=film_dt, film_max=film_max,
                started=time.strftime("%F %T"), success=False, false_done=False)

    kind = task.get("kind", "nav")
    system = vlm_policy.AUDIT_SYSTEM if kind == "audit" else vlm_policy.SYSTEM
    with Bridge(gpu=gpu) as br:
        env_meta = br.open_env(task["config"], seed=seed,
                               extra={"obs": "film", "filmDt": film_dt, "filmMax": film_max} if obs == "film" else None)
        meta.update(renderer=env_meta["renderer"], load_time_s=env_meta["load_time_s"],
                    kind=kind)
        targets = br.targets()
        tgt = targets.get(task.get("target") or task.get("zone"))
        checkpoints = list(task.get("checkpoints", []))
        cp_idx = 0

        res = br.act({"action": "wait", "ms": 300})
        # ladder L3 soft fence: zone center = actual start position (bug within inspect_r)
        zone_c = list(res["pos"]) if task.get("inspect_r") else None
        log = [dict(step=0, action_str="(start)", result_txt="episode start",
                    dataurl=res["frames"][-1], reply=None)]
        _save_frame(run_dir, "f000.jpg", res["frames"][-1], ["step 0 | start"])

        n_steps = 0
        for step in range(1, steps + 1):
            n_steps = step
            reply = client.chat(vlm_policy.build_messages(task["instr"], log, proprio, system, obs))
            action, err = vlm_policy.parse_action(reply["text"])
            if err:
                action = {"action": "turn", "deg": 45}
            log[-1]["reply"] = reply["text"]

            if action["action"] == "done":
                d = _dist(res["pos"], tgt) if tgt else None
                if kind == "audit":
                    meta["done_by_model"] = True
                else:
                    ok = d < task["radius"] and cp_idx >= len(checkpoints)
                    meta["success"] = ok
                    meta["false_done"] = not ok
                    meta["final_dist"] = round(d, 2)
                traj.write(json.dumps(dict(step=step, action=action, pos=res["pos"],
                                           dist=round(d, 2) if d is not None else None,
                                           success=meta["success"],
                                           latency_s=reply["latency_s"],
                                           usage=reply.get("usage"), reply=reply["text"]),
                                      ensure_ascii=False) + "\n")
                break

            res = br.act(action)
            d = _dist(res["pos"], tgt) if tgt else None
            notes = []
            if zone_c is not None:
                over = _dist(res["pos"], zone_c) - task["inspect_r"]
                if over > 0:
                    notes.append(f"you are {over:.1f}m OUTSIDE the inspection zone - go back")
            if cp_idx < len(checkpoints):
                cp_name, cp_r = checkpoints[cp_idx]
                if _dist(res["pos"], targets[cp_name]) < cp_r:
                    cp_idx += 1
                    if proprio:
                        notes.append(f"checkpoint reached: {cp_name}")
            cmd_dist = min(action.get("dist", 1.5) or 4, 4)
            if kind == "audit":
                # with distance-targeted movement, any significant shortfall is a real obstruction (partial stops must surface to audits too)
                blocked = (action["action"] in ("forward", "back")
                           and (cmd_dist - res["moved"]) > max(0.25, 0.1 * cmd_dist)
                           and not res["teleported"])
            else:
                # S1 keeps the prototype rule for cross-model comparability
                blocked = action["action"] == "forward" and res["moved"] < 0.3 * cmd_dist
            rtxt = vlm_policy.result_text(res, action, proprio, notes,
                                          blocked=blocked and bool(blocked_hint))
            dtxt = f"dist_to_target {d:.1f} | " if d is not None else ""
            for i, f in enumerate(res.get("film") or []):
                _save_frame(run_dir, f"f{step:03d}_film{i}.jpg", f["url"],
                            [f"step {step} film t=+{f['t']}s | {json.dumps(action, ensure_ascii=False)}"])
            for i, f in enumerate(res["frames"]):
                _save_frame(run_dir, f"f{step:03d}_{i}.jpg", f,
                            [f"step {step} | {json.dumps(action, ensure_ascii=False)} | moved {res['moved']}"
                             + (" | BLOCKED" if blocked else ""),
                             f"{dtxt}yaw {res['yaw']} | pos ({res['pos'][0]:.1f},{res['pos'][2]:.1f})",
                             (log[-1]["reply"] or "")[:120].replace("\n", " ") if log[-1].get("reply") else ""])
            traj.write(json.dumps(dict(step=step, action=action, pos=res["pos"], yaw=res["yaw"],
                                       moved=res["moved"], blocked=blocked,
                                       teleported=res["teleported"], respawned=res["respawned"],
                                       dist=round(d, 2) if d is not None else None,
                                       latency_s=reply["latency_s"],
                                       usage=reply.get("usage"), reply=reply["text"]),
                                  ensure_ascii=False) + "\n")
            traj.flush()
            log.append(dict(step=step, action_str=json.dumps(action), result_txt=rtxt,
                            dataurl=res["frames"][-1], film=res.get("film") or None, reply=None))

            if kind == "nav" and cp_idx >= len(checkpoints) and d is not None and d < task["radius"]:
                meta["success"] = True
                meta["final_dist"] = round(d, 2)
                break

        if tgt:
            meta.setdefault("final_dist", round(_dist(res["pos"], tgt), 2))
        if kind == "audit":
            meta["flags"] = br.flags()
            meta["success"] = None          # audit outcomes are judged by judge/report_tc via flags vs answers
        meta["steps_used"] = n_steps
        meta["checkpoints_hit"] = cp_idx
        meta["ended"] = time.strftime("%F %T")
        meta["vlm_usage"] = client.total_usage
        meta["page_errors"] = br.page_errors
        meta["console_errors"] = br.console_errors()[:20]

    traj.close()
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    if video:
        try:
            from judge.video import make_video
            make_video(run_dir)
        except Exception:
            traceback.print_exc()
    return meta


def _worker(spec):
    try:
        m = run_episode(**spec)
        return dict(run_dir=str(spec["run_dir"]), success=m["success"],
                    steps=m["steps_used"], final_dist=m.get("final_dist"))
    except Exception as e:
        traceback.print_exc()
        return dict(run_dir=str(spec["run_dir"]), error=str(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", help="single-episode mode: task name")
    ap.add_argument("--grid", help="batch mode: comma-separated task names")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--proprio", default="1", help="0 / 1 / 0,1")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int)
    ap.add_argument("--model")
    ap.add_argument("--base-url")
    ap.add_argument("--gpu", default="gl-egl", choices=["vulkan", "gl-egl", "swiftshader"])
    ap.add_argument("--obs", default="single", choices=["single", "film"])
    ap.add_argument("--film-dt", type=float, default=0.5,
                    help="film strip sim-time frame interval (2 fps default; Qwen-VL video "
                         "convention, within the 1-5 fps range of VideoGameQA-Bench/TempGlitch)")
    ap.add_argument("--film-max", type=int, default=8,
                    help="film strip: max frames per action (default 8; raise it with a shorter --film-dt "
                         "to keep the covered time window)")
    ap.add_argument("--blocked-hint", type=int, default=1, choices=[0, 1])
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--tag")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="grid mode: skip episodes whose run dir already holds a finished meta.json")
    args = ap.parse_args()

    stamp = args.tag or time.strftime("%m%d-%H%M%S")
    base = REPO / "runs" / stamp

    if args.task:
        rd = base / f"{args.task}-p{args.proprio}-s{args.seed}"
        meta = run_episode(args.task, rd, model=args.model, base_url=args.base_url,
                           proprio=int(args.proprio), seed=args.seed, steps=args.steps,
                           gpu=args.gpu, temperature=args.temperature, video=not args.no_video,
                           obs=args.obs, blocked_hint=args.blocked_hint, film_dt=args.film_dt,
                           film_max=args.film_max)
        print(json.dumps({k: meta[k] for k in
                          ("task", "model", "success", "false_done", "steps_used", "final_dist")},
                         ensure_ascii=False))
        print(f"output: {rd}")
        return

    if args.grid:
        specs = []
        for task in args.grid.split(","):
            for pp in args.proprio.split(","):
                for seed in range(args.episodes):
                    specs.append(dict(
                        task_name=task, run_dir=base / f"{task}-p{pp}-s{seed}",
                        model=args.model, base_url=args.base_url, proprio=int(pp),
                        seed=seed, steps=args.steps, gpu=args.gpu,
                        temperature=args.temperature, video=not args.no_video,
                        obs=args.obs, blocked_hint=args.blocked_hint, film_dt=args.film_dt,
                        film_max=args.film_max))
        if args.resume:
            def _done(rd):
                m = rd / "meta.json"
                return m.exists() and '"ended"' in m.read_text()
            n0 = len(specs)
            specs = [s for s in specs if not _done(s["run_dir"])]
            print(f"resume: {n0 - len(specs)} finished episodes skipped")
        print(f"{len(specs)} episodes, parallel={args.parallel} -> {base}")
        from multiprocessing import get_context
        with get_context("spawn").Pool(args.parallel) as pool:
            for r in pool.imap_unordered(_worker, specs):
                print(json.dumps(r, ensure_ascii=False))
        from judge.metrics import aggregate, format_table
        rows = aggregate(sorted(base.glob("*/")))
        (base / "summary.md").write_text(format_table(rows) + "\n")
        print("\n" + format_table(rows))
        return

    ap.error("one of --task / --grid is required")


if __name__ == "__main__":
    main()
