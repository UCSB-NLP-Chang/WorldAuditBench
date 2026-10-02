#!/bin/bash
# VLA arm, three.js: Open-P2P 1.2B explores the 87 held-out cases (reports/eval-task-sets-2026-09-17.json), one episode each,
# 1200 ticks x 50 ms of simulated time (virtual clock on the standalone pages), full frame every 0.5 s + poses + video.
# Two drivers in parallel (lists A/B, runs/vla-threejs-list{A,B}.txt), each with its own P2P server; resumable (--skip-done).
# Usage: bash scripts/run_vla_threejs.sh [A|B|both]
cd "$(dirname "$0")/.."
export HF_HOME=/home/ubuntu/tools/hf_cache
TAG=${TAG:-vla-threejs-v2}   # v2: idle-nudge wrapper on (v1 = runs/vla-threejs, list A only, no nudge)
NUDGE=${NUDGE:-40}
which=${1:-both}
start () {  # list-letter
  local L=$1
  nohup .venv/bin/python -m agent.vla.vla_explore --configs "$(cat scripts/vla-lists/vla-threejs-list$L.txt)" --seeds 1 --ticks 1200 \
      --tag "$TAG" --idle-nudge "$NUDGE" --eager --gpu 0 --skip-done > "runs/$TAG-driver$L.log" 2>&1 &
  echo "driver $L started (pid $!), log runs/$TAG-driver$L.log"
}
[ "$which" = A ] || [ "$which" = both ] && start A
[ "$which" = B ] || [ "$which" = both ] && { sleep 40; start B; }
