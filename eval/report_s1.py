"""S1 report: aggregate table + per-episode top-down trajectory plots + gate verdict.

Usage: python -m eval.report_s1 runs/s1-8b [--gate-task ring_visible] [--gate-sr 0.6]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from eval.metrics import aggregate, format_table, episode_metrics, load_episode
from eval.plot_traj import plot_episode


def report(run_base, gate_task="ring_visible", gate_sr=0.6, plots=True):
    run_base = Path(run_base)
    dirs = sorted(d for d in run_base.glob("*/") if (d / "meta.json").exists())
    rows = aggregate(dirs)
    table = format_table(rows)

    # per-episode detail + trajectory plots
    detail = defaultdict(list)
    for d in dirs:
        steps, meta = load_episode(d)
        m = episode_metrics(steps, meta)
        detail[(meta["task"], meta["proprio"])].append(
            dict(seed=meta["seed"], success=m["success"], false_done=m["false_done"],
                 steps=m["steps"], final_dist=m["final_dist"], dir=d.name))
        if plots and not (d / "trajectory.png").exists():
            try:
                # targets are not stored per episode and recovering them from configs is convoluted;
                # target-free plots still show behavior shape (use plot_traj manually for annotated singles)
                plot_episode(d, {}, title=f"{meta['task']} p{meta['proprio']} s{meta['seed']} "
                                          f"{'OK' if m['success'] else 'FAIL'}")
            except Exception as e:
                print(f"plot failed {d.name}: {e}")

    lines = [f"# S1 report — {run_base}\n", "```", table, "```", ""]
    for (task, proprio), es in sorted(detail.items()):
        fails = [e for e in es if not e["success"]]
        lines.append(f"## {task} - proprio={proprio}  ({sum(e['success'] for e in es)}/{len(es)})")
        if fails:
            lines.append("failures: " + ", ".join(
                f"s{e['seed']}(dist={e['final_dist']}{',false done' if e['false_done'] else ''})"
                for e in fails))
        lines.append("")

    # gate
    lines.append("## Gate verdict\n")
    for r in rows:
        if r["task"] == gate_task:
            ok = r["SR"] >= gate_sr
            lines.append(f"- {r['model'].split('/')[-1]} · {gate_task} · proprio={r['proprio']}: "
                         f"SR={r['SR']:.0%} {'≥' if ok else '<'} {gate_sr:.0%} → "
                         f"**{'PASS' if ok else 'FAIL'}**")
    out = "\n".join(lines) + "\n"
    (run_base / "s1_report.md").write_text(out)
    print(out)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_base")
    ap.add_argument("--gate-task", default="ring_visible")
    ap.add_argument("--gate-sr", type=float, default=0.6)
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()
    report(args.run_base, args.gate_task, args.gate_sr, plots=not args.no_plots)
