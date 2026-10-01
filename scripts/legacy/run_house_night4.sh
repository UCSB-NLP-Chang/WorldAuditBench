#!/bin/bash
# Follow-up to run_house_night3.sh: judge the 32B-auditor S3 tour claims with the canonical 30B
# judge once the main pipeline is done, then refresh the summary.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-night.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
until grep -q "ALL DONE" "$LOG"; do sleep 60; done
[ -f runs/hs-tour-v1/claims-32b.jsonl ] || { say "no 32B tour claims - nothing to judge"; exit 0; }
say "== judging 32B tour claims with 30B =="
CUDA_VISIBLE_DEVICES=4,5 nohup $VLLM serve Qwen/Qwen3-VL-30B-A3B-Instruct --tensor-parallel-size 2 --max-model-len 32768 \
    --gpu-memory-utilization 0.90 --port 8010 > runs/vllm-hs-judge30b-2.log 2>&1 &
for i in $(seq 1 180); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/v1/models 2>/dev/null)
  [ "$code" = "200" ] && break; sleep 10
done
$PY -m eval.vqa_audit runs/hs-tour-v1 --stage judge --claims-out runs/hs-tour-v1/claims-32b.jsonl \
    --judge-url http://localhost:8010/v1 --out reports/house-suite/tour-vqa-32b.md --cache runs/judge_cache_vqa_hs.json > runs/hs-vqa-tour-32b-judge.log 2>&1
say "32B tour VQA judged (exit $?)"
pgrep -u "$USER" -f "vllm serv[e]" | xargs -r kill; sleep 12; pgrep -u "$USER" -f "EngineCor[e]" | xargs -r kill
$PY scripts/house_night_summary.py >> "$LOG" 2>&1
say "ALL DONE (v4)"
