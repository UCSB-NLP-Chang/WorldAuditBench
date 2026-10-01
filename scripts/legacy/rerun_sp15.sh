#!/bin/bash
# Rerun the sp15 cell (spawnpile v3, real cloned assets) in all three settings.
# GPUs 0-3 are another user's; everything runs on 4/6 sequentially.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm

serve () {
  local name=$1 hfid=$2 gpus=$3 port=$4
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  echo "== serving $name =="
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.92 --port "$port" \
      > "runs/vllm-sp15-$name.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/v1/models" 2>/dev/null)
    [ "$code" = "200" ] && { echo "$name up"; return 0; }
    grep -q "Engine core initialization failed" "runs/vllm-sp15-$name.log" 2>/dev/null && break
    sleep 10
  done
  echo "!! $name failed"; return 1
}

grid () {
  .venv/bin/python -m harness.runner --grid audit_sp15_bug --episodes 3 \
      --proprio 1 --obs single --blocked-hint 0 --parallel 3 --tag "sp-$1" \
      --model "$2" --base-url http://localhost:8010/v1 > "runs/sp15redo-$1.log" 2>&1
  echo "$1 done (exit $?)"
}

echo "== tour re-record (no GPU) =="
.venv/bin/python - <<'PYEOF'
import sys
sys.path.insert(0, '.')
from harness.bridge import Bridge
from harness.scripted_tour import ROUTES, run_episode
from harness.runner import REPO
with Bridge() as br:
    run_episode(br, "sp15-spawnpile", ROUTES["sp15-spawnpile"],
                REPO / "runs" / "tour-v1" / "sp15-spawnpile-s0")
PYEOF
echo "tour done (exit $?)"

echo "== S2 VLA exploration (GPU 4) =="
pkill -f "vllm serve" 2>/dev/null; sleep 10
rm -rf runs/vla-sp15-redo
.venv/bin/python -m harness.vla_explore --configs sp15-spawnpile --seeds 2 --gpu 4 \
    --ticks 1200 --tag vla-sp15-redo --eager > runs/sp15redo-vla.log 2>&1
echo "explore done (exit $?)"

echo "== S1 grids =="
serve qwen4b  "Qwen/Qwen3-VL-4B-Instruct"      4   8010 && grid qwen4b  "Qwen/Qwen3-VL-4B-Instruct"
pkill -f "vllm serve" 2>/dev/null; sleep 10
serve qwen8b  "Qwen/Qwen3-VL-8B-Instruct"      4   8010 && grid qwen8b  "Qwen/Qwen3-VL-8B-Instruct"
pkill -f "vllm serve" 2>/dev/null; sleep 10
serve qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6 8010 && grid qwen30b "Qwen/Qwen3-VL-30B-A3B-Instruct"
pkill -f "vllm serve" 2>/dev/null; sleep 10
serve qwen32b "Qwen/Qwen3-VL-32B-Instruct"     4,6 8010 && grid qwen32b "Qwen/Qwen3-VL-32B-Instruct"

echo "== VQA (32B): new VLA + new tour episode =="
pkill -f "vllm serve" 2>/dev/null; sleep 10
if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.vqa_audit runs/vla-sp15-redo --stage vqa \
      --model Qwen/Qwen3-VL-32B-Instruct > runs/sp15redo-vqa1.log 2>&1
  echo "vla vqa done (exit $?)"
  .venv/bin/python -m eval.vqa_audit runs/tour-v1 --stage vqa \
      --model Qwen/Qwen3-VL-32B-Instruct > runs/sp15redo-vqa2.log 2>&1
  echo "tour vqa done (exit $?)"
fi

echo "== merge =="
.venv/bin/python - <<'PYEOF'
import json, shutil
from pathlib import Path
main, redo = Path('runs/vla-p2p1200'), Path('runs/vla-sp15-redo')
rows = [json.loads(l) for l in (main / 'claims.jsonl').read_text().splitlines()]
rows = [r for r in rows if r['case'] != 'sp15']
rows += [json.loads(l) for l in (redo / 'claims.jsonl').read_text().splitlines()]
(main / 'claims.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
for d in redo.iterdir():
    if d.is_dir():
        shutil.move(str(d), str(main / d.name))
print('merged', len(rows), 'rows')
PYEOF

echo "== judges + matrices (30B) =="
pkill -f "vllm serve" 2>/dev/null; sleep 10
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.judge_sem runs/sp-qwen4b runs/sp-qwen8b runs/sp-qwen30b runs/sp-qwen32b \
      --out reports/sp-suite/judge-matrix.md > runs/sp15redo-judge1.log 2>&1
  echo "S1 matrix done (exit $?)"
  .venv/bin/python -m eval.vqa_audit runs/vla-p2p1200 --stage judge \
      --out reports/sp-suite/vla-vqa-matrix.md > runs/sp15redo-judge2.log 2>&1
  echo "S2 matrix done (exit $?)"
  .venv/bin/python -m eval.vqa_audit runs/tour-v1 --stage judge \
      --out reports/sp-suite/tour-vqa-matrix.md > runs/sp15redo-judge3.log 2>&1
  echo "S3 matrix done (exit $?)"
fi
echo "ALL DONE"
