#!/bin/bash
# Setting 3 scoring: 32B VQA over the scripted-tour recordings, then 30B judge.
# Usage: bash scripts/run_tour_audit.sh
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

serve () {
  local name=$1 hfid=$2 gpus=$3 port=$4
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  echo "== serving $name =="
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.92 --port "$port" \
      > "runs/vllm-tour-$name.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/v1/models" 2>/dev/null)
    [ "$code" = "200" ] && { echo "$name up"; return 0; }
    grep -q "Engine core initialization failed" "runs/vllm-tour-$name.log" 2>/dev/null && break
    sleep 10
  done
  echo "!! $name failed"; return 1
}

pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.vqa_audit runs/tour-v1 --stage vqa \
      --model Qwen/Qwen3-VL-32B-Instruct > runs/tour-vqa.log 2>&1
  echo "vqa done (exit $?)"
fi
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.vqa_audit runs/tour-v1 --stage judge \
      --out reports/sp-suite/tour-vqa-matrix.md > runs/tour-judge.log 2>&1
  echo "tour judge done (exit $?)"
  # Setting 2 re-judged under the same joint-fallback rule (claims unchanged)
  .venv/bin/python -m eval.vqa_audit runs/vla-p2p1200 --stage judge \
      --out reports/sp-suite/vla-vqa-matrix.md > runs/vla-rejudge.log 2>&1
  echo "S2 judge done (exit $?)"
fi
echo "ALL DONE"
