#!/bin/bash
# S1 observation-protocol upgrade: film mode (2 fps sim-time strip, max 8 frames/action,
# 480x300 + full-res final). Rate grounded in literature: Qwen-VL video training uses
# 2 fps; VideoGameQA-Bench feeds ~1 fps; TempGlitch ablates 1 vs 5 fps (denser: limited
# gain). Reruns L0 (canonical S1, 45 bug + 6 clean) and the L1/L2/L3 ladder per model.
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
      > "runs/vllm-film-$name.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/v1/models 2>/dev/null)
    [ "$code" = "200" ] && { echo "$name up"; return 0; }
    grep -q "Engine core initialization failed" "runs/vllm-film-$name.log" 2>/dev/null && break
    sleep 10
  done
  echo "!! $name failed"; return 1
}

tasks_for () {  # suffix (bug|l1|l2|l3) -> comma list
  local sfx=$1 out=""
  for i in 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15; do
    out="$out,audit_sp${i}_${sfx}"
  done
  echo "${out#,}"
}

FILM="--obs film --film-dt 0.5 --proprio 1 --blocked-hint 0 --parallel 4"

run_model () {  # name hfid gpus
  local name=$1 hfid=$2 gpus=$3
  serve "$name" "$hfid" "$gpus" || return 1
  echo "== $name L0 film =="
  .venv/bin/python -m harness.runner --grid "$(tasks_for bug)" --episodes 3 $FILM \
      --tag "sp-film-$name" --model "$hfid" --base-url http://localhost:8010/v1 \
      > "runs/film-l0-$name.log" 2>&1
  echo "$name l0-bug done (exit $?)"
  .venv/bin/python -m harness.runner --grid audit_sp00_clean --episodes 6 $FILM \
      --tag "sp-film-$name" --model "$hfid" --base-url http://localhost:8010/v1 \
      > "runs/film-l0c-$name.log" 2>&1
  echo "$name l0-clean done (exit $?)"
  for lv in l1 l2 l3; do
    echo "== $name $lv film =="
    .venv/bin/python -m harness.runner --grid "$(tasks_for $lv)" --episodes 3 $FILM \
        --tag "sp-${lv}f-$name" --model "$hfid" --base-url http://localhost:8010/v1 \
        > "runs/film-$lv-$name.log" 2>&1
    echo "$name $lv done (exit $?)"
  done
}

run_model qwen4b  "Qwen/Qwen3-VL-4B-Instruct"      4
run_model qwen8b  "Qwen/Qwen3-VL-8B-Instruct"      4
run_model qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6
run_model qwen32b "Qwen/Qwen3-VL-32B-Instruct"     4,6

echo "== judge (30B) =="
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6; then
  .venv/bin/python -m eval.judge_sem \
      runs/sp-film-qwen4b runs/sp-film-qwen8b runs/sp-film-qwen30b runs/sp-film-qwen32b \
      --out "reports/sp-suite/judge-matrix-film.md" > runs/film-judge-l0.log 2>&1
  echo "judge l0 done (exit $?)"
  for lv in l1 l2 l3; do
    .venv/bin/python -m eval.judge_sem \
        runs/sp-${lv}f-qwen4b runs/sp-${lv}f-qwen8b runs/sp-${lv}f-qwen30b runs/sp-${lv}f-qwen32b \
        --out "reports/sp-suite/s1-ladder-$lv-film.md" > "runs/film-judge-$lv.log" 2>&1
    echo "judge $lv done (exit $?)"
  done
fi
pkill -f "vllm serve" 2>/dev/null
echo "FILM ALL DONE"
