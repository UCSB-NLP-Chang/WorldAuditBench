#!/usr/bin/env python3
"""Film-rate ablation table: collect the totals row of each per-run judge report into one table.
usage: fps_table.py reports/house-suite/fps-*.md > reports/house-suite/fps-ablation.md
"""
import re
import sys
from pathlib import Path

rows = []
for f in sys.argv[1:]:
    txt = Path(f).read_text()
    m = re.search(r"\| (Qwen[^|]+) \| (\d+/\d+) \| (\d+/\d+) \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \| (\d+) \|", txt)
    if not m:
        continue
    setting = Path(f).stem.replace("fps-", "")
    rows.append((setting, *m.groups()))
print("# S1 film-rate ablation (house suite, L0, judge 30B)\n")
print("| run | model | found | clean FP eps | P | R | F1 | flags |\n|---|---|---|---|---|---|---|---|")
for r in rows:
    print("| " + " | ".join(r) + " |")
