# Family house walkthrough (source for `09_sims_house_builder_constrained.html`)

Realistic two-storey house environment: real-scale rooms, walkable stairs, PBR materials and
Poly Haven CC0 furniture.  Everything is baked into one self-contained HTML (no network at
runtime) so it can be dropped into the candidate-environment pool like the other builds.

```
app.js          scene/gameplay code (ES module; imports three + addons)
template.html   HUD + bootstrap loader + constrained-benchmark boundary script
manifest.json   which Poly Haven models / texture sets / HDRI to embed, texture size, catalogue height
pack.py         asset packer -> pack.json  (quantized GLB, WebP textures, gzip'd JS modules)
build.py        template + pack.json + app.js -> single-file HTML
orig_v1_*.bak   the previous procedural-box version, kept for reference
```

## Rebuild

```bash
# one-off: fetch the CC0 assets (~115 MB) into assets/house/  (assets/ is git-ignored)
#   models  : https://api.polyhaven.com/files/<id> -> gltf 1k + includes -> assets/house/models/<id>/
#   textures: Diffuse.jpg / nor_gl.jpg / arm.jpg (1k)      -> assets/house/textures/<id>/
#   hdri    : kloofendal_48d_partly_cloudy_puresky_1k.hdr  -> assets/house/hdri/sky_1k.hdr
#   addons  : RGBELoader.js, RoundedBoxGeometry.js (three r169 data/examples/jsm) -> assets/house/
.venv/bin/python environments/threejs/scenes/src/house/pack.py \
    --assets assets/house --vendor assets/vendor/three --extra-vendor assets/house --out /tmp/house_pack.json
.venv/bin/python environments/threejs/scenes/src/house/build.py \
    --pack /tmp/house_pack.json --out environments/threejs/scenes/09_sims_house_builder_constrained.html
```

`pack.py` caches per-asset results next to the pack file, so after the first run only `build.py`
is needed when `app.js` / `template.html` change (a few seconds).

## Runtime contract

* `window.BenchmarkWorld` — `ready`, `scene`, `camera`, `renderer`, `root`, `player` (a Group
  whose position is the player's feet), `floors[0|1]`, `colliders` (AABB list with `floor`
  0/1/2=both), `semanticObjects` (name -> objects, e.g. `SOFA`, `TOILET`, `STAIR_STEP`,
  `WINDOW_GLASS`, `DOOR`), `rooms`, `getState()`, `setFloor(n)`, `teleport(x,y,z)`,
  `setView(yaw,pitch)`, `addObject/removeObject`, `THREE`.
* Controls: WASD, mouse look (pointer lock on click), Space jump, Shift run, 1/2 teleport
  between floors, R reset.  Stairs are walked normally (ground height follows the treads).
* `window.BenchmarkBoundary` — unchanged boundary clamp/warning from the constrained builds
  (half extents 6.9 x 4.9 m, i.e. the interior; all exterior doors are closed).

## Layout (metres; x east, z south, y up)

Ground floor: hall + staircase (x -1.8..1.8), living room and study (west), bathroom and
laundry (north-west), open kitchen/dining (east).  Upper floor: landing with stairwell
balustrade, master bedroom with en-suite (west), dressing room, kids room (north-east),
family lounge (south-east).  Ceilings 2.7 m, floor-to-floor 3.0 m, exterior walls 0.3 m
(brick outer leaf), interior walls 0.12 m, doors 0.9 x 2.1 m, windows with sills at 0.9 m.

## Assets and licences

All models, textures and the HDRI are CC0 from https://polyhaven.com (see `manifest.json`
for the exact ids).  three.js r169 is MIT.  Models are re-encoded by `pack.py`:
KHR_mesh_quantization (int16 positions, int8 normals, uint16 UVs), WebP textures via
EXT_texture_webp, occlusion from the packed ARM texture; `steel_frame_shelves_01` is
rescaled x0.1 because the upstream export is in the wrong unit (catalogue height is used
to detect this automatically).

## 2026-09-06 review fixes (user feedback)

* Ground-floor wooden floor "flickering": the foundation plinth's top face was coplanar with the
  floor slabs (both at y=0) -> z-fighting. The plinth top now sits 4 cm below the slabs.
* Master-bedroom mirror and en-suite towel rail were hung inside door openings (floating). Mirror
  moved to the clear wall between nightstand and dresser (z=0.6), rail to the solid wall east of
  the en-suite door (x=-4.82).
* Player capsule radius 0.3 -> 0.22 and furniture spacing revised so every passage is >= 0.6 m
  (living room: sofa/coffee table/side table/armchairs/ottoman; dressing room bench; study
  bookshelf). `walkability.py <html>` reports per-room reachability for a given radius
  (all rooms >= 90 % reachable at r=0.22; remaining pockets are dead corners behind furniture).
* Movement is confined indoors: exterior doors are fixed shut and the boundary box is the
  interior (halfX 6.6 / halfZ 4.6); the garden stays visible through the windows.

## Harness scene (bug-hunt benchmark)

`make_harness_module.py` derives `environments/threejs/runtime/house/house.js` (scene type `house` in environments/threejs/runtime/scenes.js) from
app.js: same geometry/furnishing code, assets served from `assets/house/pack/` (written by
`export_pack.py --pack pack.json --out assets/house/pack`), core.js owns rendering/physics.
Objects are named `TAG#n` in placement order (DINING_CHAIR#1 ...) for the HS bug suite
(`scripts/tools/gen_house_cases.py`). Re-run make_harness_module.py after editing app.js.

Pitfalls met while baking the house into the harness BVH (all handled in make_harness_module.py):
* three-mesh-bvh's StaticGeometryGenerator collects meshes with `traverseVisible()` - an
  invisible helper mesh (the stair ramp) silently drops out of the bake; hide its material instead.
* the bake applies world matrices with `applyMatrix4`, which writes normalized int16
  (KHR_mesh_quantization) positions back into [-1,1] and yields phantom triangles - hand it
  Float32 copies of the positions.
* Extrude/Shape geometries are non-indexed; the merge needs all-indexed input (`mergeVertices`).
* the capsule (eye 1.7 + radius) needs ~2 m of headroom on the stairs: the stairwell opening
  starts at z=2.0 and the ramp surface sits 4.5 cm above the nosing line.


## 2026-09-07 fixes

* The row of wine bottles on the kitchen "counter" under the window floated: the lower cabinets of the
  window runs are hidden (upper cabinets only), so props at counter height there had nothing under them.
  Bottles moved to the island's east end, the vase to the short counter by the stove; the sideboard bottle
  row is centred on the shelf (the model's origin is at one end of its 0.68 m row).
* Standalone page: the boundary warning now fires only when leaving through the front door (boundary box
  x ±8, z -6.6..4.6 around center (0,0,-1)); touching walls no longer shows it.  The harness `bounds` clamp
  is unchanged.
* Regenerate `environments/threejs/runtime/house/house.js` after editing `app.js` (`make_harness_module.py`), and rebuild the page
  (`build.py --pack <pack.json> --out ...`).

## 2026-09-08 fixes (release envs-2026-09-08)

* Sideboard wine bottles: the 0.68 m row ran along z across a 0.38 m-deep unit (rot WEST) and overhung on both sides -
  now rot 0 along the unit's 1.08 m top (`x: 6.65 - 0.34, z: 4.25`). Sofa pillows raised 3 cm onto the seat cushion.
* Boundary warning: the walkthrough used to hard-clamp the player inside the house and the boundary box's south edge
  coincided with the south wall, so the warning fired whenever the player touched any south-wall spot. Now the front
  door stands open (`FRONT_DOOR_ANGLE = 1.5`, standalone only), the player may step out onto the doorstep
  (`OUTSIDE = +-7.6 x +-6.2`, same box in template.html) and the warning appears only there; the room label reads
  "室外" outside. The harness module keeps the door shut (`FRONT_DOOR_ANGLE = 0` in make_harness_module.py) so the HS
  suite geometry is unchanged apart from the two decor moves above (bottles, pillow), which post-date the HS f2 runs.
* Checks: `audit_props.py` (downward rays over every placed prop's footprint) and `boundary_test.py` (7 walks) - run
  both after `build.py`; the audit's remaining flags are single-corner hits on neighbours (chairs under the table,
  skirting boards) and were verified visually.
