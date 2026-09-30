# H09 — existing cabinet vase

Published combined release: review-service/releases/indoor-h09-h10-20260913-v1. Native distribution: indoor-workspace/dist/indoor-h09-cabinet-20260913-v1. H09 revision 34 uses the original cabinet vase/foliage StaticMeshActor_925 beside the fireplace. Its transform, mesh, materials and collision are retained. The treatment removes its cast shadow from the cabinet top and wall; the matching control retains the clear shadow. The other original cabinet vase StaticMeshActor_919 is unchanged.

The custom floor-vase scenario and hidden template have been removed from all region maps. No new vase is spawned. H15 remains the previously published bedroom-door/box C1 task; H03 remains the stove pot; H06 is unchanged and H14 remains deleted.

All Unreal work is remote in ../indoor-workspace. Candidate distribution: ../indoor-workspace/dist/indoor-h09-cabinet-20260913-v1. Earlier H09 floor-vase builds are superseded and must not be republished.

Use scripts/prepare.py to copy the actual live release and preserve all other tasks, scripts/verify.py to validate review continuity, and scripts/acceptance.py to check the native evidence. scripts/deploy_authorized.py performs guarded publication using the prior explicit authorization for this H09 update, backs up the database, finishes session cleanup with HTTP admission stopped, and invokes the rollback-capable publisher. Never print private runtime config or temporary credentials.

The final evidence is in out/acceptance.json and out/validation.json. Browser smoke testing uses a dedicated temporary technical login and scripts/indoor-h09-cabinet-public.cjs on the Mac. Revoke the login and close its sessions afterwards; do not submit feedback.

Status: published after the user explicitly requested publishing H09 and H10 together. Includes the H10 start-at-observation behavior and preserves the material-progress review UI. Publication checks passed for all protected review/identity tables. Public browser smoke test passed for H09, H10, H15 and HB03: live video, H10 starting position and same-process switching verified. No feedback submitted; technical session closed and temporary login revoked.

H10 was verified in this same native binary: cold start and same-process return begin at the visible plant; actual walking away and returning keeps the plant in the control and removes it in the bug condition. The combined release passed 155 service tests, 28 paired native checks, 2 H09 rendered checks, 6 region route checks and 14 restoration cycles.
