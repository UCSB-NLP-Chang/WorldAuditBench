#!/bin/bash
# Small models re-laid out (2026-09-07 06:50 UTC): the 4B on GPU 3 ran 3x slower than expected because GPU 3
# also renders every harness browser. Once the 32B releases 4+5, run 4B on GPU 4 and 8B on GPU 5 in parallel
# (single-GPU servers, parallel 6 each), then re-judge everything with a fresh 30B on 2+6.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [small2] $*" | tee -a "$LOG"; }
until grep -q "qwen32b DONE" "$LOG"; do sleep 30; done
sleep 20
bash scripts/run_house_f2_model.sh qwen4b "Qwen/Qwen3-VL-4B-Instruct" 4 8021 0.90 6 > /dev/null 2>&1 & P4=$!
bash scripts/run_house_f2_model.sh qwen8b "Qwen/Qwen3-VL-8B-Instruct" 5 8020 0.90 6 > /dev/null 2>&1 & P8=$!
wait $P4; wait $P8
say "4B + 8B finished"
until grep -q "F2 ALL DONE" "$LOG"; do sleep 60; done
export HF_HOME=/mnt/data3/jingbo/hf_cache
CUDA_VISIBLE_DEVICES=2,6 nohup /mnt/data3/jingbo/envs/vllm/bin/vllm serve Qwen/Qwen3-VL-30B-A3B-Instruct --tensor-parallel-size 2 --max-model-len 32768 --gpu-memory-utilization 0.90 --port 8010 > runs/vllm-f2-judge30b.log 2>&1 &
JP=$!
for i in $(seq 1 150); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/v1/models 2>/dev/null)" = "200" ] && break; sleep 10; done
for lv in l1 l2 l3; do
  $PY -m eval.judge_sem runs/hs-$lv-qwen4b runs/hs-$lv-qwen8b runs/hs-$lv-qwen30b runs/hs-$lv-qwen32b --out "reports/house-suite/s1-ladder-$lv.md" --cache runs/judge_cache_hs.json > "runs/hs-ladder-judge-$lv.log" 2>&1
  say "judge $lv done (exit $?)"
done
$PY -m eval.judge_sem runs/hs90-f2-qwen4b runs/hs90-f2-qwen8b runs/hs90-f2-qwen30b runs/hs90-f2-qwen32b --out reports/house-suite/s1-f2-l0.md --cache runs/judge_cache_hs.json > runs/hs-f2-l0-judge.log 2>&1
say "judge L0 done (exit $?)"
pkill -TERM -P "$JP" 2>/dev/null; kill "$JP" 2>/dev/null
say "F2 ALL DONE incl. small models -> reports/house-suite/s1-f2-l0.md, s1-ladder-l{1,2,3}.md"
