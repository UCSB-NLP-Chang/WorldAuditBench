#!/bin/bash
# 2026-09-07 05:15 UTC: 32B first, all cards, higher concurrency. Two servers per big model when GPU 2 is
# free: A = GPUs 4+5 (full context, parallel 8), B = GPUs 2+3 (16k context, util 0.80 because the headless
# browsers live on GPU 3, parallel 6). The ladder cases are split by case (A: hs01-08, B: hs09-15) so the
# two runners never touch the same episode; both write the same run tag (hs-lX-<model>).
# Order: 32B ladder -> 30B (L0 remainder + ladder; A's server kept on port 8010 for the judge) -> judge.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [split] $*" | tee -a "$LOG"; }
FILM="--obs film --proprio 1 --blocked-hint 0 --film-dt 0.5 --film-max 8 --resume"
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"; M32="Qwen/Qwen3-VL-32B-Instruct"
tasks () { python3 -c "import sys; lo,hi,lv=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]; print(','.join(f'audit_hs{i:02d}_{lv}' for i in range(lo,hi+1)))" "$@"; }
serve () {  # name hfid gpus port util maxlen -> pid file runs/.f2-server-<name>.pid
  say "serving $1 on GPUs $3 port $4 (util $5, maxlen $6)"
  CUDA_VISIBLE_DEVICES=$3 nohup $VLLM serve "$2" --tensor-parallel-size 2 --max-model-len "$6" --gpu-memory-utilization "$5" --port "$4" > "runs/vllm-f2-$1.log" 2>&1 &
  echo $! > "runs/.f2-server-$1.pid"
  for i in $(seq 1 150); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$4/v1/models" 2>/dev/null)" = "200" ] && { say "$1 up"; return 0; }
    grep -q "Engine core initialization failed\|CUDA out of memory\|RuntimeError" "runs/vllm-f2-$1.log" 2>/dev/null && break
    sleep 10
  done
  say "!! $1 failed to start"; return 1
}
stop () { local p; p=$(cat "runs/.f2-server-$1.pid" 2>/dev/null); [ -n "$p" ] && { pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; }; sleep 10; }
gpu2_free () { [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 2)" -lt 3000 ]; }
ladder () {  # model hfid port parallel lo hi
  for lv in l1 l2 l3; do
    say "== hs-$lv-$1 cases $5-$6 (port $3, parallel $4) =="
    $PY -m harness.runner --grid "$(tasks $5 $6 $lv)" --episodes 3 $FILM --parallel "$4" --tag "hs-$lv-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs-$lv-$1.log" 2>&1
    say "hs-$lv-$1 cases $5-$6 done (exit $?)"
  done
}
l0 () {  # model hfid port parallel
  BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
  say "== hs90-f2-$1 L0 (resume, port $3) =="
  $PY -m harness.runner --grid "$BUGS" --episodes 3 $FILM --parallel "$4" --tag "hs90-f2-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs90-f2-$1-bugs.log" 2>&1
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 $FILM --parallel "$4" --tag "hs90-f2-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs90-f2-$1-clean.log" 2>&1
  say "hs90-f2-$1 L0 done"
}
big_model () {  # name hfid portA portB keepA
  local name=$1 hfid=$2 pa=$3 pb=$4 keep=$5 hasB=0 PB=
  if gpu2_free && serve "${name}B" "$hfid" 2,3 "$pb" 0.80 16384; then
    hasB=1
    ( ladder "$name" "$hfid" "$pb" 6 9 15; say "${name}B share done" ) & PB=$!
  else
    say "GPU 2 not available -> $name runs on 4+5 only"
  fi
  serve "${name}A" "$hfid" 4,5 "$pa" 0.92 32768 || { say "!! ${name}A failed"; return 1; }
  [ "$name" = qwen30b ] && l0 "$name" "$hfid" "$pa" 8
  if [ "$hasB" = 1 ]; then ladder "$name" "$hfid" "$pa" 8 1 8; wait $PB; stop "${name}B"; else ladder "$name" "$hfid" "$pa" 8 1 15; fi
  [ -z "$keep" ] && stop "${name}A"
  say "$name DONE"
}
big_model qwen32b "$M32" 8011 8012
big_model qwen30b "$M30" 8010 8013 keep
judge_all () {
  for lv in l1 l2 l3; do
    $PY -m eval.judge_sem runs/hs-$lv-qwen4b runs/hs-$lv-qwen8b runs/hs-$lv-qwen30b runs/hs-$lv-qwen32b --out "reports/house-suite/s1-ladder-$lv.md" --cache runs/judge_cache_hs.json > "runs/hs-ladder-judge-$lv.log" 2>&1
    say "judge $lv done (exit $?)"
  done
  $PY -m eval.judge_sem runs/hs90-f2-qwen4b runs/hs90-f2-qwen8b runs/hs90-f2-qwen30b runs/hs90-f2-qwen32b --out reports/house-suite/s1-f2-l0.md --cache runs/judge_cache_hs.json > runs/hs-f2-l0-judge.log 2>&1
  say "judge L0 done (exit $?)"
}
say "big models done -> interim judge (30B on 8010)"; judge_all
until grep -q "qwen8b DONE" "$LOG" && grep -q "qwen4b DONE" "$LOG"; do sleep 60; done
say "small models done -> final judge"; judge_all
stop qwen30bA
say "F2 ALL DONE -> reports/house-suite/s1-f2-l0.md, s1-ladder-l{1,2,3}.md"
