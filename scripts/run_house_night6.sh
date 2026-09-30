#!/bin/bash
# Use the idle NVLink pair while S2 finishes: S1 film for the small models (8B on GPU 4, 4B on GPU 5,
# concurrently), completing the 4-model lineup used on Sponza. Must finish before v3 needs GPUs 4,5.
cd "$(dirname "$0")/.."
export HF_HOME=/mnt/data3/jingbo/hf_cache
export PATH="$HOME/.local/bin:$PATH"
VLLM=/mnt/data3/jingbo/envs/vllm/bin/vllm
PY=.venv/bin/python
LOG=runs/house-night.log
say () { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
until grep -q "32B phase done" "$LOG"; do sleep 20; done
serve1 () {  # name hfid gpu port
  CUDA_VISIBLE_DEVICES=$3 nohup $VLLM serve "$2" --max-model-len 32768 --gpu-memory-utilization 0.90 --port "$4" > "runs/vllm-hs-$1.log" 2>&1 &
}
say "serving qwen8b on GPU 4 port 8011 and qwen4b on GPU 5 port 8012"
serve1 qwen8b "Qwen/Qwen3-VL-8B-Instruct" 4 8011
serve1 qwen4b "Qwen/Qwen3-VL-4B-Instruct" 5 8012
up8=0; up4=0
for i in $(seq 1 120); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8011/v1/models 2>/dev/null)" = "200" ] && up8=1
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8012/v1/models 2>/dev/null)" = "200" ] && up4=1
  [ "$up8" = 1 ] && [ "$up4" = 1 ] && break
  sleep 10
done
say "small models up: 8b=$up8 4b=$up4"
BUGS=$(python3 -c "print(','.join(f'audit_hs{i:02d}_bug' for i in range(1,16)))")
FILM="--obs film --film-dt 0.5 --proprio 1 --blocked-hint 0 --parallel 3 --resume"
run_s1 () {  # name hfid port
  $PY -m harness.runner --grid "$BUGS" --episodes 3 $FILM --tag "hs-film-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs-film-$1-bugs.log" 2>&1
  say "$1 bugs done (exit $?)"
  $PY -m harness.runner --grid audit_hs00_clean --episodes 6 $FILM --tag "hs-film-$1" --model "$2" --base-url "http://localhost:$3/v1" >> "runs/hs-film-$1-clean.log" 2>&1
  say "$1 clean done (exit $?)"
}
[ "$up8" = 1 ] && run_s1 qwen8b "Qwen/Qwen3-VL-8B-Instruct" 8011 &
[ "$up4" = 1 ] && run_s1 qwen4b "Qwen/Qwen3-VL-4B-Instruct" 8012 &
wait
pgrep -u "$USER" -f "vllm serv[e]" | xargs -r kill; sleep 12; pgrep -u "$USER" -f "EngineCor[e]" | xargs -r kill
say "small models phase done; GPUs 4,5 released"
