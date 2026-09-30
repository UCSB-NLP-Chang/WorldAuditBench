# Indoor cabinet interaction

User requested a more forgiving E interaction for the existing bedroom cabinet and a contextual action prompt in the upper-right of the game image.

The cabinet door (StaticMeshActor_2071) accepts E within 250 cm and a 35-degree half-angle toward either the closed-panel anchor or the current panel center. Visibility tracing blocks interaction through solid scenery. Direct room-door and mug targets retain their prior priority. The HUD and E action use the same target resolver. The upper-right card, below the minimap, shows an E keycap and Open cabinet / Close cabinet according to the next action. The prompt is part of the native rendered image, visible to both people and visual agents.

Authoritative source edits and build happened on A10. Original source files are in backup/. Fresh binary: ../indoor-workspace/dist/indoor-cabinet-interaction-20260913-v1. All task definitions and criteria are unchanged. Preserve H03 pot, H09 existing cabinet vase, H10 observation start, H15 room door, and absence of H14. Existing review versions are retained as compatibility aliases.

Verification: out/acceptance.json; 28 paired native scenarios, 14 same-process restoration cycles, 155 review-service tests, and 47 owners checked for review retention. A real agent walked from spawn, operated the cabinet at 25 degrees off-center, saw the Open/Close prompt switch and panel move, and was rejected when facing away. An additional real walking test reached within 230 cm of the cabinet below the solid floor and was correctly denied. The original H15 room door still opened and closed through the normal E action. Screenshots of both cabinet states were visually reviewed.

Guarded deployment scripts copy the actual live service and retain concurrent UI changes, reviewers, feedback and per-project rendering profiles. See out/deployment-report.json for publication status and rollback backup. Public browser QA submits no feedback and removes its temporary login afterward.
