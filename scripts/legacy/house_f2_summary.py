#!/usr/bin/env python3
"""Assemble the HS-suite f2 (90-step) summary: L0 four models, the S1 ladder L1/L2/L3, the 32B film-rate
ablation, per-case hit lists and episode statistics, from the judge reports + run metadata.
Usage: house_f2_summary.py > reports/house-suite/summary-f2-all.md
"""
import glob
import json
import re
import statistics
from pathlib import Path

REP = Path("reports/house-suite")
MODELS = ["qwen4b", "qwen8b", "qwen30b", "qwen32b"]
LABEL = {"qwen4b": "4B", "qwen8b": "8B", "qwen30b": "30B", "qwen32b": "32B"}
COL = {"Qwen3-VL-4B-Instruct": "4B", "Qwen3-VL-8B-Instruct": "8B", "Qwen3-VL-30B-A3B-Instruct": "30B", "Qwen3-VL-32B-Instruct": "32B"}


def totals(md):
    """model -> dict(found, fp, P, R, F1, flags) from a judge report."""
    out = {}
    txt = Path(md).read_text() if Path(md).exists() else ""
    sec = txt.split("## Totals")[-1] if "## Totals" in txt else ""
    for line in sec.splitlines():
        m = re.match(r"\| (Qwen[^|]+?) \| (\S+) \| (\S+) \| (\S+) \| (\S+) \| (\S+) \| (\d+) \|", line)
        if m:
            out[COL.get(m.group(1), m.group(1))] = dict(found=m.group(2), fp=m.group(3), P=m.group(4), R=m.group(5), F1=m.group(6), flags=int(m.group(7)))
    return out


def per_case(md):
    """case -> {model: found str} for cases with any hit."""
    txt = Path(md).read_text() if Path(md).exists() else ""
    head = None
    hits = {}
    for line in txt.splitlines():
        if line.startswith("| case"):
            head = [COL.get(c.strip(), c.strip()) for c in line.strip("|").split("|")][1:]
            continue
        m = re.match(r"\| (hs\d\d[^|]*) \|(.*)\|$", line)
        if m and head:
            cells = [c.strip() for c in m.group(2).split("|")]
            row = {}
            for mod, c in zip(head, cells):
                mm = re.search(r"found (\d+)/(\d+)", c)
                if mm and int(mm.group(1)) > 0:
                    row[mod] = f"{mm.group(1)}/{mm.group(2)}"
            if row:
                hits[m.group(1).strip()] = row
    return hits


def ep_stats(tag):
    ms = [m for m in glob.glob(f"runs/{tag}/*/meta.json") if "clean" not in m]
    if not ms:
        return None
    d = [json.loads(Path(m).read_text()) for m in ms]
    st = [x["steps_used"] for x in d]
    fl = [len(x["flags"]) for x in d]
    return dict(n=len(d), steps=statistics.median(st), cap=sum(1 for s in st if s >= 90), flags=statistics.mean(fl), withflag=sum(1 for f in fl if f > 0))


def main():
    L = []
    L.append("# HS suite, S1 film f2 (0.5 s x 8 frames), 90-step budget — all settings (2026-09-07)\n")
    L.append("Judge: Qwen3-VL-30B-A3B temp 0 (`eval/judge_sem.py`), found = a flag the judge matches to the planted defect; "
             "P/R/F1 count at most one TP per episode, every other flag is an FP. Textured-wall house (v2).\n")
    # --- L0
    L.append("## 1. L0 (no priors): 15 bug cases x 3 episodes + 6 clean episodes\n")
    t = totals(REP / "s1-f2-l0.md")
    L.append("| model | found | clean FP eps | P | R | F1 | flags |")
    L.append("|---|---|---|---|---|---|---|")
    for m in ["4B", "8B", "30B", "32B"]:
        if m in t:
            r = t[m]
            L.append(f"| {m} | {r['found']} | {r['fp']} | {r['P']} | {r['R']} | {r['F1']} | {r['flags']} |")
    hits = per_case(REP / "s1-f2-l0.md")
    L.append("\nCases found by anyone (model: found/episodes):\n")
    for case, row in hits.items():
        L.append(f"- {case}: " + ", ".join(f"{m} {v}" for m, v in row.items()))
    # --- ladder
    L.append("\n## 2. S1 ladder (priors stacked: L1 existence, L2 +type & examples, L3 +near spawn), 45 episodes per level\n")
    L.append("| level | " + " | ".join(f"{m} found" for m in ["4B", "8B", "30B", "32B"]) + " | " + " | ".join(f"{m} P" for m in ["4B", "8B", "30B", "32B"]) + " |")
    L.append("|---|" + "---|" * 8)
    row0 = totals(REP / "s1-f2-l0.md")
    L.append("| L0 | " + " | ".join(row0.get(m, {}).get("found", "-") for m in ["4B", "8B", "30B", "32B"]) + " | " + " | ".join(row0.get(m, {}).get("P", "-") for m in ["4B", "8B", "30B", "32B"]) + " |")
    for lv in ["l1", "l2", "l3"]:
        tl = totals(REP / f"s1-ladder-{lv}.md")
        L.append(f"| {lv.upper()} | " + " | ".join(tl.get(m, {}).get("found", "-") for m in ["4B", "8B", "30B", "32B"]) + " | " + " | ".join(tl.get(m, {}).get("P", "-") for m in ["4B", "8B", "30B", "32B"]) + " |")
    for lv in ["l1", "l2", "l3"]:
        hits = per_case(REP / f"s1-ladder-{lv}.md")
        L.append(f"\n{lv.upper()} cases found: " + ("; ".join(f"{c.split(' ')[0]} " + ", ".join(f"{m} {v}" for m, v in row.items()) for c, row in hits.items()) or "none"))
    # --- episode stats
    L.append("\n## 3. Episode behaviour (bug episodes): median steps, episodes hitting the 90-step cap, flags per episode\n")
    L.append("| run | episodes | steps median | cap hit | flags/ep | eps with >=1 flag |")
    L.append("|---|---|---|---|---|---|")
    for m in MODELS:
        for lv, tag in [("L0", f"hs90-f2-{m}"), ("L1", f"hs-l1-{m}"), ("L2", f"hs-l2-{m}"), ("L3", f"hs-l3-{m}")]:
            s = ep_stats(tag)
            if s:
                L.append(f"| {LABEL[m]} {lv} | {s['n']} | {s['steps']:.0f} | {s['cap']} | {s['flags']:.1f} | {s['withflag']} |")
    # --- film-rate
    L.append("\n## 4. Film-rate ablation (32B, L0): f2 vs f8\n")
    L.append("| setting | frames/call | found | clean FP eps | flags | cap hit |")
    L.append("|---|---|---|---|---|---|")
    for tag, fr in [("hs90-f2-qwen32b", "8 (0.5 s)"), ("hs90-f8-qwen32b", "32 (0.125 s)")]:
        t = totals(REP / f"fps90-{tag}.md")
        s = ep_stats(tag)
        r = t.get("32B", {})
        L.append(f"| {tag.split('-')[1]} | {fr} | {r.get('found', '-')} | {r.get('fp', '-')} | {r.get('flags', '-')} | {s['cap'] if s else '-'}/{s['n'] if s else '-'} |")
    print("\n".join(L))


if __name__ == "__main__":
    main()
