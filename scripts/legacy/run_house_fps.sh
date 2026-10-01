#!/bin/bash
# S1 film-rate ablation on the house suite (user request 2026-09-06): does a denser film strip
# help? Same L0 film protocol as the night run (proprio on, hint off, T=0.4, 35 steps), only the
# strip changes; the covered window is kept at ~4 s so only the rate varies:
#   f2: dt 0.5 s x 8 frames  (2 fps, the canonical run, already done: runs/hs-film-<model>)
#   f4: dt 0.25 s x 16 frames (4 fps)
#   f8: dt 0.125 s x 32 frames (8 fps)
# Big models first (30B then 32B) on the NVLink pair GPUs 4+5; each run judged with the 30B.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-fps.log
BIG=4,5
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
serve () {  # name hfid util
  say "serving $1 on GPUs $BIG (util $3)"
  CUDA_VISIBLE_DEVICES=$BIG nohup $VLLM serve "$2" --tensor-parallel-size 2 --max-model-len 32768 \
      --gpu-memory-utilization "$3" --port 8010 > "runs/vllm-fps-$1.log" 2>&1 &
  for i in $(seq 1 180); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/v1/models 2>/dev/null)" = "200" ] && { say "$1 up"; return 0; }
    grep -q "Engine core initialization failed\|CUDA out of memory" "runs/vllm-fps-$1.log" 2>/dev/null && break
    sleep 10
  done
  say "!! $1 failed to start"; return 1
}
stop_serve () { pgrep -u "$USER" -f "vllm serv[e]" | xargs -r kill; sleep 12; pgrep -u "$USER" -f "EngineCor[e]" | xargs -r kill; sleep 3; }
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
COMMON="--obs film --proprio 1 --blocked-hint 0 --parallel 4 --resume"

grid () {  # name hfid tag dt max
  say "== $3 ($1, film dt=$4 x $5) =="
  $PY -m harness.runner --grid "$BUGS" --episodes 3 $COMMON --film-dt "$4" --film-max "$5" --tag "$3" \
      --model "$2" --base-url http://localhost:8010/v1 >> "runs/$3-bugs.log" 2>&1
  say "$3 bugs done (exit $?)"
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 $COMMON --film-dt "$4" --film-max "$5" --tag "$3" \
      --model "$2" --base-url http://localhost:8010/v1 >> "runs/$3-clean.log" 2>&1
  say "$3 clean done (exit $?)"
}
judge () {  # tag
  $PY -m eval.judge_sem "runs/$1" --out "reports/house-suite/fps-$1.md" --cache runs/judge_cache_hs.json > "runs/$1-judge.log" 2>&1
  say "judge $1 done (exit $?)"
}

# 30B: runs + self-judge
serve qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 0.90 || exit 1
grid qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" hs-film4-qwen30b 0.25 16
judge hs-film4-qwen30b
grid qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" hs-film8-qwen30b 0.125 32
judge hs-film8-qwen30b
# the canonical 2 fps run, re-judged into the same report family (cached -> instant)
$PY -m eval.judge_sem runs/hs-film-qwen30b --out reports/house-suite/fps-hs-film2-qwen30b.md --cache runs/judge_cache_hs.json > runs/fps-judge-f2-30b.log 2>&1
stop_serve
# 32B: runs, then the 30B judge
if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" 0.93; then
  grid qwen32b "Qwen/Qwen3-VL-32B-Instruct" hs-film4-qwen32b 0.25 16
  grid qwen32b "Qwen/Qwen3-VL-32B-Instruct" hs-film8-qwen32b 0.125 32
  stop_serve
  if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 0.90; then
    judge hs-film4-qwen32b; judge hs-film8-qwen32b
    $PY -m eval.judge_sem runs/hs-film-qwen32b --out reports/house-suite/fps-hs-film2-qwen32b.md --cache runs/judge_cache_hs.json > runs/fps-judge-f2-32b.log 2>&1
    stop_serve
  fi
fi
$PY scripts/fps_table.py reports/house-suite/fps-*.md > reports/house-suite/fps-ablation.md
say "ALL DONE (fps ablation) -> reports/house-suite/fps-ablation.md"
