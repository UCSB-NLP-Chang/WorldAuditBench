#!/bin/bash
# Restart the Unreal VLA batch drivers with the current code: stop the drivers and their Unreal instances, release the claims of
# unfinished tasks (they are re-run), stop leftover model servers on rain2, relaunch r1/r2 (rain2 inference) and l1 (local).
# Usage: bash scripts/vla_ue_restart.sh [TAG]   (default vla-ue-v1)
cd /home/ubuntu/game-auditing
TAG=${1:-${TAG:-vla-ue-v1}}
pids=$(ps -eo pid,cmd | awk -v t="--tag $TAG" '/[h]arness.vla_ue / && index($0, t) {print $1}')
[ -n "$pids" ] && { echo "stopping drivers: $pids"; kill $pids; sleep 4; kill -9 $pids 2>/dev/null; }
upids=$(ps -eo pid,cmd | awk '/[A]uditorServe/ && /ue-state\/ep-/ {print $1}')
[ -n "$upids" ] && { echo "stopping Unreal instances: $upids"; kill $upids; sleep 4; kill -9 $upids 2>/dev/null; }
for i in 1 2 3 4 5 6; do n=$(timeout 20 ssh -o BatchMode=yes rain2 'nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l' 2>/dev/null); [ "${n:-0}" = 0 ] && break; sleep 5; done
[ "${n:-0}" != 0 ] && { echo "rain2 still has $n GPU processes; stopping leftover p2p servers"; timeout 20 ssh -o BatchMode=yes rain2 'pkill -f "[p]2p_server.py"' ; sleep 3; }
for c in runs/$TAG/*.claim; do [ -e "$c" ] || continue; t=$(basename "$c" .claim); [ -f "runs/$TAG/$t/meta.json" ] || { rm -f "$c"; echo "released claim $t"; }; done
TAG=$TAG bash scripts/vla_ue_driver.sh r1 --p2p-host rain2; sleep 1
TAG=$TAG bash scripts/vla_ue_driver.sh r2 --p2p-host rain2; sleep 1
TAG=$TAG bash scripts/vla_ue_driver.sh l1
