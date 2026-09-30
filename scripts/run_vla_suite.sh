#!/bin/bash
# Setting 2 end-to-end: Open-P2P 1.2B explores every SP world (recording), then
# Qwen3-VL-32B audits the recordings via VQA, then the 30B judge scores claims.
# Usage: bash scripts/run_vla_suite.sh
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
TAG=vla-p2p1200

BUGS=$(python3 -c "
import glob, os
names = sorted(os.path.basename(p)[:-5] for p in glob.glob('env/configs/sp*.json')
               if 'answers' not in p and 'sp00' not in p)
print(','.join(names))")

echo "== phase 1: VLA exploration (P2P 1.2B on GPU 3) =="
.venv/bin/python -m harness.vla_explore --configs "$BUGS" --seeds 2 \
    --ticks 1200 --tag "$TAG" --eager > "runs/$TAG-explore-bugs.log" 2>&1
echo "   bugs done (exit $?)"
.venv/bin/python -m harness.vla_explore --configs sp00-clean --seeds 4 \
    --ticks 1200 --tag "$TAG" --eager > "runs/$TAG-explore-clean.log" 2>&1
echo "   clean done (exit $?)"

serve () {  # name hfid gpus port
  local name=$1 hfid=$2 gpus=$3 port=$4
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  echo "== serving $name =="
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.92 --port "$port" \
      > "runs/vllm-vla-$name.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/v1/models" 2>/dev/null)
    [ "$code" = "200" ] && { echo "$name up"; return 0; }
    grep -q "Engine core initialization failed" "runs/vllm-vla-$name.log" 2>/dev/null && break
    sleep 10
  done
  echo "!! $name failed to start"; return 1
}

echo "== phase 2: VQA audit (32B on GPUs 4,6) =="
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.vqa_audit "runs/$TAG" --stage vqa \
      --model Qwen/Qwen3-VL-32B-Instruct > "runs/$TAG-vqa.log" 2>&1
  echo "   vqa done (exit $?)"
fi

echo "== phase 3: judge scoring (30B on GPUs 4,6) =="
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.vqa_audit "runs/$TAG" --stage judge \
      --out reports/sp-suite/vla-vqa-matrix.md > "runs/$TAG-judge.log" 2>&1
  echo "   judge done (exit $?)"
fi
echo "ALL DONE"
