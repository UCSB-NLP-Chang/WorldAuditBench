# Ancient Chinese City on A10

Current update (2026-09-12): the website runs release `ancient-performance-20260912`
and game build `dist/ancient-stairs-lod-20260912`; all 23 ancient entries are revision 2.
The residence has 30.2 cm stair risers, exceeding the old 25 cm step limit. Ancient
maps now use 35 cm, and a real E + walk traversal test covers going inside and back
outside without jumping. The old setting fails this regression test.

Two NPC meshes now have additional reduced LODs. Published rendering arguments
are in `environments/ancient-chinese-city/streaming-settings.json`; preserve them
when creating future launch profiles. Output remains 1280×720, capped at 30 FPS.
The user authorized stopping the old standalone indoor demo: `unreal-auditor.service`
is stopped and disabled. The indoor review family remains available on the website.

Public browser verification: residence 30.1 FPS, tea house 27.8 FPS, market 22.3 FPS
with one reviewer; these measured views are not a three-user performance guarantee.
Browser E + W reached inside the doorway (y=7447.34), with separate reviewer PIDs
and same-process map switching verified. Thirty packaged tests, twenty restoration
cycles and eight render captures passed. QA submitted no reviews and removed its
temporary logins. Existing feedback, review history and evidence were preserved.
Evidence: `out/ancient-a10-review/performance-fix/public-report.json` locally and
`ancient-workspace/out/performance-fix` on A10.
Backup: `review-service/backups/ancient-performance-20260912-034059`.

The A10 workspace is authoritative: `/home/ubuntu/unreal-auditor/ancient-workspace`.
Do not edit or compile the old Mac playtest to update the website. Use SSH to edit,
run Unreal commandlets, compile, cook and render on A10.

The review family is `ancient`, displayed as **Ancient Chinese City**.
It contains three constrained scenes, three baselines and twenty injected bugs.

| Scene | Map suffix | Baseline | Bug IDs |
| --- | --- | --- | --- |
| Market street | Market | AB01 | A01, A04, A06, A07, A09, A11, A14, A20 |
| Tea house | TeaHouse | AB02 | A03, A05, A08, A12, A15, A18 |
| Residence entrance | Courtyard | AB03 | A02, A10, A13, A16, A17, A19 |

All maps are under `/Game/Auditor/AncientCity/`.
Public IDs are `unreal_ancient_city_baseline_01…03` and
`unreal_ancient_city_bug_01…20`. Internal IDs remain AB01–AB03/A01–A20.

The canonical region bounds, routes and task parameters are in
`environments/ancient-chinese-city/regions.json` and `tasks.json`.
`rubrics.bilingual.json` contains expected behavior, steps and criteria.
`scene-descriptions.json` supplies exactly the same bilingual description to
every variant of a scene. The website hides baseline rubrics.

Market: aim at the loose wicker basket and press E to lift/release it.
Residence entrance: aim at the closed door leaf and press E to open/close it.
Tea house: walking and visual inspection; no E interaction.
The original architecture, NPCs and animations remain. Each scene has collision
boundaries. A baseline removes all injected changes.

The current fifteen-subtype taxonomy is reused, including post-interaction
trajectory anomalies, Layout conflict, Purpose conflict and World-setting
conflict. This set uses fourteen subtypes; it does not invent a purpose fault
just to fill a quota. A20 adds the historical-setting mismatch. The pre-existing
Urban U045 explicitly remains outside the fifteen precise subtypes because its
static checker material is not view/distance-dependent; this integration does
not silently remap that task.

Authoring scripts on A10:
- `scripts/create_regions.py`: derives the three maps and embeds the catalog.
- `scripts/complete_rubrics.py`: bilingual rubric sidecar.
- `scripts/build_linux.py`: native Linux packaging; use a fresh isolated output.
- `scripts/test_packaged.py`: twenty behavior tests plus nine baseline tests.
- `scripts/test_reuse.py`: all twenty baseline → bug → baseline cycles.
- `scripts/render_packaged.py` and `render_details.py`: actual Vulkan screenshots.

The ground mesh's missing collision was repaired in the project copy.
Spawn/probe placement waits for editor mesh compilation and checks actual Pawn
capsule collision. A06 keeps its chopstick holder supported on the lowered
table. Basket trajectories use real contact callbacks; A17 requires seeing the
door, leaving while looking away, and returning without E.

Published binary:
`/home/ubuntu/unreal-auditor/ancient-workspace/dist/ancient-stairs-lod-20260912/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity`

SHA256: `a8f3fdc5615a0aea86266e515cdef97579d107530c6a108960b1b4154882345b`.

Runtime switching reloads an authored map inside the same process and restores
transient effects, physics and spawn. Separate reviewers always get separate
processes, even on the same task. Capacity stays at three people, sharing the
existing FIFO queue with Subway, Indoor and Urban.

Release: `review-service/releases/ancient-performance-20260912`.
The integration rebases on the current `core18-20260911` release and preserves
all 56 existing entries, all existing launch profiles, identities, feedback,
append-only review_history, evidence and events. Total: four families,
thirteen scenes, seventy bugs and nine baselines, 79 entries.

Deployment backup:
`review-service/backups/ancient-20260912-021556`.
Validation: 116 website tests; 29 packaged behavior/baseline tests; all twenty
same-process restoration tests. Render evidence covers all twenty bugs, three
baselines and corresponding clean views; the A06 support correction has its own
final-build screenshot. See A10 `out/tests-streaming2`, `out/reuse-streaming2`,
`out/render-packaged`, `out/render-final` and local
`out/ancient-a10-review`.

Website: https://review.150-230-45-149.sslip.io/


The published project enables PixelStreaming2, matching the existing UE5.6 web frontend and per-slot PixelStreamingConnectionURL. Final streaming deployment backup: `review-service/backups/ancient-streaming2-20260912-022900`.

The private runtime library directory also contains libnvcuvid.so.580.105.08 and its symlinks, extracted from the matching Lambda libnvidia-decode-580-server package. No system driver or system package was replaced. AVCodecs requires this alongside the existing encode library to enable hardware encoding. Provenance: `review-service/deps/nvdec-580.105.08/installation.json`.

Public canaries must only read review-ipc/response.json. Writing independent diagnostic commands there replaces the supervisor-owned acknowledgement and correctly causes runtime identity verification to fail. Use separate diagnostic processes for writable IPC tests.

Public HTTPS verification passed with two independent instances (PIDs 358970 and 358980). AB01 → AB02 → AB03 → A01 → A02 kept PID 358970 and the same iframe/video connection; the other reviewer remained unchanged. Keyboard messages were delivered. Both End session flows completed, all temporary logins were removed and no QA feedback was submitted. Postflight confirmed the original feedback, review_history and evidence fingerprints unchanged, SQLite integrity OK and zero active sessions. GPU encoder fallback warnings are absent with the matching private decode library. Public report: `ancient-workspace/out/public-report.json`. Disk after all build/QA artifacts: 330 GB used, approximately 1.1 TB available.


## Sparse NPC update — 2026-09-12

Current release: review-service/releases/ancient-sparse-npcs-20260912.
Current executable: ancient-workspace/dist/ancient-sparse-npcs-20260912/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity. Native executable hash is unchanged (a8f3fdc5615a0aea86266e515cdef97579d107530c6a108960b1b4154882345b); map/pak content changed. All 23 ancient task identities include the new content hashes and revision 3. Other families and rendering settings remain unchanged.

Each old regional map contained 162 NPC skeletal mesh components, including six walking-crowd generators. Regional maps now retain three authored NPC actors in Market, three in TeaHouse, and none in Courtyard. Unneeded population actors are removed from the authored maps; they are not view-dependent hidden actors. Existing retained poses/positions, task prop transforms/tags and the complete original Playtest are preserved. Reload verification confirms removed crowds do not respawn. Canonical policy: environments/ancient-chinese-city/npc-layout.json; editor helper scripts/npc_policy.py; create_regions.py applies the same policy during regeneration.

Source map backups: ancient-workspace/out/npc-reduction/map-backup. Layout/reload audit: out/npc-reduction/layout-report.json. Render captures: out/npc-reduction/render. Renderer samples after warmup: Market 23.0 FPS, TeaHouse 30.0 FPS, Courtyard 30.0 FPS. These are single-instance measured views, not a three-user guarantee.

One uncapped NullRHI stair test failed at the stair edge, while the rendered 30 FPS traversal passed. The identical executable/map also passed a dedicated NullRHI run capped at the published 30 FPS. Packaged tests now explicitly use the production 30 FPS cadence. Original diagnostic logs are preserved under out/npc-reduction/tests; production-cadence results are under tests-30fps.

Deployment backup: review-service/backups/ancient-sparse-npcs-20260912-040401. Systemd drop-in: zz-ancient-sparse-npcs.conf. The old standalone indoor service remains disabled by the user's instruction.

Final verification: 30/30 production-cadence packaged tests pass; 4/4 render checks pass. Public website test passed through all three baselines, walked through the residence door/stairs using browser E/W, retained the runtime on same-family switches, and verified a separate second reviewer. No QA reviews submitted; temporary logins removed. Protected review records remain byte-for-byte unchanged by fingerprint. See out/npc-reduction/public-report.json and postflight.json.

2026-09-12 taxonomy and basket update: live website is review-service/releases/taxonomy-temporal-era-20260912; Ancient revision 4 uses dist/ancient-basket-20260912. Basket starts stationary, E can lift/release repeatedly from its current location, the player capsule cannot kick it during the drop, and clean baskets settle and regain solid collision. A09 retains intentional repeated rebounds; A14 retains disappearance. Behavioral tests 30/30, restoration cycles 20/20, rendered checks 3/3 passed. Preserve 30 FPS settings, sparse NPC policy, stair fix and Urban public IDs 01-18. Taxonomy version user-2026-09-12-temporal-era keeps all five categories and fifteen stable subtype keys: Temporal consistency / 时间一致性; Historical anachronism / 时代设定冲突; Visual consistency still includes shadow/lighting relational inconsistencies. Layout and Purpose remain. Historical review payloads are preserved. Future releases must use this current website release as their base.

2026-09-12 scene-context update: website release scene-semantics-context-20260912; taxonomy user-2026-09-12-scene-semantics names the fifth category Scene semantic consistency / 场景语义一致性. All fifteen subtype keys and assignments are unchanged. Three shared bilingual Ancient descriptions now establish premodern historical daily life (not a present-day film set/exhibition/theme park), distinguish fixed furnishings and movable paper umbrellas, and explain basket/door E interactions and expected normal motion. Authoritative descriptions: ancient-workspace/environments/ancient-chinese-city/scene-descriptions.json. Public context and read-only physics inventory are in PUBLIC_CONTEXT.md and out/scene-context/physics-inventory.json. This is a metadata-only update: all binaries, maps, task revisions, hashes, runtime profiles and existing reviews are preserved. Ancient stays revision 4 on dist/ancient-basket-20260912. Use this current website as the base for subsequent releases.

2026-09-12 independent-door/push release: website ancient-push-independent-doors-20260912; Ancient revision 5, binary dist/ancient-push-independent-doors-20260912, SHA256 37e53e5da40d471601f215f8a9aa6df70b2a0229becfb61dc6049cc052c904c1. User explicitly requested one leaf initially open and the other closed. E toggles only the aimed-at leaf, never both; both swing inward with matching exterior faces, using mirrored partner geometry around its existing hinge. Basket E is now one horizontal 140 cm/s impulse, with no vertical lift/teleport. A09 retains abnormal repeated rebounds after the same push; A17 affects only the initially closed leaf; A19 blocks the initially open half. The shared concise descriptions and A09/A17/A19 bilingual rubrics match these behaviors. Native tests 30/30, restoration cycles 20/20, rendered checks 7/7 passed; evidence out/push-doors. Preserve sparse NPCs, 30 FPS settings, stair fix, taxonomy and Urban numbering. This release is the base for future site changes.

2026-09-12 concise rubric update: current website release ancient-concise-rubrics-20260912. All 20 Ancient bug tasks show one paragraph with two sentences in each language: anomaly, then normal behavior. No steps, repeated section headings or details expander in the Ancient rubric UI. Other families and baseline visibility are unchanged. Canonical concise-rubrics.json overrides criteria/expected in complete_rubrics.py; detailed steps remain internal metadata for existing tooling and are not displayed. Native build, hashes and task revisions remain unchanged (Ancient revision 5). Forty bilingual task views and all three baseline views passed browser checks, with API text verified.
