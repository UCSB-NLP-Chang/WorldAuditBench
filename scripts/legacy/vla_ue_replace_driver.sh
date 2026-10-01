#!/bin/bash
# Replace one running Unreal VLA driver with a fresh one (new code / settings): kill it by PID, stop the Unreal instance it
# orphaned, release the claim of the episode it was in (it is re-run), relaunch under the same name.
# Usage: bash scripts/vla_ue_replace_driver.sh <driver-pid> <name> [driver args, e.g. --p2p-host rain2]
cd /home/ubuntu/game-auditing
TAG=${TAG:-vla-ue-v1}
pid=$1; name=$2; shift 2
if kill -0 "$pid" 2>/dev/null; then kill "$pid"; sleep 3; kill -9 "$pid" 2>/dev/null; echo "stopped driver $name ($pid)"; fi
sleep 1
for up in $(ps -eo pid,ppid,cmd | awk '$2==1 && /[A]uditorServe/ && /ue-state\/ep-/ {print $1}'); do
  task=$(tr '\0' '\n' < /proc/$up/cmdline 2>/dev/null | grep -o 'ue-state/ep-[A-Za-z0-9]*' | sed 's#.*/ep-##')
  kill "$up" 2>/dev/null; sleep 2; kill -9 "$up" 2>/dev/null; echo "stopped orphaned Unreal instance $up (task ${task:-?})"
  if [ -n "$task" ] && [ ! -f "runs/$TAG/$task/meta.json" ]; then rm -f "runs/$TAG/$task.claim"; rm -rf "runs/$TAG/$task"; echo "released $task"; fi
done
TAG=$TAG bash scripts/vla_ue_driver.sh "$name" "$@"
