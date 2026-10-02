"""Per-episode and aggregate metrics.

Episode input = the rows of trajectory.jsonl (dicts written by the runner) + meta.
Metrics: SR, false done, steps, path_len (teleport displacement excluded - pitfall #7),
blocked, spin (cumulative same-direction turning >360deg with <1m displacement),
revisit (2m-grid revisit ratio).
"""
import json
import math
from collections import defaultdict
from pathlib import Path


def episode_metrics(steps, meta):
    path_len = 0.0
    blocked = 0
    teleports = 0
    positions = []
    for s in steps:
        if s.get("pos"):
            positions.append(s["pos"])
        if s.get("teleported"):
            teleports += 1
        elif s.get("moved") is not None:
            path_len += s["moved"]
        if s.get("blocked"):
            blocked += 1

    # spin: cumulative same-direction turn angle >=360deg with horizontal displacement <1m
    spin_events = 0
    cum = 0.0
    sign = 0
    start_pos = None
    for s in steps:
        a = s.get("action") or {}
        if a.get("action") == "turn":
            d = a.get("deg", 45)
            sg = 1 if d > 0 else -1
            if sg != sign:
                sign, cum, start_pos = sg, 0.0, s.get("pos")
            cum += abs(d)
            if cum >= 360:
                p0, p1 = start_pos, s.get("pos")
                if p0 and p1 and math.hypot(p1[0] - p0[0], p1[2] - p0[2]) < 1.0:
                    spin_events += 1
                cum, start_pos = 0.0, s.get("pos")
        elif a.get("action") in ("forward", "back"):
            if (s.get("moved") or 0) > 0.5:
                sign, cum = 0, 0.0

    # revisit: 2m grid
    cells = [(round(p[0] / 2), round(p[2] / 2)) for p in positions]
    visits = len(cells)
    unique = len(set(cells))
    revisit_ratio = round((visits - unique) / visits, 3) if visits else 0.0

    lat = [s["latency_s"] for s in steps if s.get("latency_s") is not None]
    return dict(
        success=meta.get("success", False),
        false_done=meta.get("false_done", False),
        steps=len(steps),
        path_len=round(path_len, 1),
        blocked=blocked,
        teleports=teleports,
        spin_events=spin_events,
        revisit_ratio=revisit_ratio,
        final_dist=meta.get("final_dist"),
        mean_latency_s=round(sum(lat) / len(lat), 2) if lat else None,
    )


def load_episode(run_dir):
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text())
    steps = [json.loads(l) for l in (run_dir / "trajectory.jsonl").read_text().splitlines() if l.strip()]
    return steps, meta


def aggregate(run_dirs):
    """Aggregate by (model, task, proprio). Returns a list of rows."""
    groups = defaultdict(list)
    for rd in run_dirs:
        try:
            steps, meta = load_episode(rd)
        except FileNotFoundError:
            continue
        m = episode_metrics(steps, meta)
        m["_meta"] = meta
        groups[(meta.get("model", "?"), meta.get("task", "?"), meta.get("proprio", "?"))].append(m)

    rows = []
    for (model, task, proprio), ms in sorted(groups.items()):
        n = len(ms)
        sr = sum(1 for m in ms if m["success"]) / n
        rows.append(dict(
            model=model, task=task, proprio=proprio, n=n,
            SR=round(sr, 2),
            false_done=sum(1 for m in ms if m["false_done"]),
            steps=round(sum(m["steps"] for m in ms) / n, 1),
            path_len=round(sum(m["path_len"] for m in ms) / n, 1),
            blocked=round(sum(m["blocked"] for m in ms) / n, 1),
            spin=round(sum(m["spin_events"] for m in ms) / n, 2),
            revisit=round(sum(m["revisit_ratio"] for m in ms) / n, 2),
        ))
    return rows


def format_table(rows):
    if not rows:
        return "(no episodes)"
    cols = ["model", "task", "proprio", "n", "SR", "false_done", "steps", "path_len", "blocked", "spin", "revisit"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    out = ["  ".join(c.ljust(widths[c]) for c in cols)]
    out.append("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        out.append("  ".join(str(r[c]).ljust(widths[c]) for c in cols))
    return "\n".join(out)
