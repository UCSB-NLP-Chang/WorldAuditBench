#!/bin/bash
# After the current three.js drivers exit, run one more driver over the full list (claim + skip-done) to pick up any
# episode that was claimed by a driver that died (e.g. a server OOM) and never finished.
cd /home/ubuntu/game-auditing
for pid in "$@"; do while kill -0 $pid 2>/dev/null; do sleep 60; done; done
echo "$(date -u +%FT%TZ) all drivers exited; clearing orphan claims" >> runs/vla-chain.log
for c in runs/vla-threejs-v2/*.claim; do d=${c%.claim}; [ -f $d/meta.json ] || { rm -f "$c"; rm -rf "$d"; echo "  cleared $(basename $d)" >> runs/vla-chain.log; }; done
bash scripts/vla_threejs_driver.sh sweep >> runs/vla-chain.log 2>&1
echo "$(date -u +%FT%TZ) sweep driver started" >> runs/vla-chain.log
