#!/bin/bash
# Second half of the 90-step film-rate ablation: after the 32B pipeline (GPUs 4+5) finishes, run
# the 30B settings on the same pair (another user's job landed on GPU 3 and killed the parallel 30B
# server), judge everything with the 30B, build the table. Leaves >= 2 GPUs free for others.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-fps90.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
until grep -q "32B pipeline done" "$LOG"; do sleep 60; done
GPUS=$($PY scripts/gpu_wait.py --n 2 --free-gb 44 --timeout-h 6 --prefer 4,5,2,6,0,1,3 2>>"$LOG") || { say "no free GPU pair for the 30B half"; exit 1; }
say "serving qwen30b on GPUs $GPUS port 8010 (util 0.90)"
CUDA_VISIBLE_DEVICES=$GPUS nohup $VLLM serve Qwen/Qwen3-VL-30B-A3B-Instruct --tensor-parallel-size 2 --max-model-len 32768 \
    --gpu-memory-utilization 0.90 --port 8010 > runs/vllm-fps90-qwen30b-b.log 2>&1 &
for i in $(seq 1 180); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/v1/models 2>/dev/null)" = "200" ] && { say "qwen30b up"; break; }
  sleep 10
done
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
COMMON="--obs film --proprio 1 --blocked-hint 0 --parallel 6 --resume"
grid () {  # tag dt max
  say "== $1 (dt=$2 x $3) =="
  $PY -m harness.runner --grid "$BUGS" --episodes 3 $COMMON --film-dt "$2" --film-max "$3" --tag "$1" --model "$M30" --base-url http://localhost:8010/v1 >> "runs/$1-bugs.log" 2>&1
  say "$1 bugs done (exit $?)"
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 $COMMON --film-dt "$2" --film-max "$3" --tag "$1" --model "$M30" --base-url http://localhost:8010/v1 >> "runs/$1-clean.log" 2>&1
  say "$1 clean done (exit $?)"
}
judge () { $PY -m eval.judge_sem "runs/$1" --out "reports/house-suite/fps90-$1.md" --cache runs/judge_cache_hs.json > "runs/$1-judge.log" 2>&1; say "judge $1 done (exit $?)"; }
grid hs90-f2-qwen30b 0.5 8;    judge hs90-f2-qwen30b
grid hs90-f4-qwen30b 0.25 16;  judge hs90-f4-qwen30b
grid hs90-f8-qwen30b 0.125 32; judge hs90-f8-qwen30b
for t in hs90-f2-qwen32b hs90-f4-qwen32b hs90-f8-qwen32b; do [ -d "runs/$t" ] && judge "$t"; done
pgrep -u "$USER" -f "vllm serv[e].*port 8010" | xargs -r kill; sleep 12; pgrep -u "$USER" -f "EngineCor[e]" | xargs -r kill
$PY scripts/fps_table.py reports/house-suite/fps90-*.md > reports/house-suite/fps-ablation-90.md
say "ALL DONE (fps ablation, 90 steps) -> reports/house-suite/fps-ablation-90.md"
