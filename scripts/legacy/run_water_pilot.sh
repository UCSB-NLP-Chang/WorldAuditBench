#!/bin/bash
# WT (reef) S1 pilot on the idle 30B judge server (GPUs 2+6, port 8010): 17 bug cases x 1 + clean x 2,
# f2 film, 90 steps, parallel 6; judged right after (same server) -> reports/water-suite/s1-pilot-30b.md
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=runs/water-pilot.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"
BUGS=$(python3 -c "print(','.join(f'audit_wt{i:02d}_bug' for i in range(1,18)))")
mkdir -p reports/water-suite
say "== wt90-f2-qwen30b (pilot) =="
$PY -m harness.runner --grid "$BUGS" --episodes 1 --obs film --proprio 1 --blocked-hint 0 --parallel 6 --resume --film-dt 0.5 --film-max 8 --tag wt90-f2-qwen30b --model "$M30" --base-url http://localhost:8010/v1 >> runs/wt90-f2-qwen30b-bugs.log 2>&1
say "bugs done (exit $?)"
$PY -m harness.runner --grid audit_wt00_clean --episodes 2 --obs film --proprio 1 --blocked-hint 0 --parallel 2 --resume --film-dt 0.5 --film-max 8 --tag wt90-f2-qwen30b --model "$M30" --base-url http://localhost:8010/v1 >> runs/wt90-f2-qwen30b-clean.log 2>&1
say "clean done (exit $?)"
$PY -m eval.judge_sem runs/wt90-f2-qwen30b --out reports/water-suite/s1-pilot-30b.md --cache runs/judge_cache_wt.json > runs/wt90-f2-qwen30b-judge.log 2>&1
say "judge done (exit $?) -> reports/water-suite/s1-pilot-30b.md"
