# Reef dive (source for `10_beautiful_water_clean_constrained.html`)

Shallow-water reef with a first-person diver.  The ocean surface, sky, sun, navigation buoy and
volumetric light rays are the WebGL pipeline of Victor Zakharov's MIT project
[beautiful-water](https://github.com/VictorZakharov/beautiful-water) (copied under `upstream/`,
unused WebGPU modules and the performance HUD removed).  Everything under water is new:

* `app/seabed.js`   sandy seabed (two-resolution height mesh, Poly Haven `coast_sand_01`), lights, plankton
* `app/reef.js`     Poly Haven rock models, procedural corals (staghorn / table / brain / tube sponge /
                    anemone / sea fan), instanced seagrass and kelp with vertex sway
* `app/fish.js`     boids schools: Khronos CC0 `BarramundiFish` (instanced, vertex swim animation) and
                    procedural silver fish
* `app/caustics.js` onBeforeCompile patches: animated caustics + underwater tint, sway, swim
* `app/dive.js`     first-person diver (same `player` API as the previous build) + headless helpers
* `app/main.js`     entry; `upstream/scene/environment.js` now only holds `seabedHeight()`

## Rebuild

```bash
# assets (git-ignored): assets/water/models/<id>/ (Poly Haven 1k glTF, Khronos BarramundiFish.glb),
#                       assets/water/textures/<id>/ (Diffuse/nor_gl/arm jpg), assets/water/vendor/ (three 0.185.1
#                       three.core.js three.module.js OrbitControls Reflector Refractor GLTFLoader
#                       BufferGeometryUtils SkeletonUtils from cdn.jsdelivr.net/npm/three@0.185.1)
.venv/bin/python environments/threejs/scenes/src/common/pack.py --manifest environments/threejs/scenes/src/water/manifest.json \
    --assets assets/water --out /tmp/water_pack.json
.venv/bin/python environments/threejs/scenes/src/water/build.py --pack /tmp/water_pack.json \
    --vendor assets/water/vendor --out environments/threejs/scenes/10_beautiful_water_clean_constrained.html
```

`build.py` embeds every ES module (three.js builds/addons, `upstream/`, `app/`) as gzip+base64 and the
bootstrap in `template.html` turns them into blob-URL modules in dependency order, rewriting `three`,
`three/addons/...` and relative specifiers.  No bundler or network is needed at runtime.

## Runtime contract

`window.BenchmarkWorld = { version, ready, scene, camera, renderer, controls, player, reef, addObject,
removeObject, getState, teleport(x,y,z), setView(yaw,pitch), activateDiver(useLock), THREE }`.
`player` keeps the previous build's API (`isActive/start/exit/reset/setPosition([x,y,z])/getState/update`);
`activateDiver(false)` drives the diver without pointer lock (headless harness).  The constrained
boundary script (half extents 26.5 m) is unchanged.  Controls: 进入潜水 button, WASD swim, mouse look,
Space up, C/Ctrl down, Shift fast, R reset.  Seabed at about -6 m, reef ridge 9–16 m north-east of the buoy.


## v3 (2026-09-07): first person, fish fix, bug catalogue, harness contract

* Starts in the first-person diver (no orbit "观察模式"); keys work at once, mouse look on the first click.
* The barramundi swam tail-first: the glTF's head is at +z already, so the `headFlip` rotation was removed
  (`main.js` `createFish(..., { headFlip: query.has('headflip') })`); a geometry width profile confirms the
  head end is the wide end.
* Rocks are solid for the diver (`dive.js`: ellipsoid colliders from each ROCK's world bounds, 0.78 x
  half extents; invisible box colliders and seabed "holes" are supported for the bug cases).
* **Bug catalogue** `app/bugs.js` (`?bug=wtXX-<slug>`), 17 cases mirroring the SP/HS taxonomy plus two
  reef-specific ones: wt01 floating boulder, wt02 sunken rock, wt03 oversized coral, wt04 double-spawned
  rock, wt05 invisible wall, wt06 seabed hole (diver sinks and respawns), wt07 no-collision rock,
  wt08 trembling coral, wt09 magenta rock, wt10 rock invisible from behind, wt11 x-ray coral, wt12 coral
  cluster unloads after leaving, wt13 rock position resets on revisit, wt14 coral LOD pop, wt15 coral pile,
  wt16 fish swim backwards, wt17 fish swim upside down.  `BenchmarkWorld.bug` = the judge answer
  ({name, where, at, category}); behaviour bugs run per-frame hooks.  Verified by
  scratchpad `water_bug_verify.py` (12/12: collisions, hole, visibility, unload, reset, LOD, fish heading).
* **Harness contract** `app/agent.vla.js`: with `?harness=1&config=<name>` the page fetches
  `environments/threejs/runtime/configs/<name>.json` (served by agent/vla/bridge.py), applies its `bug`, and installs the same
  `window.__env` API as environments/threejs/runtime/core.js (`enable/act/tick/state/targets/flags/probe`, film strips at
  `filmDt`), so agent/vla/runner.py runs S1 on the reef unchanged.  Actions are real-time: forward/back hold
  W/S for dist / 3.15 m/s, turn/look change the diver's yaw/pitch, film frames are 480x300 canvas grabs
  (`preserveDrawingBuffer` in harness mode).  The bridge opens the page when the config has a `page` key.
* Cases / answers: `scripts/tools/gen_water_cases.py` (answers dumped from the page), tasks `audit_wtXX_bug` /
  `audit_wt00_clean` (agent/vla/tasks.py, 90 steps), judge GT + labels in judge/judge_sem.py.
