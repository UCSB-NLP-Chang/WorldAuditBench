# Indoor AC and cola revision

User request: A24 must be a recognizable white wall-mounted indoor split air conditioner. A21 must be two or three conspicuous cola bottles, replacing the tiny food tin. The previous MAR condenser is explicitly rejected. Published to A10 as `ancient-indoor-cola-20260913-v3`.

Selected candidates, visually inspected in the browser:

- Indoor air conditioner unit, Rylae Shylna (@risteralline): https://sketchfab.com/3d-models/indoor-air-conditioner-unit-d93c5557a9ba46afbb00e35f48343077. White indoor unit with vent and temperature display; 528 triangles; CC BY 4.0; creator lists UE 5.4.3 and PBR textures.
- Coca Cola Bottle, Yanez Designs: https://sketchfab.com/3d-models/coca-cola-bottle-69dc15f696f04e85a11df4ec4658d907. Dark glass bottle with a prominent red Coca-Cola label; approximately 2,900 triangles; CC BY 4.0. Arrange three bottles on the tea table, labels facing the accessible viewing area.

Sketchfab registration completed with explicit user approval on 2026-09-12. Both original FBX archives were downloaded using the logged-in browser and transferred to A10 `source-additions/indoor-cola-v3`. Its `manifest.json` records creator, license URL, source URL and SHA256. No paid purchase was needed.

Authoritative A10 workspace: `/home/ubuntu/unreal-auditor/ancient-workspace`. Current live release when inspected: `configuration-tasks-20260913-v2`, Ancient binary `dist/ancient-configuration-20260913-v3`. Preserve A18 and all other configuration edits, 253 global entries, user reviews, and current taxonomy ordering. Read the current live state again before publication; increment only A21/A24 revisions from their current values.

Read-only wall probe: `scripts/ancient/probe_indoor_wall.py`, copied to A10 `scripts/probe_indoor_wall.py`. Outputs in `out/indoor-cola-v3`. It tests nine contact points behind a 90 x 30 cm wall plate, never saves maps. Current native mounted-object check assumes bounds center is the contact point; extend with an optional local back-contact anchor for a thick indoor unit, preserving the newspaper's default behavior.

After downloads: record source/license hashes; import to fresh asset directories; author only A21 and A24, persist updated generation recipes; inspect actual rendered front/normal-spawn views; run native/restoration checks; build to a fresh immutable directory; rebase release on current live state and publish with existing acceptance/source guards; verify public playback and task switching and close only the dedicated QA session.


Implementation now authored and visually checked in editor: A21 uses three independent copies of the original bottle at 28 cm height, with separate glass and label materials. A24 uses an approximately 86 cm wide unit mounted on the solid wall above the entrance, facing into the room. Mounted support uses the rear local anchor; the newspaper retains its original check. Native tests also check both additional bottles touch the tabletop. Only A21 and A24 catalog definitions changed. `author_ac.py` and configuration `author_a21.py` now invoke `author_indoor_cola.py` to preserve this choice on regeneration. Native checks 34/34, restoration cycles 24/24, five packaged renders, 133 service checks and bug-type ordering across all 253 entries / 13 families passed. Publication preserved existing review records. Live browser QA passed seven task switches on the same process and iframe, both updated bilingual rubrics, attribution delivery, video health and mobile layout. A21 and A24 are revision 3. Public mouse-look verification also passed: turning and looking upward shows the white indoor AC on the entrance wall. All three owned QA sessions were closed, no review records were submitted, and the temporary login was revoked.


Published executable SHA256: `6ca2d615cdc5e0159428413ac015ef022483825f0ba9121a35282b0a0590087a`. Immutable build: `dist/ancient-indoor-cola-20260913-v3`. Public creator attribution is linked from the site footer at `/ancient-prop-attributions.md`. Reports: A10 `out/indoor-cola-v3/acceptance.json`, `publish.log`; release staging `deployment-report.json`.
