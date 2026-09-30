#!/bin/bash
# House suite, S1 film-rate ablation at the raised step budget (90 steps; the 35-step runs left the
# agents in 1-3 of 13 rooms). Two NVLink pairs in parallel: 32B on GPUs 2+3 (port 8011), 30B on
# GPUs 4+5 (port 8010, also the judge). Settings keep a ~4 s strip window and vary only the rate:
#   f2: dt 0.5 x 8 frames | f4: dt 0.25 x 16 | f8: dt 0.125 x 32
# GPU budget (user, 2026-09-06): leave at least two cards free for others - this uses 2+3 (30B,
# port 8010, also the judge) and 4+5 (32B, port 8011, parallel 4, util 0.92 after the engine hang
# on 2+3 with parallel 6); 0, 1 and 6 stay free. Walls carry the plaster grain (EXPERIMENTS.md).
# Usage: nohup bash scripts/run_house_fps90.sh &   (log: runs/house-fps90.log)
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-fps90.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
serve () {  # name hfid gpus port util
  say "serving $1 on GPUs $3 port $4 (util $5)"
  CUDA_VISIBLE_DEVICES=$3 nohup $VLLM serve "$2" --tensor-parallel-size 2 --max-model-len 32768 \
      --gpu-memory-utilization "$5" --port "$4" > "runs/vllm-fps90-$1.log" 2>&1 &
  for i in $(seq 1 180); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$4/v1/models" 2>/dev/null)" = "200" ] && { say "$1 up"; return 0; }
    grep -q "Engine core initialization failed\|CUDA out of memory" "runs/vllm-fps90-$1.log" 2>/dev/null && break
    sleep 10
  done
  say "!! $1 failed to start"; return 1
}
stop_port () { pgrep -u "$USER" -f "vllm serv[e].*--port $1" | xargs -r kill; sleep 12; }
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
COMMON="--obs film --proprio 1 --blocked-hint 0 --parallel 6 --resume"
COMMON32="--obs film --proprio 1 --blocked-hint 0 --parallel 4 --resume"
grid () {  # hfid port tag dt max [common]
  local C=${6:-$COMMON}
  say "== $3 (dt=$4 x $5) =="
  $PY -m harness.runner --grid "$BUGS" --episodes 3 $C --film-dt "$4" --film-max "$5" --tag "$3" \
      --model "$1" --base-url "http://localhost:$2/v1" >> "runs/$3-bugs.log" 2>&1
  say "$3 bugs done (exit $?)"
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 $C --film-dt "$4" --film-max "$5" --tag "$3" \
      --model "$1" --base-url "http://localhost:$2/v1" >> "runs/$3-clean.log" 2>&1
  say "$3 clean done (exit $?)"
}
judge () {  # tag  (30B judge on port 8010)
  $PY -m eval.judge_sem "runs/$1" --out "reports/house-suite/fps90-$1.md" --cache runs/judge_cache_hs.json > "runs/$1-judge.log" 2>&1
  say "judge $1 done (exit $?)"
}
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"; M32="Qwen/Qwen3-VL-32B-Instruct"

pipeline32 () {
  serve qwen32b "$M32" 4,5 8011 0.92 || { say "32B pipeline aborted"; return 1; }
  grid "$M32" 8011 hs90-f2-qwen32b 0.5 8 "$COMMON32"
  grid "$M32" 8011 hs90-f4-qwen32b 0.25 16 "$COMMON32"
  grid "$M32" 8011 hs90-f8-qwen32b 0.125 32 "$COMMON32"
  stop_port 8011
  say "32B pipeline done"
}
pipeline32 &
P32=$!

serve qwen30b "$M30" 2,3 8010 0.90 || exit 1
grid "$M30" 8010 hs90-f2-qwen30b 0.5 8;   judge hs90-f2-qwen30b
grid "$M30" 8010 hs90-f4-qwen30b 0.25 16; judge hs90-f4-qwen30b
grid "$M30" 8010 hs90-f8-qwen30b 0.125 32; judge hs90-f8-qwen30b
wait $P32
for t in hs90-f2-qwen32b hs90-f4-qwen32b hs90-f8-qwen32b; do [ -d "runs/$t" ] && judge "$t"; done
stop_port 8010
$PY scripts/fps_table.py reports/house-suite/fps90-*.md > reports/house-suite/fps-ablation-90.md
say "ALL DONE (fps ablation, 90 steps) -> reports/house-suite/fps-ablation-90.md"
