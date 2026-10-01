#!/bin/bash
# The 4B server died mid-ladder (vLLM: "AssertionError: Expected a cached item for mm_hash=..." in the
# multimodal processor cache) -> L2 stopped at 25/45, L3 never ran. Redo on GPU 4 with the MM processor
# cache disabled, resume, then re-judge L2/L3 (30B on port 8010) and regenerate the summary.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-f2-all.log
say () { echo "$(date '+%F %T') [4b-redo] $*" | tee -a "$LOG"; }
FILM="--obs film --proprio 1 --blocked-hint 0 --film-dt 0.5 --film-max 8 --resume"
M4="Qwen/Qwen3-VL-4B-Instruct"
lv_tasks () { python3 -c "print(','.join(f'audit_hs{i:02d}_$1' for i in range(1,16)))"; }
say "serving 4B on GPU 4 port 8021 (mm processor cache off)"
CUDA_VISIBLE_DEVICES=4 nohup $VLLM serve "$M4" --max-model-len 32768 --gpu-memory-utilization 0.90 --port 8021 --mm-processor-cache-gb 0 > runs/vllm-f2-qwen4b-redo.log 2>&1 &
SPID=$!
for i in $(seq 1 120); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8021/v1/models 2>/dev/null)" = "200" ] && break; sleep 10; done
say "4B up"
for lv in l2 l3; do
  say "== hs-$lv-qwen4b (resume) =="
  $PY -m harness.runner --grid "$(lv_tasks $lv)" --episodes 3 $FILM --parallel 6 --tag "hs-$lv-qwen4b" --model "$M4" --base-url http://localhost:8021/v1 >> "runs/hs-$lv-qwen4b.log" 2>&1
  say "hs-$lv-qwen4b done (exit $?) finished=$(ls runs/hs-$lv-qwen4b/*/meta.json 2>/dev/null | wc -l)"
done
pkill -TERM -P "$SPID" 2>/dev/null; kill "$SPID" 2>/dev/null; sleep 8
for lv in l2 l3; do
  $PY -m eval.judge_sem runs/hs-$lv-qwen4b runs/hs-$lv-qwen8b runs/hs-$lv-qwen30b runs/hs-$lv-qwen32b --out "reports/house-suite/s1-ladder-$lv.md" --cache runs/judge_cache_hs.json > "runs/hs-ladder-judge-$lv.log" 2>&1
  say "judge $lv done (exit $?)"
done
$PY scripts/house_f2_summary.py > reports/house-suite/summary-f2-all.md
say "F2 ALL DONE incl. 4B redo -> reports/house-suite/summary-f2-all.md"
