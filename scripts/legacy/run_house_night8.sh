#!/bin/bash
# Final scoring pass (replaces the tail of v3/v4b/v7 after the small-model driver held the GPUs):
# 30B on GPUs 4+5 -> S2 recordings VQA -> 32B tour-claims judge -> S1 judge for all four models
# -> summary. Every judge call is cached, so reruns are cheap.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-night.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
say "== v8 final scoring: serving 30B on GPUs 4,5 =="
CUDA_VISIBLE_DEVICES=4,5 nohup $VLLM serve Qwen/Qwen3-VL-30B-A3B-Instruct --tensor-parallel-size 2 --max-model-len 32768 \
    --gpu-memory-utilization 0.90 --port 8010 > runs/vllm-hs-judge30b-final.log 2>&1 &
ok=0
for i in $(seq 1 120); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/v1/models 2>/dev/null)" = "200" ] && { ok=1; break; }
  grep -q "Engine core initialization failed\|CUDA out of memory" runs/vllm-hs-judge30b-final.log 2>/dev/null && break
  sleep 10
done
[ "$ok" = 1 ] || { say "!! v8: 30B failed to start"; exit 1; }
say "judge30b up"
$PY -m eval.vqa_audit runs/hs-vla-p2p --model "Qwen/Qwen3-VL-30B-A3B-Instruct" --base-url http://localhost:8010/v1 \
    --judge-url http://localhost:8010/v1 --out reports/house-suite/vla-vqa-30b.md --cache runs/judge_cache_vqa_hs.json > runs/hs-vqa-vla.log 2>&1
say "VQA vla done (exit $?)"
$PY -m eval.vqa_audit runs/hs-tour-v1 --stage judge --claims-out runs/hs-tour-v1/claims-32b.jsonl \
    --judge-url http://localhost:8010/v1 --out reports/house-suite/tour-vqa-32b.md --cache runs/judge_cache_vqa_hs.json > runs/hs-vqa-tour-32b-judge.log 2>&1
say "32B tour VQA judged (exit $?)"
$PY -m eval.judge_sem runs/hs-film-qwen4b runs/hs-film-qwen8b runs/hs-film-qwen30b runs/hs-film-qwen32b \
    --out reports/house-suite/s1-judge.md --cache runs/judge_cache_hs.json > runs/hs-judge-all.log 2>&1
say "S1 judge (4 models) done (exit $?)"
pgrep -u "$USER" -f "vllm serv[e]" | xargs -r kill; sleep 12; pgrep -u "$USER" -f "EngineCor[e]" | xargs -r kill
$PY scripts/house_night_summary.py >> "$LOG" 2>&1
say "ALL DONE (v8)"
