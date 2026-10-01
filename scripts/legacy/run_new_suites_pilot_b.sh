#!/bin/bash
# AF / WL / CT S1 pilots on the 30B server (GPUs 2+6, port 8010): 17 bug cases x 1 + clean x 2 per suite,
# f2 film, 90 steps, parallel 6; judged right after on the same server -> reports/<suite>-suite/s1-pilot-30b.md
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=runs/new-suites-pilot-b.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
M30="Qwen/Qwen3-VL-30B-A3B-Instruct"
URL=http://localhost:8010/v1
say "waiting for the 30B server"
for i in $(seq 1 240); do curl -s -o /dev/null http://localhost:8010/v1/models && break; sleep 10; done
curl -s -o /dev/null http://localhost:8010/v1/models || { say "!! server not up"; exit 1; }
say "server up"
for P in ct af; do
  case $P in af) DIR=airfield-suite;; wl) DIR=wilderness-suite;; ct) DIR=cottage-suite;; esac
  BUGS=$(python3 -c "print(','.join(f'audit_${P}{i:02d}_bug' for i in range(1,18)))")
  mkdir -p reports/$DIR
  say "== ${P}90b-f2-qwen30b =="
  $PY -m harness.runner --grid "$BUGS" --episodes 1 --obs film --proprio 1 --blocked-hint 0 --parallel 6 --resume --film-dt 0.5 --film-max 8 --tag ${P}90b-f2-qwen30b --model "$M30" --base-url $URL > runs/${P}90b-f2-qwen30b-bugs.log 2>&1
  say "$P bugs done (exit $?)"
  $PY -m harness.runner --grid audit_${P}00_clean --episodes 2 --obs film --proprio 1 --blocked-hint 0 --parallel 2 --resume --film-dt 0.5 --film-max 8 --tag ${P}90b-f2-qwen30b --model "$M30" --base-url $URL > runs/${P}90b-f2-qwen30b-clean.log 2>&1
  say "$P clean done (exit $?)"
  $PY -m eval.judge_sem runs/${P}90b-f2-qwen30b --out reports/$DIR/s1-pilot-30b.md --cache runs/judge_cache_${P}b.json > runs/${P}90b-f2-qwen30b-judge.log 2>&1
  say "$P judge done (exit $?) -> reports/$DIR/s1-pilot-30b.md"
done
say "all done"
