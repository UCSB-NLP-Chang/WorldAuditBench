#!/usr/bin/env python3
"""Collect the HS-suite night results into reports/house-suite/summary.md:
verification table, S3 tour exposure/VQA, S1 judge matrix, S2 explorer stats, run inventory.
Robust to missing pieces (phases that were skipped for lack of GPUs are reported as such).
usage: python scripts/house_night_summary.py
"""
import json
import re
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "reports" / "house-suite" / "summary.md"
lines = [f"# HS suite (Family House) - night run summary\n\nGenerated {time.strftime('%F %T')}.\n"]


def section(title):
    lines.append(f"\n## {title}\n")


# 1. verification
section("Behavioral verification (harness/hs_verify.py)")
rep = REPO / "runs" / "hs-verify" / "report.md"
if rep.exists():
    body = rep.read_text().splitlines()
    n_pass = sum(1 for l in body if l.startswith("- PASS"))
    n_fail = sum(1 for l in body if l.startswith("- FAIL"))
    lines.append(f"{n_pass} PASS / {n_fail} FAIL. Failures:\n")
    lines += [l for l in body if l.startswith("- FAIL")] or ["(none)"]
else:
    lines.append("not run")

# 2. S3 tours
section("S3 - scripted oracle tours (runs/hs-tour-v1)")
tour = REPO / "runs" / "hs-tour-v1"
if tour.exists():
    rows = []
    for ep in sorted(tour.iterdir()):
        m = ep / "meta.json"
        if not m.exists():
            continue
        meta = json.loads(m.read_text())
        rows.append(f"| {ep.name} | {meta['ticks']} | {meta['sim_seconds']} s | {len(meta['frames'])} | {len(meta.get('bug_events', []))} |")
    lines.append("| episode | ticks | sim time | frames | bug events |\n|---|---|---|---|---|")
    lines += rows
    vqas = [p.name for p in sorted((REPO / "reports" / "house-suite").glob("tour-vqa-*.md"))]
    lines.append(f"\nVQA audits: {', '.join(vqas) if vqas else 'not run (no GPU)'}")
else:
    lines.append("not run")

# 3. S1
section("S1 - embodied agent self-audit, film observation (runs/hs-film-*)")
for base in sorted(REPO.glob("runs/hs-film-*")):
    metas = [json.loads(p.read_text()) for p in base.glob("*/meta.json")]
    if not metas:
        continue
    bug = [m for m in metas if m["task"].endswith("_bug")]
    cln = [m for m in metas if m["task"].endswith("_clean")]
    flagged_bug = sum(1 for m in bug if m.get("flags"))
    flagged_cln = sum(1 for m in cln if m.get("flags"))
    lines.append(f"- **{base.name}**: {len(bug)} bug episodes ({flagged_bug} with >=1 flag), "
                 f"{len(cln)} clean episodes ({flagged_cln} with flags = clean FP)")
judge = sorted((REPO / "reports" / "house-suite").glob("s1-judge*.md"))
lines.append(f"\nJudge matrices: {', '.join(p.name for p in judge) if judge else 'not run (no GPU)'}")
if not list(REPO.glob("runs/hs-film-*")):
    lines.append("not run (no free GPUs during the night)")

# 4. S2
section("S2 - P2P blind explorer (runs/hs-vla-p2p)")
vla = REPO / "runs" / "hs-vla-p2p"
if vla.exists():
    eps = [p for p in vla.iterdir() if (p / "meta.json").exists()]
    lines.append(f"{len(eps)} episodes recorded; VQA audit: "
                 f"{'see vla-vqa-30b.md' if (REPO / 'reports/house-suite/vla-vqa-30b.md').exists() else 'not run'}")
else:
    lines.append("not run (no free GPU for the P2P model)")

# 5. night log tail
section("Night log (runs/house-night.log)")
log = REPO / "runs" / "house-night.log"
if log.exists():
    lines.append("```\n" + "\n".join(log.read_text().splitlines()[-40:]) + "\n```")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines) + "\n")
print("wrote", OUT)
