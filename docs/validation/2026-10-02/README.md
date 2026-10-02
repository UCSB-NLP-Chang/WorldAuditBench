# Runtime validation — 2026-10-02

## Rebuilt candidates — 2026-10-02 14:45 UTC

The new executables are **not ready for publication**. All seven environments
compiled. Of the 126 tasks, 125 passed initial-frame, turn, spawn and bundled-boundary
checks. The 125 captured initial views were visually reviewed: no minimap or black
minimap background was visible. These checks do not establish anomaly equivalence
or clear the native scene issues below.

The first rebuilt Subway executable failed S16 because it treated the authored
Blueprint poster as a static-mesh actor and lacked `timed_poster_hide`. A separate
candidate now restores the target actor, the fixed poster materials and the
15-second disappearance. All 15 checkpoints on a walking and waiting route match
the existing production executable in actor-state digest, position and simulated
time. Before/after screenshots confirm the correct posters and disappearance.
S16 and S22 both pass spawn, bundled-policy, boundary and changed-frame checks with
this candidate. S22's original fountain material and backing patches were also
restored; broader visual acceptance remains pending.

The Ancient rebuild also omitted A19's repositioned lion and A25's opposite door
swing. Their original runtime patches were recovered. Both now match production
actor states at all 12 checkpoints on a sampled look, wait and return route;
reviewed screenshots confirm the lion and initial door configuration. Close-range
interaction checks are still running, so these comparisons do not yet establish
complete task equivalence.

Broader paired checks of production and rebuilt programs are running. They compare
identical action sequences and record executable hashes. A matching actor-state
digest does not cover materials, component state or every trigger; screenshots and
actual interaction results must also be reviewed. Source-literal searches are
review leads, not by themselves failed tasks.

The rebuilt candidates have not replaced the published packages. Existing
production artifacts and experimental data are retained. Dynamic captures and
recovery work remain in the private AWS release workspace. Nine new routes were
captured and their 162 sampled screenshots reviewed. U024's ground seams and
U041's facade penetration were reproduced; U033's window reflections remain
unresolved. Ancient and Medieval startup textures sharpen during idle. The S01
stairs stayed visible on the sampled route, which does not clear the original
report. Sampled screenshots cannot establish the absence of flicker.

## Earlier production-package checks

The checks in this section apply to the earlier production binaries and documented
launcher, **not to the new rebuild candidates above**. Visual acceptance remains
open; these checks do not certify the absence of native scene defects.

## Verified

- All **213 paper tasks** match the current AWS production task table in revision,
  map and content/page hashes. See [task-identities.json](task-identities.json).
- All **126 Unreal tasks** were started on A10G from the released packages. Each
  produced a reset image and a different image after a 30° turn. Executable hashes,
  spawn positions, initial yaw, policy hashes and actual native region bounds were
  checked. See [unreal-results.json](unreal-results.json).
- All **87 Three.js tasks** passed pinned-page hash checks, reset, four 90°
  turns, a two-second idle observation, nonblank-frame checks and hidden-UI
  checks, with no uncaught JavaScript errors. See
  [threejs-results.json](threejs-results.json). 21 tasks used SwiftShader;
  the remaining tasks used Apple M4 Metal. These are launch and panorama checks,
  not exhaustive collision or anomaly checks. Some pages request an optional
  `/env/configs/` file and receive 404; they use the explicit `bug` query parameter
  when that optional file is absent.
- Every Unreal policy has **3× the original horizontal bounds area**. The frozen
  policy is selected per task; both the September 17 exploration policy and the
  September 18 area policy remain in use, as in the experiment profiles.
- `set HUD bShowHUD false` disables the minimap and its background in the engine.
  `getall HUD bShowHUD` confirmed the setting for every task before the launcher
  returned its first observation. The observation pipeline does not cover or crop
  the corner. The native client reports the exploration boundary as text when the
  character reaches it.
- The unified Urban archive preserves all 180 files across four cooked scene
  layouts, verified by individual SHA-256. All 15 Urban tasks passed the launch
  checks from the unified installation.

These checks apply to the documented installer and `scripts/serve_unreal.py`
launcher. Running an original executable without the launch profile does not apply
its external exploration policy or the HUD setting.

## Visual review and outstanding findings

A longer walk was captured for 32 Unreal tasks: all 15 Urban tasks and 17 tasks
covering the other scene maps. Each walk contains a stationary observation,
a full panorama in 30° steps, four forward and four backward moves, and another
stationary observation. This covers selected routes, not every reachable position.

| Finding | Evidence and status |
|---|---|
| Subway exterior stairs disappearing with distance | A 148-observation S01 route, repeated with the HUD disabled, approached, descended, climbed and looked back at the exterior stairs. The reported disappearance was not reproduced on that route. A separate run increased view distance and disabled occlusion for comparison. No global culling change was adopted. The original report remains open. |
| Urban rear-lane ground | Stretched pavement patterns and triangular seams are visible in the U024 walk. This is outside the cardboard-box movement anomaly and remains open. |
| Urban storefront reflections | Repeated tree/sky reflections and abrupt-looking window changes are visible in U033 and neighboring shopfronts. Material-level review remains open. |
| Urban facade collision | In the U041 walk, forward movement reached the back side of the shop facade. U041's intended anomaly concerns the dumpster collision, so this route requires separate collision review. |
| Lighting changes | Several maps gradually settle in brightness after startup or a turn. Stationary frame differences decrease over time, consistent with exposure adaptation; this alone does not establish random light flicker. S01 uses fixed exposure. Reflection shimmer and lighting during movement are not exhaustively cleared. |
| Initial texture detail | Some Ancient scene surfaces have low detail at the first observation and resolve after additional frames. Texture-streaming startup remains part of the visual review. |

The current AWS machine contains the compiled releases and recovered C++ source.
The September 14 authoring recovery lacks the matching editable map/material
content; the older September 7 Urban content is not the same scene revision.
A verified recook of the affected later maps needs that matching authoring content
and an editor build. The archive consolidation and HUD change do not repair these
outstanding material or geometry findings.

### Review images

The three Urban walks were repeated after disabling the HUD. The contact sheets
show the captured observation order:

- [U024 ground](images/urban-ground.jpg): triangular texture transitions in
  panorama frames 04–07 and the final return view.
- [U033 reflections](images/urban-reflections.jpg): repeated tree/sky imagery in
  storefront windows.
- [U041 facade](images/urban-facade.jpg): movement reaches the reverse side of
  the shop signs in forward frames 2–4.
- [S01 stairs](images/subway-stairs.jpg): the beginning of the repeated exterior
  route, including distant and near views. The full route has 148 observations.

## Published artifacts and source checks

- Unified Urban archive: HF revision
  `8581dfdda3a690a5b397588167ddedbfdbe1afef`, 3,377,912,168 bytes, SHA-256
  `fae9adcd012cb29777f57ac7f1a13908c1c3ed7819e1e582973e439faa95f2ca`.
  The public file metadata matches the fully verified archive.
- The HF Space HUD startup setting was updated at
  `dda0437287680ebb2b7376cd194ab99a6b17dceb`; its runtime remains **PAUSED**.
- Source suite: 191 passed, 3 skipped (`not chromium and not live`). After the
  release-manifest update, the 24 resource/native-client tests passed again.
  Space suite: 8 passed. `scripts/check_release.py` and `git diff --check` passed.

Injected anomalies, task maps, rubrics, frozen bounds and cooked content were not
rewritten as part of this validation. Source checks and launch checks do not
reproduce the paper's model scores.
