#!/bin/bash
# HS suite night run v2 (2026-09-06, user's allocation): big model on the NVLink pair GPU 4+5,
# the P2P explorer (S2) on GPU 6 in parallel with S1. Phases:
#   S1 30B film (resume)  ||  S2 P2P x2 seeds      -> VQA (tours + vla) -> S1 judge
#   then 32B S1 film on 4+5 -> judge (30B back) -> summary
# Usage: bash scripts/run_house_night2.sh   (logs: runs/house-night.log)
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-night.log
BIG=4,5
P2P_GPU=6
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

serve () {  # name hfid gpus port
  local name=$1 hfid=$2 gpus=$3 port=$4
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  say "serving $name on GPUs $gpus port $port"
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.90 --port "$port" \
      > "runs/vllm-hs-$name.log" 2>&1 &
  for i in $(seq 1 180); do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/v1/models" 2>/dev/null)
    [ "$code" = "200" ] && { say "$name up"; return 0; }
    grep -q "Engine core initialization failed\|CUDA out of memory" "runs/vllm-hs-$name.log" 2>/dev/null && break
    sleep 10
  done
  say "!! $name failed to start"; return 1
}
stop_serve () { pgrep -u "$USER" -f "vllm serv[e]" | xargs -r kill; sleep 12; pgrep -u "$USER" -f "EngineCor[e]" | xargs -r kill; sleep 3; }

BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
FILM="--obs film --film-dt 0.5 --proprio 1 --blocked-hint 0 --parallel 4 --resume"
CFGS="hs00-clean,hs01-float,hs02-clip,hs03-scale,hs04-doublespawn,hs05-airwall,hs06-hole,hs07-ghostisland,hs08-jitter,hs09-magenta,hs10-backcull,hs11-xray,hs12-unload,hs13-statereset,hs14-lodpop,hs15-spawnpile"

run_s1 () {  # name hfid port
  local name=$1 hfid=$2 port=$3
  say "== S1 $name L0 film (bugs x3, resume) =="
  $PY -m harness.runner --grid "$BUGS" --episodes 3 $FILM --tag "hs-film-$name" \
      --model "$hfid" --base-url "http://localhost:$port/v1" >> "runs/hs-film-$name-bugs.log" 2>&1
  say "$name bugs done (exit $?)"
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 $FILM --tag "hs-film-$name" \
      --model "$hfid" --base-url "http://localhost:$port/v1" >> "runs/hs-film-$name-clean.log" 2>&1
  say "$name clean done (exit $?)"
}

say "== night run v2: big model on GPUs $BIG (NVLink), P2P on GPU $P2P_GPU =="
serve qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" "$BIG" 8010 || { say "abort: 30B did not start"; exit 1; }

# S2 in parallel with S1 (different GPU)
say "== S2 P2P explorer on GPU $P2P_GPU (parallel) =="
$PY -m harness.vla_explore --configs "$CFGS" --seeds 2 --ticks 1200 --tag hs-vla-p2p --gpu "$P2P_GPU" --eager > runs/hs-vla.log 2>&1 &
S2PID=$!
run_s1 qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 8010
wait $S2PID; say "S2 done (exit $?)"

say "== VQA audit (S3 tours, S2 recordings) with 30B =="
$PY -m eval.vqa_audit runs/hs-tour-v1 --model "Qwen/Qwen3-VL-30B-A3B-Instruct" --base-url http://localhost:8010/v1 \
    --judge-url http://localhost:8010/v1 --out reports/house-suite/tour-vqa-30b.md --cache runs/judge_cache_vqa_hs.json > runs/hs-vqa-tour.log 2>&1
say "VQA tour done (exit $?)"
if [ -d runs/hs-vla-p2p ]; then
  $PY -m eval.vqa_audit runs/hs-vla-p2p --model "Qwen/Qwen3-VL-30B-A3B-Instruct" --base-url http://localhost:8010/v1 \
      --judge-url http://localhost:8010/v1 --out reports/house-suite/vla-vqa-30b.md --cache runs/judge_cache_vqa_hs.json > runs/hs-vqa-vla.log 2>&1
  say "VQA vla done (exit $?)"
fi
say "== S1 judge (30B) =="
$PY -m eval.judge_sem runs/hs-film-qwen30b --out reports/house-suite/s1-judge-30b.md --cache runs/judge_cache_hs.json > runs/hs-judge.log 2>&1
say "judge done (exit $?)"
stop_serve

# 32B on the same NVLink pair
if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" "$BIG" 8010; then
  run_s1 qwen32b "Qwen/Qwen3-VL-32B-Instruct" 8010
  stop_serve
  if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" "$BIG" 8010; then
    $PY -m eval.judge_sem runs/hs-film-qwen30b runs/hs-film-qwen32b --out reports/house-suite/s1-judge.md --cache runs/judge_cache_hs.json > runs/hs-judge2.log 2>&1
    say "judge (30b+32b) done (exit $?)"
    stop_serve
  fi
fi
$PY scripts/house_night_summary.py >> "$LOG" 2>&1
say "ALL DONE"
