#!/bin/bash
# Generic launcher for the tool-calling agent harness. Everything is a runner argument; this wrapper
# only supplies the endpoint, the key and a log file.
#
#   bash scripts/run_agent.sh --suite sp --variant l1 --episodes 3 --parallel 4 --tag sp-l1 \
#       --model qwen3.8-flash --obs film --decision macro                  # endpoint defaults to alibaba
#   bash scripts/run_agent.sh --endpoint openrouter --suite hs --variant all --cases 01,05 --episodes 1 --tag hs-try \
#       --model qwen/qwen3.8-flash --extra-body '{"provider":{"only":["alibaba"]}}'
#   bash scripts/run_agent.sh --endpoint alibaba --task audit_tc10_bug --seed 0 --decision tick --obs final ...
#
# --endpoint presets (default alibaba; base URL + key file, override with --base-url / VLM_API_KEY):
#   openrouter  https://openrouter.ai/api/v1                                            ~/.config/openrouter/key
#   alibaba     https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1  ~/.config/alibaba/key
#   vllm        http://localhost:8010/v1 (no key)
# Suites: tc sp hs wt af wl ct. Variants: bug | clean | all | l1 | l2 | l3. --gpu defaults to native on macOS
# (Apple GPU via full Chromium) and gl-egl elsewhere.
# Stop a grid completely with: pkill -f multiprocessing.spawn; pkill -f ms-playwright
set -e
cd "$(dirname "$0")/.."
ENDPOINT=alibaba; ARGS=()
while (( $# )); do
  case $1 in
    --endpoint) ENDPOINT=$2; shift 2 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
case $ENDPOINT in
  openrouter) BASE=https://openrouter.ai/api/v1; KEYFILE=~/.config/openrouter/key ;;
  alibaba)    BASE=https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1; KEYFILE=~/.config/alibaba/key ;;
  vllm)       BASE=http://localhost:8010/v1; KEYFILE= ;;
  *) echo "unknown --endpoint $ENDPOINT (openrouter | alibaba | vllm)"; exit 1 ;;
esac
[[ -n $KEYFILE && -z $VLM_API_KEY ]] && export VLM_API_KEY=$(cat "$KEYFILE")
[[ " ${ARGS[*]} " == *" --base-url "* ]] || ARGS+=(--base-url "$BASE")
[[ " ${ARGS[*]} " == *" --gpu "* ]] || ARGS+=(--gpu "$([[ $(uname) == Darwin ]] && echo native || echo gl-egl)")
TAG=""; for ((i=0; i<${#ARGS[@]}; i++)); do [[ ${ARGS[$i]} == --tag ]] && TAG=${ARGS[$((i+1))]}; done
mkdir -p runs
if [[ -n $TAG ]]; then
  .venv/bin/python -u -m agent.runner "${ARGS[@]}" 2>&1 | tee -a "runs/$TAG.log"
else
  .venv/bin/python -u -m agent.runner "${ARGS[@]}"
fi
