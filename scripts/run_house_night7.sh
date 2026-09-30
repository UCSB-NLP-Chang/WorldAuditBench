#!/bin/bash
# Early judging while S2 still runs: once the small-model phase releases GPUs 4+5, serve the 30B
# judge, score all four S1 runs and the 32B tour claims, then release the GPUs again (long before
# v3 needs them for the S2 audit). v4b repeats the same judging at the very end from the cache.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-night.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
until grep -q "small models phase done" "$LOG"; do sleep 20; done
say "== early judge: serving 30B on GPUs 4,5 =="
CUDA_VISIBLE_DEVICES=4,5 nohup $VLLM serve Qwen/Qwen3-VL-30B-A3B-Instruct --tensor-parallel-size 2 --max-model-len 32768 \
    --gpu-memory-utilization 0.90 --port 8010 > runs/vllm-hs-judge30b-early.log 2>&1 &
ok=0
for i in $(seq 1 120); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/v1/models 2>/dev/null)" = "200" ] && { ok=1; break; }
  sleep 10
done
if [ "$ok" = 1 ]; then
  $PY -m eval.judge_sem runs/hs-film-qwen4b runs/hs-film-qwen8b runs/hs-film-qwen30b runs/hs-film-qwen32b \
      --out reports/house-suite/s1-judge.md --cache runs/judge_cache_hs.json > runs/hs-judge-all.log 2>&1
  say "early S1 judge (4 models) done (exit $?)"
  $PY -m eval.vqa_audit runs/hs-tour-v1 --stage judge --claims-out runs/hs-tour-v1/claims-32b.jsonl \
      --judge-url http://localhost:8010/v1 --out reports/house-suite/tour-vqa-32b.md --cache runs/judge_cache_vqa_hs.json > runs/hs-vqa-tour-32b-judge.log 2>&1
  say "early 32B tour VQA judge done (exit $?)"
else
  say "!! early judge: 30B did not come up"
fi
pgrep -u "$USER" -f "vllm serv[e]" | xargs -r kill; sleep 12; pgrep -u "$USER" -f "EngineCor[e]" | xargs -r kill
say "early judge phase done; GPUs 4,5 released"
