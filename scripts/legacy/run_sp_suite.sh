#!/bin/bash
# SP suite (Sponza-native bugs, suite v2) across the Qwen3-VL lineup.
# Scale: 15 bug cases x 3 policy resamples + shared clean x 6 (temperature 0.4 is the only
# stochasticity - the world itself is deterministic). Single-frame obs, proprio on, hint off.
# Order: 30B (reuses the already-live server on :8010) -> 8B -> 4B (GPU 3) -> 32B (GPUs 4,6),
# then the 30B judge is restarted for canonical scoring (eval/judge_sem.py).
# Usage: bash scripts/run_sp_suite.sh
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

BUGS=$(python3 -c "print(','.join(f'audit_sp{i:02d}_bug' for i in range(1,16)))")

serve () {  # name hfid gpus port
  local name=$1 hfid=$2 gpus=$3 port=$4
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  echo "== serving $name on GPUs $gpus port $port =="
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.92 --port "$port" \
      > "runs/vllm-sp-$name.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/v1/models" 2>/dev/null)
    [ "$code" = "200" ] && { echo "$name up"; return 0; }
    grep -q "Engine core initialization failed" "runs/vllm-sp-$name.log" 2>/dev/null && break
    sleep 10
  done
  echo "!! $name failed to start"; return 1
}

grid () {  # name hfid port
  local name=$1 hfid=$2 port=$3
  echo "== grid $name (bugs x3) =="
  .venv/bin/python -m harness.runner --grid "$BUGS" --episodes 3 --proprio 1 \
      --obs single --blocked-hint 0 --parallel 4 --tag "sp-$name" \
      --model "$hfid" --base-url "http://localhost:$port/v1" \
      > "runs/sp-$name-bugs.log" 2>&1
  echo "   bugs done (exit $?)"
  echo "== grid $name (clean x6) =="
  .venv/bin/python -m harness.runner --grid audit_sp00_clean --episodes 6 --proprio 1 \
      --obs single --blocked-hint 0 --parallel 4 --tag "sp-$name" \
      --model "$hfid" --base-url "http://localhost:$port/v1" \
      > "runs/sp-$name-clean.log" 2>&1
  echo "   clean done (exit $?)"
}

# phase 1: 30B on the live judge server
grid qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 8010

# phase 2+3: 8B then 4B on GPU 3, port 8011
if serve qwen8b "Qwen/Qwen3-VL-8B-Instruct" 3 8011; then
  grid qwen8b "Qwen/Qwen3-VL-8B-Instruct" 8011
fi
pkill -f "port 8011" 2>/dev/null; sleep 8
if serve qwen4b "Qwen/Qwen3-VL-4B-Instruct" 3 8011; then
  grid qwen4b "Qwen/Qwen3-VL-4B-Instruct" 8011
fi
pkill -f "port 8011" 2>/dev/null; sleep 8

# phase 4: 32B needs the 30B server's GPUs (4,6)
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" 4,6 8010; then
  grid qwen32b "Qwen/Qwen3-VL-32B-Instruct" 8010
fi

# phase 5: restore the 30B judge and score canonically
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.judge_sem runs/sp-qwen4b runs/sp-qwen8b runs/sp-qwen30b runs/sp-qwen32b \
      --out reports/sp-suite/judge-matrix.md > runs/sp-judge.log 2>&1
  echo "judge scoring done (exit $?)"
fi
echo "ALL DONE"
