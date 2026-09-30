"""S2 targeted-audit report: detection rate vs control false-alarm rate, localization error.

Usage: python -m eval.report_s2 runs/s2-8b [--radius 3.0]
Scoring: bug episode hit = some flag lands within radius of the zone's bug;
         clean episode false alarm = any flag at all.
Gate (PLAN 2.3): air-wall detection significantly above control false-alarm rate (one-sided Fisher).
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

ZONE_BUG = {"zone_east": "air_wall", "zone_west": "float", "zone_torch": "frozen_anim"}


def fisher_one_sided(k1, n1, k0, n0):
    """P(observing >= k1 | fixed margins) - detection k1/n1 vs control k0/n0, one-sided upper."""
    K, N = k1 + k0, n1 + n0
    if n1 == 0 or N == 0:
        return 1.0
    p = 0.0
    for k in range(k1, min(K, n1) + 1):
        p += math.comb(n1, k) * math.comb(n0, K - k) / math.comb(N, K)
    return min(1.0, p)


def collect(run_base, radius, answers_cache=None):
    run_base = Path(run_base)
    eps = []
    answers_cache = answers_cache if answers_cache is not None else {}
    for md in sorted(run_base.glob("*/meta.json")):
        meta = json.loads(md.read_text())
        if meta.get("kind") != "audit":
            continue
        cfg = meta["config"]
        if cfg not in answers_cache:
            from eval.score_flags import resolve_answers
            answers_cache[cfg] = resolve_answers(cfg)
        answers = answers_cache[cfg]
        task = meta["task"]
        zone = ("zone_torch" if "torch" in task
                else "zone_east" if "east" in task else "zone_west")
        bug_type = ZONE_BUG[zone]
        target_ans = next((a for a in answers if a.get("bug") == bug_type), None)
        flags = meta.get("flags", [])

        def dist_to(a, f):
            return math.hypot(f["pos"][0] - a["position"][0], f["pos"][2] - a["position"][2])

        detected, loc_err = False, None
        if target_ans and flags:
            ds = [dist_to(target_ans, f) for f in flags]
            loc_err = round(min(ds), 2)
            detected = min(ds) < radius
        matched_any = set()
        for fi, f in enumerate(flags):
            for a in answers:
                if dist_to(a, f) < radius:
                    matched_any.add(fi)
        eps.append(dict(
            dir=md.parent.name, model=meta.get("model", "?"), task=task, config=cfg,
            proprio=meta.get("proprio", "?"),
            zone=zone, is_bug_cfg=bool(target_ans), n_flags=len(flags),
            detected=detected, loc_err=loc_err,
            extra_flags=len(flags) - len(matched_any),
            done_by_model=meta.get("done_by_model", False),
            steps=meta.get("steps_used"),
        ))
    return eps


def report(run_base, radius=3.0):
    eps = collect(run_base, radius)
    groups = defaultdict(list)
    for e in eps:
        groups[(e["model"], e["task"], e["proprio"])].append(e)

    lines = [f"# S2 report — {run_base}  (radius={radius}m)\n",
             "| model | task | proprio | n | detection | FP-episode rate | flags/ep | loc err (m) | done rate | steps |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    stats = {}
    for (model, task, proprio), es in sorted(groups.items()):
        n = len(es)
        is_bug = es[0]["is_bug_cfg"]
        det = sum(e["detected"] for e in es)
        fp_eps = sum(1 for e in es if (e["n_flags"] > 0 and not e["is_bug_cfg"]) or e["extra_flags"] > 0)
        locs = [e["loc_err"] for e in es if e["detected"] and e["loc_err"] is not None]
        lines.append("| {} | {} | {} | {} | {} | {} | {:.1f} | {} | {:.0%} | {:.1f} |".format(
            model.split("/")[-1], task, proprio, n,
            f"{det}/{n}" if is_bug else "—",
            f"{fp_eps}/{n}",
            sum(e["n_flags"] for e in es) / n,
            f"{sum(locs) / len(locs):.2f}" if locs else "—",
            sum(e["done_by_model"] for e in es) / n,
            sum(e["steps"] or 0 for e in es) / n))
        stats[(model, task, proprio)] = dict(n=n, det=det, fp_eps=fp_eps)

    # gate: same-zone bug detection vs clean false alarms (per model)
    lines.append("\n## Gate (one-sided Fisher, detection > control false-alarm rate)\n")
    keys = sorted({(m, pp) for m, _, pp in stats})
    for model, pp in keys:
        for zone, bug_task, clean_task in [("east (air wall, L2)", "audit_east_bug", "audit_east_clean"),
                                           ("west (floating crate, L1)", "audit_west_bug", "audit_west_clean"),
                                           ("torch (frozen animation, L3)", "audit_torch_bug", "audit_torch_clean")]:
            b = stats.get((model, bug_task, pp))
            c = stats.get((model, clean_task, pp))
            if not b or not c:
                continue
            p = fisher_one_sided(b["det"], b["n"], c["fp_eps"], c["n"])
            verdict = "PASS" if p < 0.05 else "fail"
            lines.append(f"- {model.split('/')[-1]} · proprio={pp} · {zone}: detection {b['det']}/{b['n']} vs "
                         f"control FP {c['fp_eps']}/{c['n']} -> p={p:.4f} **{verdict}**")

    out = "\n".join(lines) + "\n"
    (Path(run_base) / "s2_report.md").write_text(out)
    print(out)
    (Path(run_base) / "s2_episodes.json").write_text(json.dumps(eps, indent=1, ensure_ascii=False))
    return eps


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_base")
    ap.add_argument("--radius", type=float, default=3.0)
    args = ap.parse_args()
    report(args.run_base, args.radius)
