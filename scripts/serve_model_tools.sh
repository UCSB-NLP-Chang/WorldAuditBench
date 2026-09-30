#!/bin/bash
# vLLM serving for the tool-calling agent harness (agent/): tool calling + prompt-token details +
# multimodal prefix caching sized for 64k-token image-heavy contexts.
# Usage: bash scripts/serve_model_tools.sh <qwen8b|qwen30b|qwen32b> [GPU list, e.g. 3,4]
# Env: PORT (default 8010), MAX_LEN (default 98304), MM_CACHE_GB (default 16), PARALLEL_EPISODES (info only)
#
# Why these flags (verified against vLLM 0.11.x docs/source, 2026-09-08):
#   --enable-auto-tool-choice --tool-call-parser hermes   Qwen3-VL-Instruct uses the Hermes <tool_call> format
#   --enable-prompt-tokens-details                        usage.prompt_tokens_details.cached_tokens (cache hit rate)
#   --limit-mm-per-prompt '{"image":512}'                  ~40 actions x 9 frames + inspect re-injections per prompt
#   --max-model-len 98304                                  64k compaction threshold + one observation + note + output
#   --mm-processor-cache-gb 16                             preprocessing cache keyed by image hash; 4 GiB overflows
#                                                          with a few parallel episodes of ~360 images each
#   --mm-processor-kwargs min/max pixels                   let 32-multiple sizes pass through unchanged
# Prefix caching is on by default in V1. Note: N parallel episodes x 64k tokens of KV must stay resident
# (8B: ~9 GiB per 64k prefix; 30B-A3B: ~6 GiB; 32B: ~16 GiB) or cross-turn cache hits vanish.
set -e
MODEL_KEY=${1:?usage: serve_model_tools.sh <qwen8b|qwen30b|qwen32b> [GPUs]}
GPUS=${2:-3,4}
NGPU=$(awk -F, '{print NF}' <<< "$GPUS")
export CUDA_VISIBLE_DEVICES=$GPUS
export HF_HOME=${HF_HOME:-/mnt/data3/jingbo/hf_cache}
VLLM=${VLLM:-/mnt/data3/jingbo/envs/vllm/bin/vllm}

COMMON="--tensor-parallel-size $NGPU --max-model-len ${MAX_LEN:-98304} --gpu-memory-utilization 0.92 \
  --port ${PORT:-8010} --enable-auto-tool-choice --tool-call-parser hermes --enable-prompt-tokens-details \
  --limit-mm-per-prompt {\"image\":512} --mm-processor-cache-gb ${MM_CACHE_GB:-16} \
  --mm-processor-kwargs {\"size\":{\"shortest_edge\":16384,\"longest_edge\":1048576}}"

case $MODEL_KEY in
  qwen8b)  exec $VLLM serve Qwen/Qwen3-VL-8B-Instruct      $COMMON ;;
  qwen30b) exec $VLLM serve Qwen/Qwen3-VL-30B-A3B-Instruct $COMMON ;;
  qwen32b) exec $VLLM serve Qwen/Qwen3-VL-32B-Instruct     $COMMON ;;
  *) echo "unknown model $MODEL_KEY"; exit 1 ;;
esac
