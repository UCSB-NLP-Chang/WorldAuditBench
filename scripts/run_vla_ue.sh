#!/bin/bash
# VLA arm, Unreal: Open-P2P 1.2B explores the 126 held-out Unreal tasks (scripts/vla-lists/vla-ue-list.txt) on this machine's A10 through
# the paused AuditorRemote step interface; one episode each, 1200 ticks x 50 ms; resumable (--skip-done).
# Usage: bash scripts/run_vla_ue.sh [list-file]
cd "$(dirname "$0")/.."
export HF_HOME=/home/ubuntu/tools/hf_cache
LIST=${1:-scripts/vla-lists/vla-ue-list.txt}
TAG=${TAG:-vla-ue}
NUDGE=${NUDGE:-40}
nohup .venv/bin/python -m agent.vla.vla_ue --tasks "@$LIST" --ticks 1200 --tag "$TAG" --idle-nudge "$NUDGE" --eager --gpu 0 --skip-done \
    > "runs/$TAG-driver.log" 2>&1 &
echo "unreal driver started (pid $!), log runs/$TAG-driver.log"
