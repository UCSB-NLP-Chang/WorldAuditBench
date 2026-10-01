#!/bin/bash
# HS suite, f2 film, 90 steps: small models (8B then 4B) on GPU 6 - L0 (bugs + clean) and the ladder L1/L2/L3.
# Servers are PID-scoped; runs resume. Judging is done by run_house_f2_big.sh (needs the 30B on port 8010).
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [small] $*" | tee -a "$LOG"; }
FILM="--obs film --proprio 1 --blocked-hint 0 --film-dt 0.5 --film-max 8 --resume"
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
lv_tasks () { python3 -c "print(','.join(f'audit_hs{i:02d}_$1' for i in range(1,16)))"; }
serve () {  # name hfid port
  say "serving $1 on GPU 6 port $3"
  CUDA_VISIBLE_DEVICES=6 nohup $VLLM serve "$2" --max-model-len 32768 --gpu-memory-utilization 0.90 --port "$3" > "runs/vllm-f2small-$1.log" 2>&1 &
  SPID=$!; echo $SPID > runs/.f2small-server-pid
  for i in $(seq 1 120); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$3/v1/models" 2>/dev/null)" = "200" ] && { say "$1 up"; return 0; }
    grep -q "Engine core initialization failed\|CUDA out of memory" "runs/vllm-f2small-$1.log" 2>/dev/null && break
    sleep 10
  done
  say "!! $1 failed to start"; return 1
}
stop () { pkill -TERM -P "$SPID" 2>/dev/null; kill "$SPID" 2>/dev/null; sleep 12; }
run_model () {  # name hfid port
  serve "$1" "$2" "$3" || return 1
  say "== hs90-f2-$1 L0 =="
  $PY -m harness.runner --grid "$BUGS" --episodes 3 $FILM --parallel 4 --tag "hs90-f2-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs90-f2-$1-bugs.log" 2>&1
  say "hs90-f2-$1 bugs done (exit $?)"
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 $FILM --parallel 4 --tag "hs90-f2-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs90-f2-$1-clean.log" 2>&1
  say "hs90-f2-$1 clean done (exit $?)"
  for lv in l1 l2 l3; do
    say "== hs-$lv-$1 =="
    $PY -m harness.runner --grid "$(lv_tasks $lv)" --episodes 3 $FILM --parallel 4 --tag "hs-$lv-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs-$lv-$1.log" 2>&1
    say "hs-$lv-$1 done (exit $?)"
  done
  stop
}
run_model qwen8b "Qwen/Qwen3-VL-8B-Instruct" 8020
run_model qwen4b "Qwen/Qwen3-VL-4B-Instruct" 8021
say "SMALL DONE"
