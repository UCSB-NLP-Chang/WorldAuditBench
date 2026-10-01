#!/bin/bash
# One-episode smoke test of the S1 ladder before the overnight batch:
# serve 4B on GPU 4, run audit_sp09_l3 (near spawn + type prior) once.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

pkill -f "vllm serve" 2>/dev/null; sleep 8
CUDA_VISIBLE_DEVICES=4 nohup $VLLM serve Qwen/Qwen3-VL-4B-Instruct \
    --max-model-len 32768 --gpu-memory-utilization 0.92 --port 8010 \
    > runs/vllm-smoke.log 2>&1 &
for i in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/v1/models 2>/dev/null)
  [ "$code" = "200" ] && break
  sleep 10
done
[ "$code" = "200" ] || { echo "serve failed"; exit 1; }

.venv/bin/python -m harness.runner --task audit_sp08_bug --proprio 1 --obs film --film-dt 0.5 \
    --blocked-hint 0 --seed 0 --tag smoke-ladder \
    --model Qwen/Qwen3-VL-4B-Instruct --base-url http://localhost:8010/v1
echo "smoke exit $?"
