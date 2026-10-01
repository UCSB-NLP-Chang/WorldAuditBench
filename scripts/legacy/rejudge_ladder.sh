#!/bin/bash
# Re-run the ladder judge after fixing judge_sem's variant filter (l1/l2/l3 flags were
# silently skipped and defaulted to no-match).
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

pkill -f "vllm serve" 2>/dev/null; sleep 10
CUDA_VISIBLE_DEVICES=4,6 nohup $VLLM serve Qwen/Qwen3-VL-30B-A3B-Instruct \
    --tensor-parallel-size 2 --max-model-len 32768 \
    --gpu-memory-utilization 0.92 --port 8010 \
    > runs/vllm-rejudge.log 2>&1 &
for i in $(seq 1 150); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/v1/models 2>/dev/null)
  [ "$code" = "200" ] && break
  sleep 10
done
[ "$code" = "200" ] || { echo "serve failed"; exit 1; }

for lv in l1 l2 l3; do
  .venv/bin/python -m eval.judge_sem \
      runs/sp-$lv-qwen4b runs/sp-$lv-qwen8b runs/sp-$lv-qwen30b runs/sp-$lv-qwen32b \
      --out "reports/sp-suite/s1-ladder-$lv.md" > "runs/rejudge-$lv.log" 2>&1
  echo "rejudge $lv done (exit $?)"
done
pkill -f "vllm serve" 2>/dev/null
echo "REJUDGE ALL DONE"
