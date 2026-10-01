#!/bin/bash
# S1 difficulty ladder: L1 (told one bug) / L2 (+type & two examples) / L3 (+near spawn,
# small inspection zone) x 4 models x 15 cases x 3 episodes. No clean arm (the L1+ prompt
# asserts a bug exists; L0 clean-FP is already measured). GPUs 4/6 only; models served
# sequentially; judge (30B) at the end emits one matrix per level.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

serve () {
  local name=$1 hfid=$2 gpus=$3
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  pkill -f "vllm serve" 2>/dev/null; sleep 10
  echo "== serving $name =="
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.92 --port 8010 \
      > "runs/vllm-ladder-$name.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/v1/models 2>/dev/null)
    [ "$code" = "200" ] && { echo "$name up"; return 0; }
    grep -q "Engine core initialization failed" "runs/vllm-ladder-$name.log" 2>/dev/null && break
    sleep 10
  done
  echo "!! $name failed"; return 1
}

tasks_for () {  # level -> comma list of the 15 ladder tasks
  local lv=$1 out=""
  for i in 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15; do
    out="$out,audit_sp${i}_${lv}"
  done
  echo "${out#,}"
}

run_model () {  # name hfid gpus
  local name=$1 hfid=$2 gpus=$3
  serve "$name" "$hfid" "$gpus" || return 1
  for lv in l1 l2 l3; do
    echo "== $name $lv =="
    .venv/bin/python -m harness.runner --grid "$(tasks_for $lv)" --episodes 3 \
        --proprio 1 --obs single --blocked-hint 0 --parallel 4 --tag "sp-$lv-$name" \
        --model "$hfid" --base-url http://localhost:8010/v1 \
        > "runs/ladder-$lv-$name.log" 2>&1
    echo "$name $lv done (exit $?)"
  done
}

run_model qwen4b  "Qwen/Qwen3-VL-4B-Instruct"      4
run_model qwen8b  "Qwen/Qwen3-VL-8B-Instruct"      4
run_model qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6
run_model qwen32b "Qwen/Qwen3-VL-32B-Instruct"     4,6

echo "== judge (30B) =="
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6; then
  for lv in l1 l2 l3; do
    .venv/bin/python -m eval.judge_sem \
        runs/sp-$lv-qwen4b runs/sp-$lv-qwen8b runs/sp-$lv-qwen30b runs/sp-$lv-qwen32b \
        --out "reports/sp-suite/s1-ladder-$lv.md" > "runs/ladder-judge-$lv.log" 2>&1
    echo "judge $lv done (exit $?)"
  done
fi
pkill -f "vllm serve" 2>/dev/null
echo "LADDER ALL DONE"
