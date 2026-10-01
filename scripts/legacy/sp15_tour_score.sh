#!/bin/bash
# Score the re-recorded sp15 tour episode: 32B VQA over tour-v1, then 30B judge.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

swap () {  # hfid
  pkill -f "vllm serve" 2>/dev/null; sleep 10
  CUDA_VISIBLE_DEVICES=4,6 nohup $VLLM serve "$1" --tensor-parallel-size 2 \
      --max-model-len 32768 --gpu-memory-utilization 0.92 --port 8010 \
      > "runs/vllm-sp15fix.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/v1/models 2>/dev/null)
    [ "$code" = "200" ] && return 0
    sleep 10
  done
  return 1
}

swap Qwen/Qwen3-VL-32B-Instruct && \
  .venv/bin/python -m eval.vqa_audit runs/tour-v1 --stage vqa \
      --model Qwen/Qwen3-VL-32B-Instruct > runs/sp15fix-vqa.log 2>&1
echo "vqa exit $?"
swap Qwen/Qwen3-VL-30B-A3B-Instruct && \
  .venv/bin/python -m eval.vqa_audit runs/tour-v1 --stage judge \
      --out reports/sp-suite/tour-vqa-matrix.md > runs/sp15fix-judge.log 2>&1
echo "judge exit $?"
echo DONE
