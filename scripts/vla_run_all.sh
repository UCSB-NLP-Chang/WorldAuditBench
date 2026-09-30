#!/bin/bash
# The whole VLA arm, sequentially in ONE process (one Open-P2P 1.2B server fits the A10 at a time):
#   three.js list A -> three.js list B -> Unreal 126 tasks.   Every stage is resumable (--skip-done).
# Usage: setsid nohup bash scripts/vla_run_all.sh > runs/vla-run-all.log 2>&1 < /dev/null &
cd /home/ubuntu/game-auditing
export HF_HOME=/home/ubuntu/tools/hf_cache
TAG=${TAG:-vla-threejs-v2}; UE_TAG=${UE_TAG:-vla-ue}; NUDGE=${NUDGE:-40}
EAGER=$([ "${P2P_EAGER:-1}" = 1 ] && echo --eager)   # P2P_EAGER=0 -> torch.compile server (one compile per batch)
stamp () { date -u +%FT%TZ; }
for L in A B; do
  echo "$(stamp) three.js list $L start" 
  .venv/bin/python -m harness.vla_explore --configs "$(cat scripts/vla-lists/vla-threejs-list$L.txt)" --seeds 1 --ticks 1200 \
      --tag "$TAG" --idle-nudge "$NUDGE" $EAGER --gpu 0 --skip-done > "runs/$TAG-driver$L.log" 2>&1
  echo "$(stamp) three.js list $L done (exit $?)"
done
echo "$(stamp) unreal batch start"
.venv/bin/python -m harness.vla_ue --tasks @scripts/vla-lists/vla-ue-list.txt --ticks 1200 --tag "$UE_TAG" --idle-nudge "$NUDGE" $EAGER --gpu 0 --skip-done \
    > "runs/$UE_TAG-driver.log" 2>&1
echo "$(stamp) unreal batch done (exit $?)"
