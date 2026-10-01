#!/bin/bash
# HS suite, f2 film, 90 steps: ladder L1/L2/L3 for 32B (GPUs 4+5, port 8011) and 30B (GPUs 2+3, port 8010)
# in parallel, after the f2/f8 ablation (fps90_takeover.sh) has released those GPUs. Then judge (30B on
# 8010) the ladder for all four models and the L0 f2 matrix, and write the reports.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [big] $*" | tee -a "$LOG"; }
FILM="--obs film --proprio 1 --blocked-hint 0 --film-dt 0.5 --film-max 8 --resume"
lv_tasks () { python3 -c "print(','.join(f'audit_hs{i:02d}_$1' for i in range(1,16)))"; }
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"; M32="Qwen/Qwen3-VL-32B-Instruct"
until grep -q "ALL DONE (f2/f8, 32B+30B)" runs/house-fps90.log; do sleep 60; done
say "f2/f8 ablation finished -> starting the ladder on 4+5 (32B) and 2+3 (30B)"
sleep 20
serve () {  # name hfid gpus port util pidfile
  say "serving $1 on GPUs $3 port $4 (util $5)"
  CUDA_VISIBLE_DEVICES=$3 nohup $VLLM serve "$2" --tensor-parallel-size 2 --max-model-len 32768 --gpu-memory-utilization "$5" --port "$4" > "runs/vllm-f2big-$1.log" 2>&1 &
  echo $! > "$6"
  for i in $(seq 1 180); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$4/v1/models" 2>/dev/null)" = "200" ] && { say "$1 up"; return 0; }
    grep -q "Engine core initialization failed\|CUDA out of memory" "runs/vllm-f2big-$1.log" 2>/dev/null && break
    sleep 10
  done
  say "!! $1 failed to start"; return 1
}
ladder () {  # name hfid port parallel
  for lv in l1 l2 l3; do
    say "== hs-$lv-$1 =="
    $PY -m harness.runner --grid "$(lv_tasks $lv)" --episodes 3 $FILM --parallel "$4" --tag "hs-$lv-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs-$lv-$1.log" 2>&1
    say "hs-$lv-$1 done (exit $?)"
  done
}
( serve qwen32b "$M32" 4,5 8011 0.92 runs/.f2big-32b-pid && ladder qwen32b "$M32" 8011 4
  p=$(cat runs/.f2big-32b-pid); pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; say "32B ladder finished, server stopped" ) &
PA=$!
( serve qwen30b "$M30" 2,3 8010 0.85 runs/.f2big-30b-pid && ladder qwen30b "$M30" 8010 6; say "30B ladder finished (server kept for judging)" ) &
PB=$!
wait $PA; wait $PB
until grep -q "SMALL DONE" runs/house-f2-all.log; do sleep 60; done
say "== judging (30B on 8010) =="
[ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/v1/models 2>/dev/null)" = "200" ] || serve qwen30b "$M30" 2,3 8010 0.85 runs/.f2big-30b-pid
for lv in l1 l2 l3; do
  $PY -m eval.judge_sem runs/hs-$lv-qwen4b runs/hs-$lv-qwen8b runs/hs-$lv-qwen30b runs/hs-$lv-qwen32b --out "reports/house-suite/s1-ladder-$lv.md" --cache runs/judge_cache_hs.json > "runs/hs-ladder-judge-$lv.log" 2>&1
  say "judge $lv done (exit $?)"
done
$PY -m eval.judge_sem runs/hs90-f2-qwen4b runs/hs90-f2-qwen8b runs/hs90-f2-qwen30b runs/hs90-f2-qwen32b --out reports/house-suite/s1-f2-l0.md --cache runs/judge_cache_hs.json > runs/hs-f2-l0-judge.log 2>&1
say "judge L0 (4 models) done (exit $?)"
p=$(cat runs/.f2big-30b-pid); pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; sleep 10
say "F2 ALL DONE -> reports/house-suite/s1-f2-l0.md, s1-ladder-l{1,2,3}.md"
