#!/bin/bash
# 2026-09-07 04:05 UTC: two more GPUs became free -> run the 30B f8 grid on GPUs 2+3 (port 8012) in parallel
# with the driver (run_house_fps90c.sh, GPUs 4+5). Judging happens later in fps90_takeover.sh because
# eval.judge_sem talks to port 8010 (the driver's 30B server).
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-fps90d.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
say "serving qwen30b on GPUs 2,3 port 8012 (util 0.85)"
CUDA_VISIBLE_DEVICES=2,3 nohup $VLLM serve "$M30" --tensor-parallel-size 2 --max-model-len 32768 \
    --gpu-memory-utilization 0.85 --port 8012 > runs/vllm-fps90d-qwen30b.log 2>&1 &
SPID=$!; echo $SPID > runs/.fps90d-server-pid
up=0
for i in $(seq 1 180); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8012/v1/models 2>/dev/null)" = "200" ] && { up=1; break; }
  grep -q "Engine core initialization failed\|CUDA out of memory" runs/vllm-fps90d-qwen30b.log 2>/dev/null && break
  sleep 10
done
[ "$up" = 1 ] || { say "!! qwen30b on 2,3 failed to start"; exit 1; }
say "qwen30b up on 8012"
say "== hs90-f8-qwen30b (dt=0.125 x 32, parallel 6, GPUs 2+3) =="
$PY -m harness.runner --grid "$BUGS" --episodes 3 --obs film --proprio 1 --blocked-hint 0 --parallel 6 --resume --film-dt 0.125 --film-max 32 --tag hs90-f8-qwen30b \
    --model "$M30" --base-url "http://localhost:8012/v1" >> runs/hs90-f8-qwen30b-bugs.log 2>&1
say "hs90-f8-qwen30b bugs done (exit $?)"
$PY -m harness.runner --grid audit_hs00_clean --episodes 6 --obs film --proprio 1 --blocked-hint 0 --parallel 6 --resume --film-dt 0.125 --film-max 32 --tag hs90-f8-qwen30b \
    --model "$M30" --base-url "http://localhost:8012/v1" >> runs/hs90-f8-qwen30b-clean.log 2>&1
say "hs90-f8-qwen30b clean done (exit $?)"
say "hs90-f8-qwen30b grid done"
pkill -TERM -P "$SPID" 2>/dev/null; kill "$SPID" 2>/dev/null; sleep 10
say "fps90d DONE (server on 2,3 stopped)"
