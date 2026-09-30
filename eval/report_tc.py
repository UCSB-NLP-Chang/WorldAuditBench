"""TC test-case matrix report: per model x case detection / false-positive rates.

Usage: python -m eval.report_tc runs/tc-<model> [runs/tc-<model2> ...] [--radius 3.0]
Episode dirs look like audit_tc01_bug-p1-s0. Answers are resolved from the bug config
(answers marked global skip distance matching - any flag counts). Any flag in a clean
episode is a false positive.
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from eval.score_flags import resolve_answers

# Semantic layer: the flag note must match the case's phenomenon keywords (case-insensitive),
# so positional coincidences (e.g. reporting an invisible wall after bumping a sunken crate) do not count
import re
SEMANTIC = {
    "tc01": r"clos\w+ (by )?(it)?self|auto[- ]?clos|closes automatically|closes on its own|reclos",
    "tc02": r"instant|no animation|snap|sudden|without.*animation|immediately|teleport",
    "tc03": r"half|stuck|partial|midway|jam",
    "tc04": r"mov\w+ (on its|by it|itself)|slid\w+|drift|moving without|by themselves",
    "tc05": r"stuck|trap|embedded|inside (the )?(pillar|wall|geometry)|cannot (move|escape)",
    "tc06": r"through (the )?(gate|bars|barrier|wall)|behind the (gate|bars)",
    "tc07": r"tint|pink|red|color|hue|magenta",
    "tc08": r"out of place|doesn'?t belong|random|floating|unattached|middle of|shouldn'?t",
    "tc09": r"sunk|sink|buried|embedded|into the (floor|ground)|half.*(floor|ground)|clip",
    "tc10": r"invisible",
    "torch": r"froz\w+|static|not (flicker|animat|mov)|no (flicker|animation)|one.*(other|not)",
}


def collect(run_bases, radius=3.0):
    answers_cache = {}
    eps = []
    for base in run_bases:
        for md in sorted(Path(base).glob("*/meta.json")):
            meta = json.loads(md.read_text())
            if meta.get("kind") != "audit":
                continue
            task = meta["task"]                     # audit_tc01_bug / audit_torch_bug ...
            parts = task.split("_")
            case, variant = parts[1], parts[2]
            cfg = meta["config"]
            if variant == "bug":
                if cfg not in answers_cache:
                    answers_cache[cfg] = resolve_answers(cfg)
                answers = answers_cache[cfg]
            else:
                answers = []
            flags = meta.get("flags", [])
            detected, loc_err, sem = False, None, False
            pat = SEMANTIC.get(case)
            if variant == "bug" and answers:
                a = answers[0]
                near = flags
                if a.get("global"):
                    detected = len(flags) > 0
                elif flags:
                    r_eff = a.get("radius", radius)
                    ex, ez = a.get("extent_x", 0), a.get("extent_z", 0)
                    def _d(f):
                        dx = max(abs(f["pos"][0] - a["position"][0]) - ex, 0)
                        dz = max(abs(f["pos"][2] - a["position"][2]) - ez, 0)
                        return math.hypot(dx, dz)
                    ds = [_d(f) for f in flags]
                    loc_err = round(min(ds), 2)
                    detected = min(ds) < r_eff
                    near = [f for f, d in zip(flags, ds) if d < r_eff]
                if detected and pat:
                    sem = any(re.search(pat, f.get("note", ""), re.I) for f in near)
                elif detected:
                    sem = True
            eps.append(dict(model=meta.get("model", "?").split("/")[-1], case=case, variant=variant,
                            seed=meta.get("seed"), n_flags=len(flags), detected=detected,
                            sem_detected=sem, loc_err=loc_err, steps=meta.get("steps_used"),
                            done=bool(meta.get("done_by_model")),
                            notes=[f.get("note", "")[:60] for f in flags]))
    return eps


def report(run_bases, radius=3.0, out=None):
    eps = collect(run_bases, radius)
    models = sorted({e["model"] for e in eps})
    cases = sorted({e["case"] for e in eps})
    g = defaultdict(list)
    for e in eps:
        g[(e["model"], e["case"], e["variant"])].append(e)

    lines = [f"# TC matrix ({', '.join(run_bases)})  radius={radius}m",
             "", "position hit = flag within radius of the answer; semantic hit = position hit AND note matches the phenomenon; FP = any flag in a clean episode", "",
             "| case | " + " | ".join(models) + " |",
             "|---|" + "---|" * len(models)]
    for c in cases:
        row = [c]
        for m in models:
            b = g.get((m, c, "bug"), [])
            cl = g.get((m, c, "clean"), [])
            det = sum(e["detected"] for e in b)
            sem = sum(e["sem_detected"] for e in b)
            fp = sum(1 for e in cl if e["n_flags"] > 0)
            cell = f"pos {det}/{len(b)} sem {sem}/{len(b)}" + (f" FP {fp}/{len(cl)}" if cl else "")
            row.append(cell)
        lines.append("| " + " | ".join(row) + " |")

    # per-model totals
    lines.append("")
    for m in models:
        b = [e for e in eps if e["model"] == m and e["variant"] == "bug"]
        cl = [e for e in eps if e["model"] == m and e["variant"] == "clean"]
        lines.append(f"- **{m}**: position {sum(e['detected'] for e in b)}/{len(b)}, "
                     f"semantic {sum(e['sem_detected'] for e in b)}/{len(b)}, "
                     f"clean FP episodes {sum(1 for e in cl if e['n_flags'] > 0)}/{len(cl)}")
    # -- detection-style P/R/F1: at most 1 TP per instance; duplicate and clean flags are FP --
    lines.append("\n## Precision / Recall / F1 (each bug instance matches at most one flag; surplus and clean flags are FP)\n")
    lines.append("| model | pos P | pos R | pos F1 | sem P | sem R | sem F1 | flags |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for m in models:
        TPp = FPp = TPs = FPs = FNp = FNs = 0
        for e in eps:
            if e["model"] != m: continue
            nf = e["n_flags"]
            if e["variant"] == "clean":
                FPp += nf; FPs += nf; continue
            tp_p = 1 if e["detected"] else 0
            tp_s = 1 if e["sem_detected"] else 0
            TPp += tp_p; FPp += nf - tp_p; FNp += 1 - tp_p
            TPs += tp_s; FPs += nf - tp_s; FNs += 1 - tp_s
        def prf(tp, fp, fn):
            pr = tp / (tp + fp) if tp + fp else 0.0
            rc = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
            return pr, rc, f1
        pp, rp, f1p = prf(TPp, FPp, FNp)
        ps, rs, f1s = prf(TPs, FPs, FNs)
        lines.append(f"| {m} | {pp:.2f} | {rp:.2f} | {f1p:.2f} | {ps:.2f} | {rs:.2f} | {f1s:.2f} | {TPp+FPp} |")

    text = "\n".join(lines) + "\n"
    print(text)
    if out:
        Path(out).write_text(text)
        Path(str(out) + ".episodes.json").write_text(json.dumps(eps, ensure_ascii=False, indent=1))
    return eps


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_bases", nargs="+")
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--out")
    args = ap.parse_args()
    report(args.run_bases, args.radius, args.out)
