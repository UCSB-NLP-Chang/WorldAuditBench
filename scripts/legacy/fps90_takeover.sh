#!/bin/bash
# Takes over the 30B stage from run_house_fps90c.sh once it has judged the 32B settings: the driver would run
# f2 then f8 on 4+5 sequentially; instead f8 already runs on 2+3 (run_house_fps90d.sh) and this script runs
# f2 on the driver's 30B server (4+5, port 8010), judges both (judge_sem uses port 8010) and writes the table.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
PY=.venv/bin/python
LOG=runs/house-fps90.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
DRIVER=2771859
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
until grep -q "32B f2/f8 judged" runs/house-fps90.log; do
  kill -0 "$DRIVER" 2>/dev/null || { say "takeover: driver exited before judging 32B -> manual attention needed"; exit 1; }
  sleep 20
done
say "takeover: 32B judged; stopping driver $DRIVER and its f2 runner, continuing 30B f2 on 4+5 (port 8010)"
kill "$DRIVER" 2>/dev/null; sleep 3
pkill -u "$USER" -f "tag hs90-f2-qwen30[b]" 2>/dev/null; sleep 8
judge () { $PY -m eval.judge_sem "runs/$1" --out "reports/house-suite/fps90-$1.md" --cache runs/judge_cache_hs.json > "runs/$1-judge.log" 2>&1; say "judge $1 done (exit $?)"; }
table () { $PY scripts/fps_table.py reports/house-suite/fps90-*.md > reports/house-suite/fps-ablation-90.md; }
say "== hs90-f2-qwen30b (dt=0.5 x 8, parallel 6, GPUs 4+5) =="
$PY -m harness.runner --grid "$BUGS" --episodes 3 --obs film --proprio 1 --blocked-hint 0 --parallel 6 --resume --film-dt 0.5 --film-max 8 --tag hs90-f2-qwen30b \
    --model "$M30" --base-url "http://localhost:8010/v1" >> runs/hs90-f2-qwen30b-bugs.log 2>&1
say "hs90-f2-qwen30b bugs done (exit $?)"
$PY -m harness.runner --grid audit_hs00_clean --episodes 6 --obs film --proprio 1 --blocked-hint 0 --parallel 6 --resume --film-dt 0.5 --film-max 8 --tag hs90-f2-qwen30b \
    --model "$M30" --base-url "http://localhost:8010/v1" >> runs/hs90-f2-qwen30b-clean.log 2>&1
say "hs90-f2-qwen30b clean done (exit $?)"
judge hs90-f2-qwen30b; table
until grep -q "hs90-f8-qwen30b grid done" runs/house-fps90d.log 2>/dev/null; do sleep 60; done
judge hs90-f8-qwen30b; table
for p in $(cat runs/.fps90c-server-pids 2>/dev/null); do pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; done
sleep 10; : > runs/.fps90c-server-pids
say "ALL DONE (f2/f8, 32B+30B) -> reports/house-suite/fps-ablation-90.md"
