# Indoor review on A10
This is the authoritative Linux review build for residential-taxonomy-v3.1 (H01-H13). The old H01-H20 deployment remains a separate legacy API; do not overwrite it. The user requests all current indoor tasks and Subway in the unified 8092 review UI, each with Chinese and English rubrics. H14 plumbing was deleted and must not return.
Build with python3 scripts/build_indoor.py. Test paired clean/bug controls with python3 scripts/test_residential_revision.py dist/indoor-linux. Preserve all existing feedback and identity data when updating the review service.

All future source edits, builds, commandlets, tests and rendering happen here on A10. The Mac snapshot is stale. Shared review runtime and bilingual rubrics: ../review-service/releases/public-20260911. Read ../review-service/HANDOFF-UNIFIED.md before publishing. The build script pauses the shared review to protect running binaries; after verification use ../review-service/releases/public-20260911/publish.py.

Public entry is https://review.150-230-45-149.sslip.io/ through review-web.service (Caddy). Participants use a shared team code and selected name. No reviewer SSH tunnel is needed. Public TURN uses TCP/3478 and relay UDP/25000-25031; retain per-project SM5/SM6 profiles. Preserve state/participants.json and the participants table; never put the group access code in source or URLs. Read review-service/releases/public-20260911/PUBLIC-HANDOFF.md for the current rollout.

## Current H03 revision — 2026-09-13
H03 revision 33 is the oversized stove pot (StaticMeshActor_299), G3 / geometry.scale. Giant-chair and wider-chair proposals are superseded; never publish the rejected indoor-h03-width candidate. Current release is ../review-service/releases/indoor-h03-pot-20260913-v1. Use actual systemd/live configuration as authority instead of the historical public-20260911 paths above. See ../indoor-h03-pot-workspace/REVISION.md for verification and publication evidence. Preserve active reviews and all other environment changes.

## Current H09 and H15 — 2026-09-13
H09 revision 33 is now the missing shadow on the larger floor vase; the smaller vase retains a clear shadow. The lit positions near the fireplace are authoritative. H15 revision 1 is the new C1 bedroom door passing through a fixed storage box. H06 is unchanged; H14 remains deleted. The current source catalog contains H01-H13 plus H15. Published build: dist/indoor-door-vase-20260913-v3. Read ../indoor-door-workspace/REVISION.md and always resolve the live release from systemd before a later publication. Preserve the H03 stove pot and unchanged review compatibility aliases.

## Combined H09/H10 release — latest
Current published release: review-service/releases/indoor-h09-h10-20260913-v1; native binary in dist/indoor-h09-cabinet-20260913-v1. H09 revision 34 uses existing cabinet vase StaticMeshActor_925, with its cast shadow removed. The added floor vases and hidden template are removed; do not restore those rejected additions. H10 retains start_at_observation and its current revision 33; verified in the same binary with real walking. H15 and other tasks are preserved. Read ../indoor-h09-cabinet-workspace/REVISION.md; always resolve the actual live release to preserve concurrent UI updates.

## Cabinet E interaction — latest
Published release: review-service/releases/indoor-cabinet-interaction-20260913-v1, with matching Indoor dist. Existing cabinet door 2071 accepts E within 250 cm and 35 degrees with visibility; native upper-right HUD shows E Open cabinet / Close cabinet. Task definitions and prior review compatibility are preserved. See ../indoor-cabinet-interaction-workspace/REVISION.md. Always resolve actual live systemd state before publication.

## Narrower cabinet range — 2026-09-14
User found 250 cm / 35 degrees too generous. Current published Indoor distribution and review release: indoor-cabinet-range-20260914-v1. Cabinet thresholds are now 150 cm and 18 degrees; upper-right E hint unchanged. See ../indoor-cabinet-range-workspace/REVISION.md. Its deployment drain helper keeps a temporary cleanup supervisor alive while HTTP admission is stopped; Store.tick cannot drain external sessions after the supervisor itself has stopped.
