#!/bin/bash
# Fix-up for rerun_realism.sh: GPUs 0-3 are now taken by another user's training, so the
# 4B/8B serves and the P2P exploration (all defaulting to GPU 3) failed. Everything below
# runs on GPUs 4/6 sequentially.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
CASES=audit_sp04_bug,audit_sp08_bug,audit_sp12_bug,audit_sp13_bug,audit_sp14_bug,audit_sp15_bug
VLACFG=sp04-doublespawn,sp08-jitter,sp12-unload,sp13-statereset,sp14-lodpop,sp15-originpile

serve () {
  local name=$1 hfid=$2 gpus=$3 port=$4
  local ngpu; ngpu=$(awk -F, '{print NF}' <<< "$gpus")
  echo "== serving $name =="
  CUDA_VISIBLE_DEVICES=$gpus nohup $VLLM serve "$hfid" \
      --tensor-parallel-size "$ngpu" --max-model-len 32768 \
      --gpu-memory-utilization 0.92 --port "$port" \
      > "runs/vllm-fixup-$name.log" 2>&1 &
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/v1/models" 2>/dev/null)
    [ "$code" = "200" ] && { echo "$name up"; return 0; }
    grep -q "Engine core initialization failed" "runs/vllm-fixup-$name.log" 2>/dev/null && break
    sleep 10
  done
  echo "!! $name failed"; return 1
}

grid () {
  .venv/bin/python -m harness.runner --grid "$CASES" --episodes 3 \
      --proprio 1 --obs single --blocked-hint 0 --parallel 3 --tag "sp-$1" \
      --model "$2" --base-url http://localhost:8010/v1 > "runs/fixup-$1.log" 2>&1
  echo "$1 done (exit $?)"
}

echo "== phase A: VLA exploration on GPU 4 =="
pkill -f "vllm serve" 2>/dev/null; sleep 12
rm -rf runs/vla-realism-redo
.venv/bin/python -m harness.vla_explore --configs "$VLACFG" --seeds 2 --gpu 4 \
    --ticks 1200 --tag vla-realism-redo --eager > runs/fixup-vla.log 2>&1
echo "explore done (exit $?)"

echo "== phase B: S1 4B/8B on GPU 4 =="
serve qwen4b "Qwen/Qwen3-VL-4B-Instruct" 4 8010 && grid qwen4b "Qwen/Qwen3-VL-4B-Instruct"
pkill -f "vllm serve" 2>/dev/null; sleep 12
serve qwen8b "Qwen/Qwen3-VL-8B-Instruct" 4 8010 && grid qwen8b "Qwen/Qwen3-VL-8B-Instruct"

echo "== phase C: VQA for the new VLA recordings (32B on 4,6) =="
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve qwen32b "Qwen/Qwen3-VL-32B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.vqa_audit runs/vla-realism-redo --stage vqa \
      --model Qwen/Qwen3-VL-32B-Instruct > runs/fixup-vqa.log 2>&1
  echo "vla vqa done (exit $?)"
fi

echo "== phase D: merge =="
.venv/bin/python - <<'PYEOF'
import json, shutil
from pathlib import Path
main, redo = Path('runs/vla-p2p1200'), Path('runs/vla-realism-redo')
rows = [json.loads(l) for l in (main / 'claims.jsonl').read_text().splitlines()]
rows = [r for r in rows if r['case'] not in ('sp04', 'sp08', 'sp12', 'sp13', 'sp14', 'sp15')]
rows += [json.loads(l) for l in (redo / 'claims.jsonl').read_text().splitlines()]
(main / 'claims.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
for d in redo.iterdir():
    if d.is_dir():
        shutil.move(str(d), str(main / d.name))
print('merged', len(rows), 'rows')
PYEOF

echo "== phase E: judges + matrices (30B on 4,6) =="
pkill -f "vllm serve" 2>/dev/null; sleep 12
if serve judge30b "Qwen/Qwen3-VL-30B-A3B-Instruct" 4,6 8010; then
  .venv/bin/python -m eval.judge_sem runs/sp-qwen4b runs/sp-qwen8b runs/sp-qwen30b runs/sp-qwen32b \
      --out reports/sp-suite/judge-matrix.md > runs/fixup-judge1.log 2>&1
  echo "S1 matrix done (exit $?)"
  .venv/bin/python -m eval.vqa_audit runs/vla-p2p1200 --stage judge \
      --out reports/sp-suite/vla-vqa-matrix.md > runs/fixup-judge2.log 2>&1
  echo "S2 matrix done (exit $?)"
  .venv/bin/python -m eval.vqa_audit runs/tour-v1 --stage judge \
      --out reports/sp-suite/tour-vqa-matrix.md > runs/fixup-judge3.log 2>&1
  echo "S3 matrix done (exit $?)"
fi
echo "ALL DONE"
