#!/bin/bash
# One model, HS suite, f2 film, 90 steps: L0 (bugs + clean; resumes if it already exists) then the ladder
# L1/L2/L3. Usage: run_house_f2_model.sh NAME HFID GPUS PORT UTIL PARALLEL [MAXLEN] [keep]
#   NAME e.g. qwen32b; GPUS "4,5" (TP2 when two ids) or "6"; keep = leave the server running afterwards.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
NAME=$1; HFID=$2; GPUS=$3; PORT=$4; UTIL=$5; PAR=$6; MAXLEN=${7:-32768}; KEEP=${8:-}
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [$NAME] $*" | tee -a "$LOG"; }
FILM="--obs film --proprio 1 --blocked-hint 0 --film-dt 0.5 --film-max 8 --resume"
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
lv_tasks () { python3 -c "print(','.join(f'audit_hs{i:02d}_$1' for i in range(1,16)))"; }
NG=$(awk -F, '{print NF}' <<< "$GPUS")
say "serving on GPUs $GPUS port $PORT (util $UTIL, tp $NG, maxlen $MAXLEN)"
CUDA_VISIBLE_DEVICES=$GPUS nohup $VLLM serve "$HFID" --tensor-parallel-size "$NG" --max-model-len "$MAXLEN" --gpu-memory-utilization "$UTIL" --port "$PORT" > "runs/vllm-f2-$NAME.log" 2>&1 &
SPID=$!; echo $SPID > "runs/.f2-server-$NAME.pid"
up=0
for i in $(seq 1 180); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/v1/models" 2>/dev/null)" = "200" ] && { up=1; break; }
  grep -q "Engine core initialization failed\|CUDA out of memory" "runs/vllm-f2-$NAME.log" 2>/dev/null && break
  sleep 10
done
[ "$up" = 1 ] || { say "!! server failed to start"; exit 1; }
say "up"
URL="http://localhost:$PORT/v1"
say "== hs90-f2-$NAME L0 (resume) =="
$PY -m harness.runner --grid "$BUGS" --episodes 3 $FILM --parallel "$PAR" --tag "hs90-f2-$NAME" --model "$HFID" --base-url "$URL" >> "runs/hs90-f2-$NAME-bugs.log" 2>&1
say "L0 bugs done (exit $?)"
$PY -m harness.runner --grid audit_hs00_clean --episodes 6 $FILM --parallel "$PAR" --tag "hs90-f2-$NAME" --model "$HFID" --base-url "$URL" >> "runs/hs90-f2-$NAME-clean.log" 2>&1
say "L0 clean done (exit $?)"
for lv in l1 l2 l3; do
  say "== hs-$lv-$NAME =="
  $PY -m harness.runner --grid "$(lv_tasks $lv)" --episodes 3 $FILM --parallel "$PAR" --tag "hs-$lv-$NAME" --model "$HFID" --base-url "$URL" >> "runs/hs-$lv-$NAME.log" 2>&1
  say "hs-$lv-$NAME done (exit $?)"
done
if [ -z "$KEEP" ]; then pkill -TERM -P "$SPID" 2>/dev/null; kill "$SPID" 2>/dev/null; sleep 10; say "server stopped"; fi
say "$NAME DONE"
