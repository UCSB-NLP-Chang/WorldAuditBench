#!/bin/bash
# 2026-09-07 05:15 UTC (user: 32B first, all cards, higher concurrency). Layout (GPUs 0/1 belong to another
# user; the harness' headless browsers all render on GPU 3, ~0.9 GB each, which is why GPU 3 cannot host a
# TP2 half):  4+5 32B (NVLink, parallel 8) | 2+6 30B (PCIe TP2, parallel 8, server kept on 8010 for the
# judge) | 3: 8B then 4B (util 0.50, 16k context) next to the browsers.  Each worker: L0 (resume) + L1/L2/L3.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [all] $*" | tee -a "$LOG"; }
say "layout: 32B@4,5 p8 | 30B@2,6 p8 (kept) | 8B->4B@3 p6"
bash scripts/run_house_f2_model.sh qwen32b "Qwen/Qwen3-VL-32B-Instruct" 4,5 8011 0.92 8 > /dev/null 2>&1 &
P32=$!
bash scripts/run_house_f2_model.sh qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 2,6 8010 0.90 8 32768 keep > /dev/null 2>&1 &
P30=$!
( bash scripts/run_house_f2_model.sh qwen8b "Qwen/Qwen3-VL-8B-Instruct" 3 8020 0.50 6 16384
  bash scripts/run_house_f2_model.sh qwen4b "Qwen/Qwen3-VL-4B-Instruct" 3 8021 0.50 6 16384 ) > /dev/null 2>&1 &
PS=$!
judge_all () {
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/v1/models 2>/dev/null)" = "200" ] || { say "!! no 30B on 8010 for the judge"; return 1; }
  for lv in l1 l2 l3; do
    $PY -m eval.judge_sem runs/hs-$lv-qwen4b runs/hs-$lv-qwen8b runs/hs-$lv-qwen30b runs/hs-$lv-qwen32b --out "reports/house-suite/s1-ladder-$lv.md" --cache runs/judge_cache_hs.json > "runs/hs-ladder-judge-$lv.log" 2>&1
    say "judge $lv done (exit $?)"
  done
  $PY -m eval.judge_sem runs/hs90-f2-qwen4b runs/hs90-f2-qwen8b runs/hs90-f2-qwen30b runs/hs90-f2-qwen32b --out reports/house-suite/s1-f2-l0.md --cache runs/judge_cache_hs.json > runs/hs-f2-l0-judge.log 2>&1
  say "judge L0 done (exit $?)"
}
wait $P32; say "32B worker finished"
wait $P30; say "30B worker finished -> interim judge"; judge_all
wait $PS;  say "small workers finished -> final judge"; judge_all
p=$(cat runs/.f2-server-qwen30b.pid); pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; sleep 10
say "F2 ALL DONE -> reports/house-suite/s1-f2-l0.md, s1-ladder-l{1,2,3}.md"
