"""Top-down trajectory plot: x-z path + targets (with success radius) + key-event annotations.

Usage (library): plot_episode(run_dir, targets, out_png, annotations=[(step, text), ...])
Usage (CLI): python -m judge.plot_traj runs/xxx/episode-dir
"""
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

RING_COLORS = {"ring_cyan": "#20b8d8", "ring_purple": "#a05ce0", "ring_orange": "#e08a20",
               "ring_end": "#20b8d8"}


def plot_episode(run_dir, targets, out_png=None, radius=3.0, annotations=(), title=None):
    run_dir = Path(run_dir)
    rows = [json.loads(l) for l in (run_dir / "trajectory.jsonl").read_text().splitlines() if l.strip()]
    xs, zs, steps = [], [], []
    for r in rows:
        if r.get("pos"):
            xs.append(r["pos"][0]); zs.append(r["pos"][2]); steps.append(r["step"])

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(xs, zs, "-", color="#456", lw=1.2, alpha=.8, zorder=2)
    ax.scatter(xs, zs, s=14, c=range(len(xs)), cmap="viridis", zorder=3)
    if xs:
        ax.scatter([xs[0]], [zs[0]], marker="^", s=130, c="#2a7", zorder=4, label="start")
        ax.scatter([xs[-1]], [zs[-1]], marker="s", s=110, c="#d33", zorder=4, label="end")
    for name, p in (targets or {}).items():
        c = RING_COLORS.get(name, "#888")
        ax.scatter([p[0]], [p[2]], marker="o", s=90, c=c, zorder=4)
        ax.add_patch(plt.Circle((p[0], p[2]), radius, fill=False, ls="--", color=c, alpha=.6))
        ax.annotate(name, (p[0], p[2]), textcoords="offset points", xytext=(6, 6), color=c)
    for i in range(0, len(steps), 5):
        ax.annotate(str(steps[i]), (xs[i], zs[i]), textcoords="offset points",
                    xytext=(3, 3), fontsize=7, color="#333")
    by_step = {s: (x, z) for s, x, z in zip(steps, xs, zs)}
    for step, text in annotations:
        if step in by_step:
            ax.annotate(text, by_step[step], textcoords="offset points", xytext=(10, -12),
                        fontsize=8, color="#b00",
                        arrowprops=dict(arrowstyle="->", color="#b00", lw=.8))
    ax.set_aspect("equal")
    ax.grid(alpha=.25)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    ax.set_title(title or run_dir.name)
    ax.legend(loc="best", fontsize=8)
    out_png = out_png or (run_dir / "trajectory.png")
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    plt.close(fig)
    return out_png


if __name__ == "__main__":
    rd = Path(sys.argv[1])
    meta = json.loads((rd / "meta.json").read_text())
    # targets are runtime-resolved and unavailable from config alone; CLI mode omits target markers
    print(plot_episode(rd, {}, title=f"{meta['task']} seed={meta['seed']} success={meta['success']}"))
