#!/bin/bash
# VLA arm with the compiled Open-P2P server (~7.5 GB GPU each): the three.js batches (list A then B, one process) and
# the Unreal batch (second process) run CONCURRENTLY on the A10.  Every stage is resumable (--skip-done).
# Usage: bash scripts/vla_run_parallel.sh        (logs: runs/vla-run-threejs.log, runs/vla-run-ue.log, driver logs per batch)
cd /home/ubuntu/game-auditing
export HF_HOME=/home/ubuntu/tools/hf_cache
export TAG=${TAG:-vla-threejs-v2} UE_TAG=${UE_TAG:-vla-ue} NUDGE=${NUDGE:-40} P2P_EAGER=${P2P_EAGER:-0}
EAGER=$([ "$P2P_EAGER" = 1 ] && echo --eager)
setsid nohup bash -c "
  for L in A B; do
    echo \"\$(date -u +%FT%TZ) three.js list \$L start\"
    .venv/bin/python -m harness.vla_explore --configs \"\$(cat runs/vla-threejs-list\$L.txt)\" --seeds 1 --ticks 1200 \
        --tag $TAG --idle-nudge $NUDGE $EAGER --gpu 0 --skip-done > runs/$TAG-driver\$L.log 2>&1
    echo \"\$(date -u +%FT%TZ) three.js list \$L done (exit \$?)\"
  done" > runs/vla-run-threejs.log 2>&1 < /dev/null &
echo "three.js runner started (pid $!)"
sleep 420   # let the first server finish compiling before the second one starts (compile peaks the GPU)
setsid nohup bash -c "
  echo \"\$(date -u +%FT%TZ) unreal batch start\"
  .venv/bin/python -m harness.vla_ue --tasks @scripts/vla-lists/vla-ue-list.txt --ticks 1200 --tag $UE_TAG --idle-nudge $NUDGE $EAGER --gpu 0 --skip-done \
      > runs/$UE_TAG-driver.log 2>&1
  echo \"\$(date -u +%FT%TZ) unreal batch done (exit \$?)\"" > runs/vla-run-ue.log 2>&1 < /dev/null &
echo "unreal runner started (pid $!)"
