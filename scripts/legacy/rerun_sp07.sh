#!/bin/bash
# Rerun the redesigned sp07 (ghost drape) cell in both settings, then regenerate matrices.
# v1 (ghost brazier-on-column) data is archived under runs/archive-sp07-ghostvase/.
# Usage: bash scripts/rerun_sp07.sh
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

serve () {  # name hfid gpus port
  local name=$1 hfid=$2 gpus=$3 port=$4
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  echo "== serving $name =="
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.92 --port "$port" \
      > "runs/vllm-sp07redo-$name.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/v1/models" 2>/dev/null)
    [ "$code" = "200" ] && { echo "$name up"; return 0; }
    grep -q "Engine core initialization failed" "runs/vllm-sp07redo-$name.log" 2>/dev/null && break
    sleep 10
  done
  echo "!! $name failed"; return 1
}

echo "== Setting 1 reruns (3 eps per model) =="
run_s1 () {  # name hfid gpus
  pkill -f "vllm serve" 2>/dev/null; sleep 12
  serve "$1" "$2" "$3" 8010 || return 1
  .venv/bin/python -m harness.runner --grid audit_sp07_bug --episodes 3 --proprio 1 \
      --obs single --blocked-hint 0 --parallel 3 --tag "sp-$1" \
      --model "$2" --base-url http://localhost:8010/v1 > "runs/sp07redo-$1.log" 2>&1
  echo "$1 done (exit $?)"
}
run_s1 qwen4b  "Qwen/Qwen3-VL-4B-Instruct"       3
run_s1 qwen8b  "Qwen/Qwen3-VL-8B-Instruct"       3
run_s1 qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct"  4,6
run_s1 qwen32b "Qwen/Qwen3-VL-32B-Instruct"      4,6

echo "== Setting 2: VLA re-exploration =="
.venv/bin/python -m harness.vla_explore --configs sp07-ghostdrape --seeds 2 \
    --ticks 1200 --tag vla-sp07-redo --eager > runs/sp07redo-vla.log 2>&1
echo "explore done (exit $?)"

echo "== VQA on the new recordings (32B) =="
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.vqa_audit runs/vla-sp07-redo --stage vqa \
      --model Qwen/Qwen3-VL-32B-Instruct > runs/sp07redo-vqa.log 2>&1
  echo "vqa done (exit $?)"
fi

echo "== merge new episodes + claims into the main VLA run =="
.venv/bin/python - <<'PYEOF'
import json, shutil
from pathlib import Path
main, redo = Path('runs/vla-p2p1200'), Path('runs/vla-sp07-redo')
rows = [json.loads(l) for l in (main / 'claims.jsonl').read_text().splitlines()]
rows = [r for r in rows if r['case'] != 'sp07']
rows += [json.loads(l) for l in (redo / 'claims.jsonl').read_text().splitlines()]
(main / 'claims.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
for d in redo.iterdir():
    if d.is_dir():
        shutil.move(str(d), str(main / d.name))
print('merged', len(rows), 'claim rows')
PYEOF

echo "== judge scoring + regenerate both matrices (30B) =="
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.judge_sem runs/sp-qwen4b runs/sp-qwen8b runs/sp-qwen30b runs/sp-qwen32b \
      --out reports/sp-suite/judge-matrix.md > runs/sp07redo-judge1.log 2>&1
  echo "S1 matrix done (exit $?)"
  .venv/bin/python -m eval.vqa_audit runs/vla-p2p1200 --stage judge \
      --out reports/sp-suite/vla-vqa-matrix.md > runs/sp07redo-judge2.log 2>&1
  echo "S2 matrix done (exit $?)"
fi
echo "ALL DONE"
