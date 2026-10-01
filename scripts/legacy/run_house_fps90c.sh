#!/bin/bash
# Reordered per user (2026-09-07 01:10 UTC): 32B f8 first (f4 deferred), then judge 32B f2+f8 and
# report; afterwards the 30B settings (f2, f8) on the same GPU pair 4+5. Uses only GPUs 4+5.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-fps90.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
serve () {  # name hfid port util
  say "serving $1 on GPUs 4,5 port $3 (util $4)"
  CUDA_VISIBLE_DEVICES=4,5 nohup $VLLM serve "$2" --tensor-parallel-size 2 --max-model-len 32768 \
      --gpu-memory-utilization "$4" --port "$3" > "runs/vllm-fps90c-$1.log" 2>&1 &
  echo $! >> runs/.fps90c-server-pids
  for i in $(seq 1 180); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$3/v1/models" 2>/dev/null)" = "200" ] && { say "$1 up"; return 0; }
    grep -q "Engine core initialization failed\|CUDA out of memory" "runs/vllm-fps90c-$1.log" 2>/dev/null && break
    sleep 10
  done
  say "!! $1 failed to start"; return 1
}
# stop ONLY the servers this driver started (PID file) - other jobs of this user (e.g. the user's
# own vLLM on another GPU) must never be touched; children (engine cores) go with the parent's group
stop_all () {
  for p in $(cat runs/.fps90c-server-pids 2>/dev/null); do pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; done
  sleep 12; : > runs/.fps90c-server-pids
}
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"; M32="Qwen/Qwen3-VL-32B-Instruct"
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
grid () {  # hfid port tag dt max parallel
  say "== $3 (dt=$4 x $5, parallel $6) =="
  $PY -m harness.runner --grid "$BUGS" --episodes 3 --obs film --proprio 1 --blocked-hint 0 --parallel "$6" --resume --film-dt "$4" --film-max "$5" --tag "$3" \
      --model "$1" --base-url "http://localhost:$2/v1" >> "runs/$3-bugs.log" 2>&1
  say "$3 bugs done (exit $?)"
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 --obs film --proprio 1 --blocked-hint 0 --parallel "$6" --resume --film-dt "$4" --film-max "$5" --tag "$3" \
      --model "$1" --base-url "http://localhost:$2/v1" >> "runs/$3-clean.log" 2>&1
  say "$3 clean done (exit $?)"
}
judge () { $PY -m eval.judge_sem "runs/$1" --out "reports/house-suite/fps90-$1.md" --cache runs/judge_cache_hs.json > "runs/$1-judge.log" 2>&1; say "judge $1 done (exit $?)"; }
table () { $PY scripts/fps_table.py reports/house-suite/fps90-*.md > reports/house-suite/fps-ablation-90.md; }

# 1) 32B f8 on the live server (port 8011); the live 32B server's PID is recorded so stop_all can end it
pgrep -u "$USER" -f "vllm serv[e].*--port 8011" | head -1 >> runs/.fps90c-server-pids
while pgrep -u "$USER" -f "tag hs90-f8-qwen32[b]" >/dev/null; do sleep 30; done   # a runner from the previous driver may still be on it
[ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8011/v1/models 2>/dev/null)" = "200" ] || serve qwen32b "$M32" 8011 0.92 || exit 1
grid "$M32" 8011 hs90-f8-qwen32b 0.125 32 4
stop_all
# 2) judge 32B f2 + f8 with the 30B -> interim conclusion
serve qwen30b "$M30" 8010 0.90 || exit 1
judge hs90-f2-qwen32b; judge hs90-f8-qwen32b; table
say "32B f2/f8 judged -> reports/house-suite/fps-ablation-90.md"
# 3) 30B f2 + f8 on the same server, judged as they finish
grid "$M30" 8010 hs90-f2-qwen30b 0.5 8 6;    judge hs90-f2-qwen30b; table
grid "$M30" 8010 hs90-f8-qwen30b 0.125 32 6; judge hs90-f8-qwen30b; table
stop_all
say "ALL DONE (f2/f8, 32B+30B) -> reports/house-suite/fps-ablation-90.md"
