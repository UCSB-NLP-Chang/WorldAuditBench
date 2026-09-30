# Mistwood Cottage (source for `01_mistwood_cottage_constrained.html`)

Upstream: [amiradeu/mistwood-cottage](https://github.com/amiradeu/mistwood-cottage) (MIT), a stylized
cottage scene with baked day-cycle textures, Rapier physics, a coin mini-game and a third-person
camera.  The upstream sources are copied under `upstream/` and rebuilt here without Vite.

Changes for the benchmark build (all in `upstream/Experience/`, marked in the files):

* `World/Player.js` — the yellow capsule placeholder is replaced by the CC0 **RobotExpressive**
  character (Tomás Laulhé, from the three.js examples): 0.72 world units tall, feet on the physics ball,
  Idle / Walking / Running / Jump animations driven by the controller velocity, faces the movement
  direction, main body tinted with the day-cycle player colour.
* `CameraThirdPerson.js` — camera collision against the physics world (walls, roof, terrain) so the
  orbit camera no longer clips into the cottage; pointer-lock look on canvas click; first-person mode
  (`V`, or camera distance below 1) which hides the character; `snap()` for scripted views.
* `Utils/Resources.js`, `Utils/Cursor.js` — asset paths go through `window.__resolveAsset` (embedded
  blob URLs); `sources.js` drops the unused EXR environment map and adds the robot model.
* Collision completion (the upstream physics let the player walk over fences, through the closed
  front door and the windows, and climb walls):
  * `Utils/PlayerController.js` — step height 0.22 (was 5 units), max climb slope 58° (was 145°),
    jump strength 2.8 (was 5); flags jump requests for the animation.
  * `World/Player.js` — vertical capsule collider (half height 0.21, radius 0.13) instead of the
    ball, so the head collides with lintels and branches.
  * `World/Cottage.js` — the baked physics proxies have an empty door opening (the door leaf is
    visual only) and no glass in the window openings: a door panel cuboid and trimesh colliders for
    the three glass meshes are added; the ones on the front / left wall are removed together with
    that wall in the dollhouse views (`Utils/Cursor.js` `setWallPhysics`, `Physics.js`
    `trimeshDesc` / `addExtra`).  The east side of the cottage is an open cutaway by design; its
    low beam already stops the capsule.
  * `World/ExtraColliders.js` — the rope fences are thin posts with ropes sagging to 0.15–0.25
    units above the ground, which a capsule rides over.  One invisible box per fence span
    (post to post, sized from the walking surface sampled next to each post, top 0.6 above it) makes
    them solid.  Post positions come from the connected components of `Environment.Merged`
    (32-vertex pieces, 0.52 tall, standing on the terrain).  The boxes use collision-group bit 1
    only and the third-person camera ray tests bit 0, so they never pull the camera in.
  * `app/main.js` — `teleport(x, null, z)` stands the capsule on the highest surface at (x, z).
  * `Utils/SoundEffects.js` — autoplay rejections are swallowed.
* Coin mini-game removed (`World/Coins.js` no longer instantiated, counter overlay and coin model
  dropped) at the user's request.
* `app/main.js` — entry without the Vercel analytics; exposes `window.BenchmarkWorld`
  (`ready`, `teleport`, `setView(theta, phi)`, `setDistance`, `setFirstPerson`, `setCycle`, `getState`).
* `app/shims/` — gsap (classic script), `@dimforge/rapier3d` → `rapier3d-compat` (wasm inlined, awaited
  at import), lil-gui / stats-gl stubs (debug only).

## Rebuild

```bash
# assets (git-ignored): assets/cottage/static = upstream static/ (sounds re-encoded at 40 kbps) +
#   models/Robot/RobotExpressive.glb; assets/cottage/vendor = three 0.177.0 build + addons,
#   rapier.es.js (@dimforge/rapier3d-compat 0.17.3), gsap.js (3.12.5 UMD), fflate.module.js
.venv/bin/python candidate_environments/src/cottage/build.py --vendor assets/cottage/vendor \
    --static assets/cottage/static --out candidate_environments/01_mistwood_cottage_constrained.html
```

`build.py` converts `.glsl` files (resolving `#include ../x.glsl`) to string modules, gzips every ES
module and embeds every static asset; the bootstrap in `template.html` injects an import map of blob
URLs (the upstream singleton pattern has circular imports, so modules must resolve lazily) and maps
asset paths to blob URLs (`__resolveAsset`, plus a fetch override for the DRACO decoder files).

## Runtime contract

Same as before: `window.experience` (upstream singleton) and the constrained boundary script of kind
`cottage` (it reads `experience.world.player.rigidBody`).  Controls: WASD move, Space jump, mouse drag
or pointer-locked look, `V` first person, day-cycle buttons, camera distance slider.

## CT bug suite (2026-09-08)

`app/bugs.js` holds 17 injected cases (`ct01-float` … `ct17-timejump`).  The upstream scene is a few merged
meshes, so carriers (trees, rocks, the lamp post) are first *detached*: the connected component of
`EnvironmentMerged` / `NoPhysics` is copied into its own mesh (world-space geometry, same baked material) and the
original triangles are collapsed.  Physics stays as it is (trimesh) except for the collision cases (Rapier cuboid
air wall, fence chain colliders removed for the ghost fence - `ExtraColliders.chainColliders`, a hole that drops the
capsule and respawns it).  `app/main.js` applies `?bug=` / the harness config's bug once the world is ready, skips
the intro in harness / bug mode and installs the shared harness contract (`/*__HARNESS__*/` in `template.html`).
Configs + answers: `tools/gen_cottage_cases.py`; catalogue: `tools/env_bug_shots.py cottage reports/cottage-suite/catalog`;
tasks `audit_ctXX_bug` / `audit_ct00_clean`, judge GT in `eval/judge_sem.py`.
