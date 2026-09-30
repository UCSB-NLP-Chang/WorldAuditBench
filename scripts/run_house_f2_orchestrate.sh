#!/bin/bash
# 2026-09-07 05:05 UTC (user): 32B first, all settings at the long budget, higher concurrency. Only one
# NVLink pair (4+5) is free (GPU 2 was taken by another user), so: 32B ladder on 4+5 (parallel 8) ->
# 30B (L0 remainder + ladder, parallel 8, server kept on port 8010 for the judge) -> judge everything
# once the 8B (GPU 6) and 4B (GPU 3) workers have also finished.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [orch] $*" | tee -a "$LOG"; }
bash scripts/run_house_f2_model.sh qwen32b "Qwen/Qwen3-VL-32B-Instruct" 4,5 8011 0.92 8
bash scripts/run_house_f2_model.sh qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,5 8010 0.90 8 32768 keep
judge_all () {
  for lv in l1 l2 l3; do
    $PY -m eval.judge_sem runs/hs-$lv-qwen4b runs/hs-$lv-qwen8b runs/hs-$lv-qwen30b runs/hs-$lv-qwen32b --out "reports/house-suite/s1-ladder-$lv.md" --cache runs/judge_cache_hs.json > "runs/hs-ladder-judge-$lv.log" 2>&1
    say "judge $lv done (exit $?)"
  done
  $PY -m eval.judge_sem runs/hs90-f2-qwen4b runs/hs90-f2-qwen8b runs/hs90-f2-qwen30b runs/hs90-f2-qwen32b --out reports/house-suite/s1-f2-l0.md --cache runs/judge_cache_hs.json > runs/hs-f2-l0-judge.log 2>&1
  say "judge L0 done (exit $?)"
}
say "big models done -> interim judge (30B on 8010)"
judge_all
until grep -q "qwen8b DONE" "$LOG" && grep -q "qwen4b DONE" "$LOG"; do sleep 60; done
say "small models done -> final judge"
judge_all
p=$(cat runs/.f2-server-qwen30b.pid); pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; sleep 10
say "F2 ALL DONE -> reports/house-suite/s1-f2-l0.md, s1-ladder-l{1,2,3}.md"
