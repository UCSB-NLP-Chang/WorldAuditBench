#!/bin/bash
# The 8B server on GPU 3 was mis-detected as failed (its previous instance was still writing shutdown
# messages into the same log); run the 8B after the 4B on GPU 3, then re-judge everything with a fresh
# 30B on 2+6 (the main orchestrator stops its 30B after its own final judge).
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [8b-chain] $*" | tee -a "$LOG"; }
until grep -q "qwen4b DONE" "$LOG"; do sleep 60; done
bash scripts/run_house_f2_model.sh qwen8b "Qwen/Qwen3-VL-8B-Instruct" 3 8020 0.50 6 16384
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
say "F2 ALL DONE incl. 8B -> reports/house-suite/s1-f2-l0.md, s1-ladder-l{1,2,3}.md"
