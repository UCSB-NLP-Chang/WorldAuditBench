#!/bin/bash
# 32B phase re-run (the v3 attempt failed: KV cache too small at gpu-memory-utilization 0.90 with a
# 32k context - the Sponza runs used 0.92). Serves 32B on GPUs 4+5, runs S1 32B film (resume), keeps
# the server up for the 32B tour-VQA stage (waiter started earlier), then stops it well before the
# S2 explorer ends (v3 then serves the 30B on the same GPUs for the final VQA/judge).
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-night.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
say "serving qwen32b on GPUs 4,5 port 8010 (util 0.93)"
CUDA_VISIBLE_DEVICES=4,5 nohup $VLLM serve Qwen/Qwen3-VL-32B-Instruct --tensor-parallel-size 2 --max-model-len 32768 \
    --gpu-memory-utilization 0.93 --port 8010 > runs/vllm-hs-qwen32b.log 2>&1 &
ok=0
for i in $(seq 1 180); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/v1/models 2>/dev/null)
  [ "$code" = "200" ] && { ok=1; break; }
  grep -q "Engine core initialization failed\|CUDA out of memory" runs/vllm-hs-qwen32b.log 2>/dev/null && break
  sleep 10
done
[ "$ok" = 1 ] || { say "!! qwen32b failed to start again (see runs/vllm-hs-qwen32b.log)"; exit 1; }
say "qwen32b up"
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
FILM="--obs film --film-dt 0.5 --proprio 1 --blocked-hint 0 --parallel 4 --resume"
say "== S1 qwen32b L0 film (bugs x3) =="
$PY -m harness.runner --grid "$BUGS" --episodes 3 $FILM --tag hs-film-qwen32b --model "Qwen/Qwen3-VL-32B-Instruct" --base-url http://localhost:8010/v1 >> runs/hs-film-qwen32b-bugs.log 2>&1
say "qwen32b bugs done (exit $?)"
$PY -m harness.runner --grid audit_hs00_clean --episodes 6 $FILM --tag hs-film-qwen32b --model "Qwen/Qwen3-VL-32B-Instruct" --base-url http://localhost:8010/v1 >> runs/hs-film-qwen32b-clean.log 2>&1
say "qwen32b clean done (exit $?)"
# let the 32B tour-VQA stage (separate waiter) finish before stopping the server
for i in $(seq 1 60); do grep -q "32B tour VQA stage done" "$LOG" && break; sleep 20; done
pgrep -u "$USER" -f "vllm serv[e]" | xargs -r kill; sleep 12; pgrep -u "$USER" -f "EngineCor[e]" | xargs -r kill
say "32B phase done; GPUs 4,5 released"
