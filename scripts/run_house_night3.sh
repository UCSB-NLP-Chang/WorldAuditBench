#!/bin/bash
# HS suite night run v3 (takes over from v2 while its S1-clean runner and S2 explorer still run):
#   1. wait for the S1 30B runner -> S1 judge (30B) + S3 tour VQA (30B) -> stop 30B
#   2. 32B on GPUs 4+5 -> S1 32B film (resume) -> stop 32B          (overlaps with S2 on GPU 6)
#   3. wait for S2 -> 30B back -> S2 VQA -> judge (30B+32B) -> summary
# Usage: nohup bash scripts/run_house_night3.sh &   (logs: runs/house-night.log)
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-night.log
BIG=4,5
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
wait_for () { local pat=$1 what=$2; while pgrep -u "$USER" -f "$pat" >/dev/null; do sleep 30; done; say "$what finished"; }

BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
FILM="--obs film --film-dt 0.5 --proprio 1 --blocked-hint 0 --parallel 4 --resume"
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

say "== night run v3 takes over (30B on $BIG already serving; S2 on GPU 6 running) =="
wait_for "harness.runne[r]" "S1 30B (clean) runner"
say "== S1 judge (30B) + S3 tour VQA (30B) =="
$PY -m eval.judge_sem runs/hs-film-qwen30b --out reports/house-suite/s1-judge-30b.md --cache runs/judge_cache_hs.json > runs/hs-judge.log 2>&1
say "judge 30B done (exit $?)"
$PY -m eval.vqa_audit runs/hs-tour-v1 --model "Qwen/Qwen3-VL-30B-A3B-Instruct" --base-url http://localhost:8010/v1 \
    --judge-url http://localhost:8010/v1 --out reports/house-suite/tour-vqa-30b.md --cache runs/judge_cache_vqa_hs.json > runs/hs-vqa-tour.log 2>&1
say "VQA tour done (exit $?)"
stop_serve

if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" "$BIG" 8010; then
  run_s1 qwen32b "Qwen/Qwen3-VL-32B-Instruct" 8010
  stop_serve
fi

wait_for "vla_explor[e]" "S2 P2P explorer"
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" "$BIG" 8010; then
  if [ -d runs/hs-vla-p2p ]; then
    $PY -m eval.vqa_audit runs/hs-vla-p2p --model "Qwen/Qwen3-VL-30B-A3B-Instruct" --base-url http://localhost:8010/v1 \
        --judge-url http://localhost:8010/v1 --out reports/house-suite/vla-vqa-30b.md --cache runs/judge_cache_vqa_hs.json > runs/hs-vqa-vla.log 2>&1
    say "VQA vla done (exit $?)"
  fi
  $PY -m eval.judge_sem runs/hs-film-qwen30b runs/hs-film-qwen32b --out reports/house-suite/s1-judge.md --cache runs/judge_cache_hs.json > runs/hs-judge2.log 2>&1
  say "judge (30b+32b) done (exit $?)"
  stop_serve
fi
$PY scripts/house_night_summary.py >> "$LOG" 2>&1
say "ALL DONE"
