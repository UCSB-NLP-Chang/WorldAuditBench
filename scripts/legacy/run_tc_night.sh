#!/bin/bash
# Overnight orchestration: serve each model in turn -> run the TC grid (22 tasks x 5 seeds, film, hint-off) -> report.
# Usage: bash scripts/run_tc_night.sh
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PORT=8010
TASKS=$(python3 - <<'EOF'
tcs = [f"audit_tc{i:02d}_{v}" for i in range(1, 11) for v in ("bug", "clean")]
tcs += ["audit_torch_bug", "audit_torch_clean"]
print(",".join(tcs))
EOF
)
echo "task set: $TASKS"

run_model () {  # name hfid gpus extra_args
  local name=$1 hfid=$2 gpus=$3 extra=$4
  echo "===== $name ($hfid) on GPUs $gpus ====="
  pkill -f "vllm serve" 2>/dev/null; sleep 8
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.92 --port $PORT $extra \
      > "runs/vllm-$name.log" 2>&1 &
  for i in $(seq 1 120); do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/v1/models 2>/dev/null)
    [ "$code" = "200" ] && break
    if grep -q "Engine core initialization failed" "runs/vllm-$name.log" 2>/dev/null; then
      echo "!! $name failed to start, skipping"; grep -iE "error" "runs/vllm-$name.log" | head -3
      return 1
    fi
    sleep 10
  done
  [ "$code" != "200" ] && { echo "!! $name startup timeout, skipping"; return 1; }
  echo "$name up"
  .venv/bin/python -m harness.runner --grid "$TASKS" --episodes 5 --proprio 1 \
      --obs film --blocked-hint 0 --parallel 4 --tag "tc-$name" \
      --model "$hfid" --base-url "http://localhost:$PORT/v1" --no-video \
      > "runs/tc-$name-grid.log" 2>&1
  echo "$name grid done (exit $?)"
  .venv/bin/python -m eval.report_tc "runs/tc-$name" --out "runs/tc-$name/report.md" \
      > /dev/null 2>&1 || echo "report_tc failed for $name"
}

run_model qwen4b  "Qwen/Qwen3-VL-4B-Instruct"        4   ""
run_model qwen8b  "Qwen/Qwen3-VL-8B-Instruct"        4   ""
run_model qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct"   4,6 ""
run_model qwen32b "Qwen/Qwen3-VL-32B-Instruct"       4,6 ""
run_model internvl38b "OpenGVLab/InternVL3_5-38B"    4,6 "--trust-remote-code"
pkill -f "vllm serve" 2>/dev/null
echo "===== ALL DONE ====="
