# Indoor H10 initial observation

The new H10 start places the player at `[-1090, -710, 239]`, facing the floor plant next to the television. The ordinary visibility and near-distance checks establish the initial observation; no disappearance state is forced. Leaving beyond 310 cm while facing away, then returning within 210 cm and looking at the plant, remains the trigger.

Implementation and builds run on A10. Both `ResidentialScenario.cpp` and the embedded `ResidentialTaskRevision.inl` must include the opt-in `start_at_observation` setting; the embedded catalog supersedes map metadata.

Ready candidate: `/home/ubuntu/unreal-auditor/indoor-h10-start-workspace/indoor-h10-start-20260913-v4`. Binary: `/home/ubuntu/unreal-auditor/indoor-workspace/dist/indoor-h10-start-20260913-v2`. Rebased on the newly published `indoor-door-vase-20260913-v3`; preserve its H09 vase and H15 door tasks, all 257 entries, and the visibility taxonomy update. Earlier H10 v1 lacks the embedded flag and must not be published. The isolated v3 build was superseded and stopped after the other indoor changes were published.

Passed: 28 paired native checks, initial-observation assertions before automated movement, cold start and same-process return, 13 restoration cycles, real walking away and returning in both control and bug conditions, and 142 service tests. Screenshots visually confirm a centered, visible plant at the start and its absence on return in the bug condition.

A10 evidence: `indoor-h10-start-workspace/out/acceptance.json`, `validation.json`, `walk-results.json`. Local images: `out/indoor-h10-start/initial.png` and `returned.png`.

Publication pending an idle shared review service or explicit authorization to end active sessions. The publish script checks current source/state/candidate hashes and backs up review records/configuration before switching.

Superseded publication instructions: H10 is now published together with the corrected existing-cabinet-vase H09 in review-service/releases/indoor-h09-h10-20260913-v1. Use the combined native build dist/indoor-h09-cabinet-20260913-v1 and see ../indoor-h09-cabinet-workspace/REVISION.md. Do not republish the old floor-vase H09 metadata from this workspace.
