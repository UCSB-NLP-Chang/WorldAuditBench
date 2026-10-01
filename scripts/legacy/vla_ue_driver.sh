#!/bin/bash
# One Unreal VLA driver over the shared 126-task list (claim mode: any number of drivers may run concurrently, each with its own
# Open-P2P 1.2B server - local GPU or --p2p-host rain2).  Environments = the AWS review release unreal-area-3x-20260918 mirrored
# locally (reports/ue-aws-profiles-20260918.json: same builds, same exploration policy = frozen farther spawn + 3x bounds).
# Usage: bash scripts/vla_ue_driver.sh <name> [extra vla_ue args, e.g. --p2p-host rain2]
cd /home/ubuntu/game-auditing
export HF_HOME=/home/ubuntu/tools/hf_cache
NAME=$1; shift
TAG=${TAG:-vla-ue-v1}; NUDGE=${NUDGE:-40}; LIST=${LIST:-scripts/vla-lists/vla-ue-list.txt}
PROFILES=${PROFILES:-reports/ue-aws-profiles-20260918.json}
export VLA_UE_MAXFPS=${VLA_UE_MAXFPS:-20}   # render cap while several games share the A10 (fixed time step: same sim/observation)
setsid nohup .venv/bin/python -m harness.vla_ue --tasks "@$LIST" --ticks 1200 --tag "$TAG" --idle-nudge "$NUDGE" --gpu 0 \
    --profiles "$PROFILES" --skip-done --claim "$@" > "runs/$TAG-driver-$NAME.log" 2>&1 < /dev/null &
echo "driver $NAME started (pid $!), log runs/$TAG-driver-$NAME.log"
