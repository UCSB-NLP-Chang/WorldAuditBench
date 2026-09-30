#!/bin/bash
# One three.js VLA driver over the shared 87-config list (claim mode: any number of drivers may run concurrently).
# Usage: bash scripts/vla_threejs_driver.sh <name> [extra vla_explore args, e.g. --p2p-host rain2]
cd /home/ubuntu/game-auditing
export HF_HOME=/home/ubuntu/tools/hf_cache
NAME=$1; shift
TAG=${TAG:-vla-threejs-v2}; NUDGE=${NUDGE:-40}
setsid nohup .venv/bin/python -m harness.vla_explore --configs "$(cat scripts/vla-lists/vla-threejs-list.txt)" --seeds 1 --ticks 1200 \
    --tag "$TAG" --idle-nudge "$NUDGE" --gpu 0 --skip-done --claim "$@" > "runs/$TAG-driver-$NAME.log" 2>&1 < /dev/null &
echo "driver $NAME started (pid $!), log runs/$TAG-driver-$NAME.log"
