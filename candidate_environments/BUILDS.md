# Built environments (distributed out of git)

The six environments are single-file HTML builds (6-71 MB each): the four candidate scenes plus the two harness scenes (house, Sponza) packed by `tools/pack_harness_page.py`. Git only tracks their
sources under `src/<env>/` (build scripts, manifests, upstream source copies, runtime layers); the built
files, the v1 originals (`src/<env>/orig_v1_*.bak`) and the downloaded Poly Haven assets (`assets/`) are
ignored (see the repo `.gitignore`). Every rebuild would otherwise add ~130 MB to the history.

## Current builds (2026-09-16c: clean review view)

Canonical copy: GitHub release **envs-2026-09-16c** (tag on the source commit these builds came from):
https://github.com/KimperYang/game-auditing/releases/tag/envs-2026-09-16c - 6 environment files + `bugs.html` + `SHA256SUMS`,
byte-identical to what the review website serves from `/home/ubuntu/unreal-auditor/threejs/releases/envs-2026-09-16c/site/`
(`threejs-environments.service`); the `envs-2026-09-16b`, `envs-2026-09-16`, `envs-2026-09-15` and `envs-2026-09-12` release
directories are kept next to it on the server.  Fetch with `gh release download envs-2026-09-16c -R KimperYang/game-auditing`
(then `sha256sum -c SHA256SUMS`).  Built the same way as 2026-09-15 (see below); this release also carries every change of
the review rounds 2-4 (2026-09-15, 2026-09-16, 16b), which were only published to the review server before.

**16c** changes nothing about the cases: it makes the review site's view match the agent's observation.  The agent only ever
receives the WebGL canvas (`harness/bridge.py` -> `window.__env.act` -> `canvas.toDataURL` in `env/core.js` and
`src/common/harness_page.js`; the only thing composited into a frame is the 1.5 s "edge of the explorable area" notice), while
the review pages used to show their own chrome under `?noui=1`: the packed Sponza/House menu card (title, case description,
"Show bug answers", "Enter world"), the reef observer panel (Resume / Back to start / Leave the water, key hints) and DOM
vignette, the cottage day-cycle buttons, Credits, WASD hints and the camera-distance slider, the "Constrained area" badge on
the reef/cottage/wilderness pages, and keys the agent does not have (V answer beacons / third person, Space jump, R weather
shift or Shift+R scenario restart, T HUD, ~ console).  Every page now carries the shared block
`src/common/noui_block.html` (injected by all build scripts and the release relayer through `src/common/noui.py`): under
`noui` every overlay is hidden and those keys are swallowed, so a reviewer sees the world exactly as the agent does, plus the
same transient boundary notice.  The packed pages take the pointer on a click on the view.  Audited with
`tools/review_clean_audit.py` (0 visible DOM elements besides the canvas on all six pages, blocked keys leave the world
state unchanged).

**Review-site versioning of 16c.** The review site labels a review "Current version" only when its
(revision, sha256, build_sha256) equals the task's current tuple; anything else is "Previous versions" (earlier build,
still counting, or an older revision).  Every page rebuild since 2026-09-15 had given all tasks a new tuple although
most tasks' content had not changed, so nearly every review was labelled "earlier build" (after the first 16c manifest
no review on a live task was "current").  Since 2026-09-16 (coordinator release `threejs-envs-20260916-v5`,
`envs-2026-09-16c/pin_content_versions.py` + `publish_pinned.py`) every task's current tuple is its **last content
change** - the earliest known tuple carrying its current revision: revision-1 tasks point at the 2026-09-12 build,
tasks revised on 2026-09-15 at that build, the three revision-3 tasks at the 2026-09-16 build - and all later tuples
are compatibility aliases.  Acceptance is unchanged; the site now shows 161 reviews as "Current version", 10 as "earlier build"
(made on a later rebuild of an unchanged task) and 58 on older revisions (latest submission per reviewer and version).  The hash of the page actually served is the
informational field `page_sha256`, `package_id` names 16c.  Rule from now on: a page-only rebuild (no case, rubric or
answer change) keeps the content version; only a content change (revision bump) moves the version tuple and, with it,
the reviews.  (`threejs-envs-20260916-v3`, file-hash versions, and `-v4`, pinned to 16b, were live for a few hours each.)

**16b** (2026-09-16, after the owner's re-review of the round-3 fixes) retired three more cases: wt03 giant fish (still clipped
through the other schools), wt13 boulder position reset (floated at its second spot) and wl13 pine position reset (too hard
to notice); the reef fish-separation tweak made for wt03 was reverted, so the clean reef is the 2026-09-12 behaviour again.
16b page hashes (`envs-2026-09-16b/site/SHA256SUMS`): sponza `fa73824e…`, cottage `c4d70389…`, airfield `22a5285d…`, house
`55f98610…`, reef `400cbc73…`, wilderness `99deb3a4…`.

What changed (answers to the third review round of 2026-09-15/16, the owner's re-review of the revised tasks; details in
`reports/threejs-review-20260915.md`, section "Round 3"):

* **Retired ("宁缺毋滥")**: sp03 oversized pot (an oversized pot is not a definite bug at 1.6x or 2.8x), wt04 double-spawned
  rock set (reads as a floating rock), wt10 rock invisible from behind (not findable), wl04 double-spawned boulder (low-poly
  boulders overlapping read as one rock), ct16 missing front door (the doorway is lower than the walker, so the leftover door
  collision reads as the head hitting the lintel).  Removed from the configs, the task lists (`harness/tasks.py`) and the site.
* **Sponza**: sp02 pot lies tipped 65 degrees with its base centre at floor level - half sunk, half sticking out.
* **Reef**: (16: wt03 giant fish kept the school at a distance; wt13 armed from the start lane) - both retired in 16b.
* **Airfield**: af15 heap is solid (static box).
* **Wilderness**: wl12 = the boulder next to the start unloads once you are 16 m away (collider removed too); (16: wl13 = the
  tall pine jumped 10 m after a leave-and-return - retired in 16b).

| file | size | sha256 | notes |
|---|---|---|---|
| `00_sponza_constrained.html` | 70.8 MB | `53b81a10954b43b4...` | Sponza atrium, the SP suite (15 cases; sp03 retired) - packed harness page (`tools/pack_harness_page.py --family sponza`) |
| `01_mistwood_cottage_constrained.html` | 33.5 MB | `03905f31914bc725...` | Mistwood Cottage (CT suite, 17 cases; ct16 retired) - `relayer.py cottage` over the 2026-09-12 build |
| `03_sketchbook_airfield_constrained.html` | 58.1 MB | `28d9307e103c505e...` | Sketchbook airfield (AF suite, 19 cases) - `relayer.py sketch` over the 2026-09-12 build |
| `09_sims_house_builder_constrained.html` | 26.7 MB | `060a64d55ed9b23f...` | Family house (HS suite, 16 cases) - packed harness page (`tools/pack_harness_page.py --family house`) |
| `10_beautiful_water_clean_constrained.html` | 11.7 MB | `ecc243d6f32b3166...` | Reef dive (WT suite, 13 cases; wt03/wt04/wt06/wt10/wt13 retired) - `relayer.py water` over the 2026-09-12 build |
| `13_beyond_fable_wilderness_constrained.html` | 5.8 MB | `a889c2b6605b2678...` | Beyond Fable wilderness (WL suite, 16 cases; wl04/wl13 retired) - `python3 src/fable/build.py` (vite) |
| `bugs.html` | 0.4 MB | `85931b45f5b421e1...` | one card per case of every environment (`tools/make_bug_index.py`) |

Superseded: **envs-2026-09-15** (2026-09-16: the third review round above) and everything older.

## Builds 2026-09-15 (superseded)


Canonical copy on the review server: `/home/ubuntu/unreal-auditor/threejs/releases/envs-2026-09-15/site/` (served to the review
website by `threejs-environments.service`); the previous release directory `envs-2026-09-12` is kept untouched next to it.
Built on the review server from this repository's sources; the Sponza and house pages were re-packed from source
(`tools/pack_harness_page.py`, assets restored from the previous builds' embedded stores), the wilderness page rebuilt with
vite (Node 22 in `/home/ubuntu/tools/node`), and the reef / cottage / airfield pages by re-injecting the edited runtime
layers into the previous builds (the upstream asset packs are not on that machine; the builds embed the layer sources
verbatim, so the result equals a full rebuild - `relayer.py` in the release directory).

What changed in this release (answers to the second human review round of 2026-09-13/14; per-case decisions and reviewer
quotes in `reports/threejs-review-20260915.md`):

* **Wilderness (WL)**: with `?bug=` the page now always uses world seed 7 - the review site's `&seed=5` had loaded a different
  world in which the position-authored cases did not exist. wl02 pine tipped 35 degrees into the meadow (was sunk only);
  wl04 copy shifted 3.2 m, turned and tipped; wl15 heap tightened; every WL rubric now gives distance and direction from the start.
* **Sponza (SP)**: sp02 pot tipped 42 degrees / sunk 0.32 m; sp03 pot 2.8x (was 1.6x) and clear of its column; sp15 heap of
  tilted, interpenetrating copies (`mesh_pile` gained per-copy `rot` / `scale`).
* **House (HS)**: hs02 stool tipped 34 degrees and sunk; hs10 culls the throw pillows together with the sofa.
* **Reef (WT)**: wt03 fish 9x (was 3x); wt04 copy shifted, turned, tipped and lifted; wt05 wall 18 m wide; wt10 carrier = the
  big boulder east of the reef centre; wt12 unloads the landmark mossy rock set (collider too); wt13 boulder jumps 8.5 m across
  the lane; wt15 nine identical staghorn copies; **wt06 retired** (a buoyant diver sinking through sand is not a readable
  collision defect).
* **Airfield (AF)**: af02 cart tipped 45 degrees / sunk 0.6 m; af05 wall 28 m wide; af06 hole 4 m north of the start (was 48 m
  south, beyond the gate); af11 x-ray object = the red car by the stone gate (was a hand-sized crate); af15 pile moved into
  sunlight south-east of the start; af17 = the east street lamp casts no shadow (was a barrel); `noui=1` (the review site) hides the
  Sketchbook GUI and starts the walker at the harness start north of the gate, facing north (reviewers used to start south of the gate).
* **Cottage (CT)**: ct02 table tipped 38 degrees / sunk 0.42; ct04 = the garden bench double-spawned (was a dead branch);
  ct09 magenta now survives the day-cycle material swap (it reverted after ~10 s); ct16 door knobs removed with the door;
  ct17 day/night cut every 0.8 s and the normal cycle is stated in the scene text.
* Judge ground truth (`eval/judge_sem.py`), configs / answers (`env/configs`), `bugs.html` and the catalogue sheets updated.

| file | size | sha256 | notes |
|---|---|---|---|
| `00_sponza_constrained.html` | 70.8 MB | `a22570619d0004d6...` | Sponza atrium, the SP suite (16 cases) - packed harness page (`tools/pack_harness_page.py --family sponza`) |
| `01_mistwood_cottage_constrained.html` | 33.5 MB | `a7fdee1d47a9da65...` | Mistwood Cottage (CT suite, 18 cases) - `relayer.py cottage` over the 2026-09-12 build |
| `03_sketchbook_airfield_constrained.html` | 58.1 MB | `57be7a5bcb6b372f...` | Sketchbook airfield (AF suite, 19 cases) - `relayer.py sketch` over the 2026-09-12 build |
| `09_sims_house_builder_constrained.html` | 26.7 MB | `55f98610de89c075...` | Family house (HS suite, 16 cases) - packed harness page (`tools/pack_harness_page.py --family house`) |
| `10_beautiful_water_clean_constrained.html` | 11.7 MB | `bf507e78ea559d27...` | Reef dive (WT suite, 17 cases; wt06 retired) - `relayer.py water` over the 2026-09-12 build |
| `13_beyond_fable_wilderness_constrained.html` | 5.8 MB | `cab7312af1ebccb0...` | Beyond Fable wilderness (WL suite, 18 cases) - `python3 src/fable/build.py` (vite) |
| `bugs.html` | 0.5 MB | `30fa5d7d5f9025a4...` | one card per case of every environment (`tools/make_bug_index.py`) |

Superseded: **envs-2026-09-12** (2026-09-15: the second review round above) and everything older.


## Builds 2026-09-12 (superseded)

Canonical copy: GitHub release **envs-2026-09-12** (tag on the source commit these builds came from):
https://github.com/KimperYang/game-auditing/releases/tag/envs-2026-09-12 - 6 environment files + `bugs.html` + `SHA256SUMS`.
The repository is private, so the browser download needs a GitHub login; from a shell use
`gh release download envs-2026-09-12 -R KimperYang/game-auditing` (then `sha256sum -c SHA256SUMS`).
Server mirror of the same files: `katrina1:/mnt/data3/jingbo/env_builds/2026-09-12/`.

What changed in this release (answers to the 2026-09-12 human review sheet; every "bug itself has issue" /
"too easy" / "too difficult" / "not realistic" row of the two reviewers was acted on):

* **All pages**: the boundary notice stays up 1.5 s instead of 5 s, and the same notice is composited into the
  agent's frames (the agent only sees the canvas). Jitter cases rock at 1.5-2.5 Hz instead of buzzing at
  7-15 Hz (invisible at 2 fps). Double-spawn copies are offset a little more (and slightly rotated) so the doubled
  shell reads in a 480x300 frame. Missing-texture cases use flat unlit magenta.
* **Sponza (SP)**: sp02 pot tilted 24 degrees and sunk (a lowered pot read as a short pot); sp03 pot 1.6x and
  shifted clear of the column it clipped; sp09 magenta on a stone pot instead of a drape (a magenta drape could be
  a coloured drape); sp15 pile moved from the world origin to the north-east aisle corner behind the last drape.
* **House (HS)**: four cases now live upstairs - hs03 oversized kids-room desk chair, hs11 master bed drawn
  through the bedroom walls, hs14 lounge sofa as a crude grey box beyond 3.5 m (the rug had no texture, so the old
  texture-LOD case never showed), hs15 furniture pile in the kids room; hs12/hs13 trigger radii 7 m -> 5 m
  (leaving the room is enough); the locked front / glass door now shows the boundary notice when pushed.
* **Reef (WT)**: wt02 a school of fish half-buried in the sand lane (a rock sunk in sand looked natural); wt03 one
  giant barramundi (the giant coral was not recognisable); wt04 doubled mossy rock set; wt07 ghost rock is the tall
  boulder that reaches the diver's depth; wt11 x-ray silver school (the x-ray coral made no visible difference);
  wt12 cluster nearer with 5/8.5 m radii; wt13 lane boulder jumping 3.5 m with 4/8 m radii.
* **Airfield (AF)**: parked vehicles are static bodies (a walker used to shove the 50 kg car) and the
  enter-vehicle key is unbound; new **af18-pushcar** - the car by the stone gate can be pushed around; af02 cart
  tilted and sunk; af03 giant fire hydrant (a big propane tank passed as real); af06 a visible 1.8 s fall through the
  tarmac before the respawn; af16 barrier upside down (a 90-degree turn passed as placement).
* **Wilderness (WL)**: walking 4.2 -> 6 m/s with a gentler uphill penalty; wl01 boulder by the start floating 3 m
  (the slope boulder never looked airborne); wl03 one grass tile at 4.5x scale with straight edges (big bushes pass
  as natural here); wl09 magenta on the slope boulder (the start boulder was too easy); wl12 radii 8/22 -> 10/16, wl13 8/14 and its collider follows the boulder; wl15 pile is solid;
  **wl16-terrainhole** (a 7 m square of terrain missing, walkable on invisible ground) replaces the invisible seam;
  **wl17-upsidedown** (the broadleaf tree north-west of the start on its crown) replaces the invisible floating grass.
* **Cottage (CT)**: the rope fences are gone (posts, ropes, hung lanterns; colliders too) and the character steps
  0.5 units / climbs 70 degrees, walking 2.3 units/s; the dollhouse wall toggle is disabled (walls stay up); the
  harness keeps the walker off the pond by ground height instead of a rectangle; ct02 tilted sunken picnic table;
  ct03 one garden bench at 2.2x beside its twin; ct06 a visible fall; ct07 ghost tree (trimesh rebuilt);
  ct08 smaller lantern post; ct09 magenta well; ct12 radii 3.5/6.5 -> 4.5/7; ct13 the lamp post in the pond with a
  following collider; ct15 pile is solid; **ct16-missingdoor** (front door gone, doorway still blocked) replaces the
  glassless windows; ct17 snaps between day and night every 3 s.
* Judge ground truth (`eval/judge_sem.py`) and `bugs.html` updated for every changed case.

| file | size | sha256 | rebuild | notes |
|---|---|---|---|---|
| `00_sponza_constrained.html` | 70.8 MB | `1caf083b9b70fb04...` | `python3 tools/pack_harness_page.py --family sponza --out candidate_environments/00_sponza_constrained.html` | Sponza atrium, the SP suite (16 cases) - the harness scene packed with its assets |
| `01_mistwood_cottage_constrained.html` | 33.5 MB | `ab70cff60bd264aa...` | `python3 src/cottage/build.py` | Mistwood Cottage (cartoon cottage, Rapier physics; fences removed); upstream amiradeu/mistwood-cottage (MIT) |
| `03_sketchbook_airfield_constrained.html` | 58.1 MB | `5c3a28c478dfb31a...` | `python3 src/sketch/build.py` | Sketchbook airfield (three r113 + cannon.js; 18 cases); upstream swift502/Sketchbook (MIT) + Poly Haven props |
| `09_sims_house_builder_constrained.html` (packed harness page: HS suite, BVH collision; `tools/pack_harness_page.py --family house`) | 26.7 MB | `b3ed6f9453d51e6d...` | `python3 src/house/build.py` | two-storey house interior (HS suite, four cases upstairs); Poly Haven furniture + PBR + HDRI |
| `10_beautiful_water_clean_constrained.html` | 11.7 MB | `c6f05ac1837b10a1...` | `python3 src/water/build.py` | shallow reef dive (WT suite); upstream VictorZakharov/beautiful-water (MIT) |
| `13_beyond_fable_wilderness_constrained.html` | 5.8 MB | `72a3c8987a0e21d3...` | `PATH=/mnt/data3/jingbo/tools/node/bin:$PATH python3 src/fable/build.py` | Beyond Fable wilderness (procedural, TS/Vite); upstream xikhar/beyond-fable (MIT) |
| `bugs.html` | 0.6 MB | `456caff7c749dcc4...` | `python3 tools/make_bug_index.py` | one card per case of every environment, thumbnails from `reports/<suite>/catalog` |

The v1 originals (`orig_v1_*`, the initial candidate builds before the rework) are no longer attached; they are in
release envs-2026-09-09c and under `src/<env>/orig_v1_*.bak` on the server.

Full checksums: `SHA256SUMS` in the release. Verify a download with `sha256sum -c SHA256SUMS`.

Superseded: **envs-2026-09-09c** (2026-09-12: the review fixes listed above) and everything older (see below).

<details><summary>Previous release notes (2026-09-09c and earlier)</summary>

## Builds 2026-09-09c (superseded)

Canonical copy: GitHub release **envs-2026-09-09c** (tag on the source commit these builds came from):
https://github.com/KimperYang/game-auditing/releases/tag/envs-2026-09-09c - 6 environment files + `bugs.html` + 5 v1 originals + `SHA256SUMS`.
The repository is private, so the browser download needs a GitHub login; from a shell use
`gh release download envs-2026-09-09c -R KimperYang/game-auditing` (then `sha256sum -c SHA256SUMS`).
Server mirror of the same files: `katrina1:/mnt/data3/jingbo/env_builds/2026-09-09c/`.

| file | size | sha256 | rebuild | notes |
|---|---|---|---|---|
| `00_sponza_constrained.html` | 70.8 MB | `e7a85fca684acd54...` | `python3 tools/pack_harness_page.py --family sponza --out candidate_environments/00_sponza_constrained.html` | Sponza atrium, the SP suite (16 cases) - the harness scene packed with its assets |
| `01_mistwood_cottage_constrained.html` | 33.5 MB | `cfe5db94af57c4e3...` | `python3 src/cottage/build.py` | Mistwood Cottage (cartoon cottage, Rapier physics); upstream amiradeu/mistwood-cottage (MIT) |
| `03_sketchbook_airfield_constrained.html` | 58.1 MB | `9b2ed90a6067c65d...` | `python3 src/sketch/build.py` | Sketchbook airfield (three r113 + cannon.js); upstream swift502/Sketchbook (MIT) + Poly Haven props |
| `09_sims_house_builder_constrained.html` (packed harness page: HS suite, BVH collision; `tools/pack_harness_page.py --family house`) | 26.7 MB | `5950c42e0b54c8a4...` | `python3 src/house/build.py` | two-storey house interior (HS suite); Poly Haven furniture + PBR + HDRI |
| `10_beautiful_water_clean_constrained.html` | 11.7 MB | `1d34562aa69351f4...` | `python3 src/water/build.py` | shallow reef dive (WT suite); upstream VictorZakharov/beautiful-water (MIT) |
| `13_beyond_fable_wilderness_constrained.html` | 5.8 MB | `fa2cbb468f44fad2...` | `PATH=/mnt/data3/jingbo/tools/node/bin:$PATH python3 src/fable/build.py` | Beyond Fable wilderness (procedural, TS/Vite); upstream xikhar/beyond-fable (MIT) |

v1 originals (the initial candidate builds before the rework, kept for comparison; `orig_v1_*` in the release):

| file | size | sha256 |
|---|---|---|
| `orig_v1_01_mistwood_cottage_constrained.html` | 43.6 MB | `ca9ed635fc638492...` |
| `orig_v1_03_sketchbook_airfield_constrained.html` | 39.6 MB | `36791733b3f68dcd...` |
| `orig_v1_09_sims_house_builder_constrained.html` | 1.2 MB | `ffa69b7c4ffb77ff...` |
| `orig_v1_10_beautiful_water_clean_constrained.html` | 1.6 MB | `55ad9c1b272c6b77...` |
| `orig_v1_13_beyond_fable_wilderness_constrained.html` | 0.7 MB | `c00d76b375d7d953...` |

Full checksums: `SHA256SUMS` in the release. Verify a download with `sha256sum -c SHA256SUMS`.

Superseded: **envs-2026-09-09b** (2026-09-09c: the four standalone pages embed the merged harness contract with the agent/ harness's fixed-tick and film-size parameters), **envs-2026-09-09** (2026-09-09b: cottage suite carriers fixed - they had rendered as a dot - plus eye height / walking speed), **envs-2026-09-08e** (2026-09-09: unified bug review - review overlay in every page, bugs.html, house and Sponza as packed harness pages with BVH collision, finer airfield prop collision), **envs-2026-09-08d** (2026-09-08e: the harness contract holds the walker inside the config bounds / outside exclusion zones), **envs-2026-09-08c** (2026-09-08d: cottage suite carriers renamed, plant pile on the east lawn, trigger distances scaled), **envs-2026-09-08b** (2026-09-08c adds the AF / WL / CT bug suites to the airfield, wilderness and cottage builds:
`?bug=<id>` and the harness contract; house and reef builds unchanged), **envs-2026-09-08** (all five rebuilt on 2026-09-08b: English UI, no jump key, taller first-person eye,
house stairs/door/lamp fixes) and **envs-2026-09-07** (same files as 2026-09-08 except the house build, whose sideboard wine-bottle row overhung the
shelf and whose boundary warning fired along the whole south wall; the front door was shut). Kept for reference.

</details>

## Reviewing bugs (every environment the same way)

Open `bugs.html` (shipped next to the environment files) - one card per case, or open an environment file with
`?bug=<id>` (e.g. `03_sketchbook_airfield_constrained.html?bug=af05-airwall`).  Inside every page the panel at the top
right lists the cases, describes the planted defect, jumps next to it ("Go to the bug") and toggles a marker beam.
House and Sponza pages are the harness scene itself (env/human.html + core.js, mesh-level collision); V shows the
invisible colliders and the answer beacons there.  Walk with WASD, look with the mouse; there is no jump anywhere.

## Rebuilding and publishing

* Run the build command from `candidate_environments/` (paths above are relative to it); each script prints a
  `wrote <file>` line on success - check for it, a `| grep | tail` chain hides failures.
* House / reef / sketch / cottage need only the repo `.venv` (Python) plus the Poly Haven / Khronos assets that
  `src/<env>/README.md` lists (fetch scripts: `src/sketch/ph_fetch.py`, `scripts/fetch_assets.sh`).
* Beyond Fable needs Node 22 (`/mnt/data3/jingbo/tools/node`) for `vite build`; `src/fable/upstream/node_modules`
  is restored with `npm ci` from the committed `package-lock.json`; `upstream/src/assets/textures.ts` (4.7 MB, generated
  by `make_textures_module.py` from the Poly Haven sets) is git-ignored too - regenerate it first (see `src/fable/README.md`).
* House checks after a rebuild: `src/house/audit_props.py` (prop placement: floating / sunk / overhanging) and
  `src/house/boundary_test.py` (warning silent inside, fires only on the doorstep).
* The harness does not read these files except the reef page (`env/configs/wt*.json` point at
  `candidate_environments/10_beautiful_water_clean_constrained.html`); the house env used by the HS suite is the
  generated module `env/house/house.js` (`src/house/make_harness_module.py`).
* Publishing a new build set: copy the HTMLs into a new `/mnt/data3/jingbo/env_builds/<date>/`, write `SHA256SUMS`,
  tag the source commit (`git tag -a envs-<date> <commit>`), push the tag and run
  `gh release create envs-<date> --verify-tag --title ... --notes-file ... <files>` (gh lives in
  `/mnt/data3/jingbo/tools/gh/bin`; it authenticates with the same token as the git remote, passed as `GH_TOKEN`).
  Release assets do not count against LFS quotas and never enter the git history.
