#!/bin/bash
# HS suite (Family House) night run, 2026-09-06: the three settings on the new environment.
#   S3  scripted oracle tours (no VLM needed for the recording)         -> runs/hs-tour-v1
#   S1  embodied agent self-audit, film obs, 15 bugs x3 + clean x6      -> runs/hs-film-<model>
#   S2  P2P blind explorer x2 seeds per config                          -> runs/hs-vla-p2p
#   then the VQA audit of S2/S3 recordings and the S1 judge (both need a served VLM).
# GPUs on this machine are shared: every VLM phase first waits for free cards (scripts/gpu_wait.py).
# Usage: bash scripts/run_house_night.sh   (logs: runs/house-night.log)
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-night.log
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
stop_serve () { pkill -f "vllm serve" 2>/dev/null; sleep 12; }

BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
FILM="--obs film --film-dt 0.5 --proprio 1 --blocked-hint 0 --parallel 4"

# ---------------- S3: scripted tours (GPU-light: Chromium rendering only) ----------------
if [ -d runs/hs-tour-v1 ]; then
  say "S3 tours already recorded (runs/hs-tour-v1) - skipping"
else
  say "== S3 scripted tours =="
  $PY -m harness.scripted_tour --suite house --tag hs-tour-v1 > runs/hs-tour.log 2>&1
  say "S3 done (exit $?)"
fi

# ---------------- S1 + VQA with a 2-GPU model (30B judge/auditor, then 32B if cards stay free) ----------------
run_s1 () {  # name hfid port
  local name=$1 hfid=$2 port=$3
  say "== S1 $name L0 film (bugs x3) =="
  $PY -m harness.runner --grid "$BUGS" --episodes 3 $FILM --tag "hs-film-$name" \
      --model "$hfid" --base-url "http://localhost:$port/v1" > "runs/hs-film-$name-bugs.log" 2>&1
  say "$name bugs done (exit $?)"
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 $FILM --tag "hs-film-$name" \
      --model "$hfid" --base-url "http://localhost:$port/v1" > "runs/hs-film-$name-clean.log" 2>&1
  say "$name clean done (exit $?)"
}

GPUS=$($PY scripts/gpu_wait.py --n 2 --free-gb 44 --timeout-h 9 2>>"$LOG") || { say "no 2 free GPUs within 9h - S1/S2 skipped"; exit 0; }
say "got GPUs $GPUS"
if serve qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" "$GPUS" 8010; then
  run_s1 qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 8010
  # ---------------- S2: P2P explorer needs one more (small) GPU; VQA audits use the 30B server ----------------
  P2P_GPU=$($PY scripts/gpu_wait.py --n 1 --free-gb 12 --timeout-h 0.05 --prefer 3,2,1,0,5,4,6 2>>"$LOG" || true)
  if [ -n "$P2P_GPU" ]; then
    say "== S2 P2P explorer on GPU $P2P_GPU =="
    CFGS=$(python3 -c "print(','.join(['hs00-clean']+[n for n in __import__('json').load(open('/dev/stdin'))]))" <<< '["hs01-float","hs02-clip","hs03-scale","hs04-doublespawn","hs05-airwall","hs06-hole","hs07-ghostisland","hs08-jitter","hs09-magenta","hs10-backcull","hs11-xray","hs12-unload","hs13-statereset","hs14-lodpop","hs15-spawnpile"]')
    $PY -m harness.vla_explore --configs "$CFGS" --seeds 2 --ticks 1200 --tag hs-vla-p2p --gpu "$P2P_GPU" --eager > runs/hs-vla.log 2>&1
    say "S2 done (exit $?)"
  else
    say "no free GPU for P2P - S2 skipped"
  fi
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
fi
stop_serve
# second model if the cards are still free
GPUS=$($PY scripts/gpu_wait.py --n 2 --free-gb 44 --timeout-h 0.1 2>>"$LOG" || true)
if [ -n "$GPUS" ] && serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" "$GPUS" 8010; then
  run_s1 qwen32b "Qwen/Qwen3-VL-32B-Instruct" 8010
  stop_serve
  GPUS=$($PY scripts/gpu_wait.py --n 2 --free-gb 44 --timeout-h 0.1 2>>"$LOG" || true)
  if [ -n "$GPUS" ] && serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" "$GPUS" 8010; then
    $PY -m eval.judge_sem runs/hs-film-qwen30b runs/hs-film-qwen32b --out reports/house-suite/s1-judge.md --cache runs/judge_cache_hs.json > runs/hs-judge2.log 2>&1
    say "judge (30b+32b) done (exit $?)"
    stop_serve
  fi
fi
$PY scripts/house_night_summary.py >> "$LOG" 2>&1
say "ALL DONE"
