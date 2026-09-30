#!/bin/bash
# vLLM serving commands (A6000 = Ampere: no FP8; use bf16 TP or AWQ/GPTQ int4).
# Usage: bash scripts/serve_model.sh <qwen8b|qwen30b|qwen32b|qwen72b|internvl38b> [GPU list, e.g. 3,4]
# Env: PORT overrides the port (default 8010; 8000 is taken by another user on this machine)
#
# Note (verified 2026-08-23): this machine's driver is 560.35 = CUDA 12.6; latest vllm
# (0.27, torch cu130) fails to start. Use vllm 0.11.x + torch cu128.
set -e
MODEL_KEY=${1:?usage: serve_model.sh <qwen8b|qwen30b|qwen32b|qwen72b|internvl38b> [GPUs]}
GPUS=${2:-3,4}
NGPU=$(awk -F, '{print NF}' <<< "$GPUS")
export CUDA_VISIBLE_DEVICES=$GPUS
export HF_HOME=/mnt/data3/jingbo/hf_cache          # /mnt/data is full; weights live on data3
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

COMMON="--max-model-len 32768 --gpu-memory-utilization 0.92 --port ${PORT:-8010}"

case $MODEL_KEY in
  qwen8b)      exec $VLLM serve Qwen/Qwen3-VL-8B-Instruct       --tensor-parallel-size "$NGPU" $COMMON ;;
  qwen30b)     exec $VLLM serve Qwen/Qwen3-VL-30B-A3B-Instruct  --tensor-parallel-size "$NGPU" $COMMON ;;
  qwen32b)     exec $VLLM serve Qwen/Qwen3-VL-32B-Instruct      --tensor-parallel-size "$NGPU" $COMMON ;;
  qwen72b)     exec $VLLM serve Qwen/Qwen2.5-VL-72B-Instruct    --tensor-parallel-size "$NGPU" $COMMON ;;
  internvl38b) exec $VLLM serve OpenGVLab/InternVL3_5-38B       --tensor-parallel-size "$NGPU" $COMMON ;;
  *) echo "unknown model $MODEL_KEY"; exit 1 ;;
esac
