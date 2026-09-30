"""Generate the SP test suite: bugs implanted as mutations of the original Sponza scene.

Design (project decision 2026-08-29):
- Real environment only (Khronos Sponza), no toy corridors, no toy prop clutter.
- Every bug is a mutation of the scene's own elements, judged against the scene's internal
  consistency (8 identical floor pots, 10 identical ground drapes, symmetric architecture),
  so each case is unambiguously a defect, never plausible design.
- Categories follow the project taxonomy: geometry-space / collision-physics /
  visual-consistency / spatiotemporal-state / semantics-logic.
- ONE shared clean config (sp00-clean): every bug config differs from it by exactly one
  mutation; a uniform neutral patrol instruction avoids per-case priming.

Mesh-name map (traverse order of the loaded gltf, see scratch inventory):
  floor pots (dish+pot pairs): 81/82 (-7.7,-1.8)  83/84 (-7.7,1.2)  1/2 (-1.95,-1.8)
    85/86 (-1.95,1.22)  87/88 (0.95,1.23)  93/94 (0.96,-1.78)  89/90 (6.67,1.23)  91/92 (6.67,-1.78)
  ground drapes (2.3x2.3): 63..72 along z=+-1.6/-2.2;  big vase: 0 at (3.96,1.59)

Usage: python tools/gen_sponza_cases.py   (idempotent; overwrites env/configs/sp*.json)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "env" / "configs"

SPONZA = [{"type": "gltf", "id": "sponza", "url": "/assets/sponza/Sponza.gltf"}]
# auto spawn point (floorPts[0]) sits at world (-0.48, 0, -0.31); SPW converts world x/z
SPW = lambda wx, wz, **kw: {"scene": "sponza", "spawnOffset": [round(wx + 0.48, 2), round(wz + 0.31, 2)], "snap": True, **kw}
SPAWN = {"scene": "sponza", "pos": SPW(-8.5, -0.3), "yawDeg": -90}   # west end, facing +x

M = lambda *idx: [f"mesh_0_{i}" if i else "mesh_0" for i in idx]


# verification viewpoints for tools (scratch packed_shots.py): camera (world x, y, z) looking at (x, y, z)
VIEWS = {
    "sp02-clip": [[6.6, 0.0, -1.0, 6.67, 0.3, 1.23]],
    "sp09-magenta": [[-3.9, 0.0, 0.2, -1.95, 0.3, -1.8]],
    "sp15-spawnpile": [[6.4, 0.0, 2.6, 7.9, 0.5, 4.0], [7.7, 0.0, 0.6, 7.9, 0.5, 4.0]],
}
def _view(cx, cy, cz, tx, ty, tz):
    import math
    return [cx, cy, cz, round(math.atan2(-(tx - cx), -(tz - cz)), 3), round(math.atan2(ty - (cy + 1.6), math.hypot(tx - cx, tz - cz)), 3)]


def emit(name, bugs, answers, desc):
    cfg = {
        "name": name,
        "meta": {"title": name, "desc": desc},
        "seed": 5,
        "scenes": SPONZA,
        "spawn": SPAWN,
        "objects": [],
        "bugs": bugs,
        "targets": {"zone_far": SPW(9.0, -0.3)},
    }
    if name in VIEWS:
        cfg["views"] = [_view(*v) for v in VIEWS[name]]
    (OUT / f"{name}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    if answers:
        (OUT / f"{name}.answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=1))
    print("wrote", name)


ANS = lambda name, where, x, z, cat, **kw: [{
    "name": name, "where": where, "at": SPW(x, z), "category": cat, **kw}]

emit("sp00-clean", [], None, "Original Sponza hall, untouched")

# ---- geometry-space ----
emit("sp01-float",
     [{"type": "mesh_offset", "meshes": M(87, 88), "dy": 0.55}],
     ANS("floating pot", "potted plant hovers ~0.5m above the floor", 0.95, 1.23, "geometry-space"),
     "One floor pot floats in mid-air")
# v3 (2026-09-12 review): a merely lowered pot read as a shorter pot -> tilted 24 degrees about its base and sunk,
# so one side is clearly below the floor
# v4 (2026-09-14 review): 24 degrees / 0.2 m still read as a short or slightly tilted pot -> 42 degrees, sunk 0.32 m:
# half of the pot is under the floor, the rim points at the ceiling
emit("sp02-clip",
     # v5 (review 2026-09-16: "half of it in the ground, half in the air"): the pot lies tipped 65 degrees towards the hall
     # with its base centre at floor level, so the floor cuts it lengthwise - lower half of the pot, one side of the rim and
     # part of the plant are underground, the other half sticks out at an angle
     [{"type": "mesh_tilt", "meshes": M(89, 90), "deg": -65, "axis": "x", "dy": -0.05}],
     ANS("sunken pot", "one potted plant lies tipped over at about 65 degrees and HALF SUNK into the floor - the lower half "
         "of the pot, one side of its rim and part of the plant are below floor level, the other half sticks up out of the "
         "floor at an angle, while its identical siblings stand upright on the floor", 6.67, 1.23, "geometry-space"),
     "One floor pot is tilted and sunk into the floor")
# v3 (2026-09-12 review): 2.2x clipped into the column behind it and was judged too easy -> 1.6x, shifted 0.3 m into the hall
# sp03-scale retired 2026-09-16 (review rounds 2 and 3): an oversized pot was judged "possible" / "not a definite bug" at 1.6x
# and at 2.8x; an object's absolute scale is not a defect in this scene.
# v2 (2026-09-01): side-by-side overlap read as plausible clutter; real double-spawn lands
# (near-)exactly on top -> doubled shell / z-fighting shimmer on one pot.  v3 (2026-09-12): offset a little larger
# so the doubled rim reads in a 480x300 frame.
emit("sp04-doublespawn",
     [{"type": "mesh_clone", "meshes": M(91, 92), "offset": [0.10, 0.03, 0.08]}],
     ANS("double-spawned pot", "the same pot is spawned twice almost exactly on top of "
         "itself - doubled/shimmering surfaces (z-fighting)", 6.67, -1.78, "geometry-space"),
     "Co-located duplicate pot (double spawn, z-fighting)")

# ---- collision-physics ----
emit("sp05-airwall",
     [{"type": "air_wall", "at": SPW(2.5, -0.3), "size": [0.4, 2.6, 9.0]}],
     ANS("air wall", "invisible barrier blocks the hall mid-way; nothing visible there", 2.5, -0.3,
         "collision-physics", extent_z=4.5),
     "Invisible wall across the hall")
emit("sp06-hole",
     [{"type": "floor_hole", "at": SPW(-4.5, -0.3), "size": [1.7, 1.7]}],
     ANS("floor without collision", "player falls through solid-looking floor here and respawns", -4.5, -0.3,
         "collision-physics", extent_x=0.9, extent_z=0.9),
     "Floor region without collision (fall-through)")
# v3 (2026-08-30): v1 targeted mesh_0 (turned out to be a chain-hung brazier on a solid
# column - untestable); v2 tried a floor planter (knee-high: the capsule steps over it in
# clean too). v3: one drape passable while its 9 siblings are solid barriers.
emit("sp07-ghostdrape",
     [{"type": "mesh_nosolid", "meshes": M(67)}],
     ANS("no-collision drape", "this drape can be walked straight through into the aisle "
         "(every other drape is a solid barrier)", 2.44, 1.56, "collision-physics"),
     "One drape has no collision")
# v2 (2026-09-01): metronome glide had no engine story; physics-solver oscillation does.
emit("sp08-jitter",
     [{"type": "mesh_tremble", "meshes": M(85, 86), "amp": 0.05}],
     ANS("trembling pot", "potted plant trembles/vibrates in place on its own (physics "
         "solver oscillation)", -1.95, 1.22, "collision-physics"),
     "One pot trembles in place (physics jitter)")

# ---- visual-consistency ----
# v3 (2026-09-12 review): a magenta drape could pass as a coloured drape; a stone pot in flat unlit magenta cannot
emit("sp09-magenta",
     [{"type": "mesh_missing_tex", "meshes": M(1, 2)}],
     ANS("missing texture", "one stone floor pot renders flat unlit magenta (texture missing placeholder)", -1.95, -1.8,
         "visual-consistency"),
     "Missing-texture magenta pot")
# v2 (2026-08-30, per project review): cull the BACK side instead - from the hall the drape
# looks and collides perfectly normally; only viewing from the aisle behind reveals it is
# missing there (neighbors stay visible from behind). No invisible-wall confound, and the
# case is discoverable ONLY by physically going around - the hardest viewpoint case.
emit("sp10-backcull",
     [{"type": "mesh_sideview_cull", "meshes": M(63), "normal": [0, 0, 1]}],
     ANS("drape invisible from behind", "drape looks normal from the hall but is invisible "
         "when viewed from the aisle behind it (neighbors stay visible from behind)", -0.49, 1.61,
         "visual-consistency"),
     "Drape culled from the back side (viewpoint-dependent rendering)")
emit("sp11-xray",
     [{"type": "mesh_xray", "meshes": M(1, 2)}],
     ANS("x-ray pot", "a pot renders on top of everything, visible through columns", -1.95, -1.8,
         "visual-consistency"),
     "Pot renders through occluders")

# ---- spatiotemporal-state ----
# v2 (2026-09-01): gaze trigger was artificial; streaming/cell-unload distance semantics.
emit("sp12-unload",
     [{"type": "mesh_despawn_on_leave", "meshes": M(87, 88), "enterR": 5, "exitR": 9}],
     ANS("unloaded pot", "after you visit this spot and walk away, the pot is unloaded "
         "and is gone when you come back", 0.95, 1.23, "spatiotemporal-state"),
     "Pot despawns after the player leaves the area (streaming bug)")
emit("sp13-statereset",
     [{"type": "mesh_reset_on_leave", "meshes": M(89, 90), "offset": [0, 0, -2.4], "enterR": 5, "exitR": 9}],
     ANS("state-reset pot", "each time you leave the area and return, the pot is at a "
         "different position (state not saved)", 6.67, 1.23,
         "spatiotemporal-state", extent_z=1.2),
     "Pot relocates every time the player leaves and returns (unsaved state)")
# v2 (2026-09-01): metronome color flip had no engine story; texture-LOD pop does
# (taxonomy: "different look near vs far / LOD / cull distance").
emit("sp14-lodpop",
     [{"type": "mesh_lod_pop", "meshes": M(67), "dist": 6.0}],
     ANS("texture LOD pop", "beyond ~6m this drape's texture drops to a blocky ultra-low-res "
         "version and pops back sharp when you approach", 2.44, 1.56, "visual-consistency"),
     "Drape texture pops between sharp and blocky with distance (LOD bug)")

# ---- semantics-logic ----
# v3 (2026-09-01, user review): v2 used fabricated crate/torch factory assets; failed-spawn
# piles must consist of REAL scene assets. Clones of Sponza's own planters and a hanging
# brazier are dumped interpenetrating at the world origin (originals stay in place).
# v4 (2026-09-12 review): mid-hall at the origin was too easy and unreal; the pile now sits in the north-east corner of
# the side aisle, behind the last drape (found by walking into the aisle)
# v5 (2026-09-14 review): upright copies standing side by side read as clutter, not a heap; the copies are now tilted
# into and through each other (mesh_pile "rot"), one pot lies on its side on top, the brazier lies with its chains on the floor
emit("sp15-spawnpile",
     [{"type": "mesh_pile", "at": SPW(7.9, 4.0),
       "groups": [{"meshes": M(87, 88), "off": [-0.2, 0, -0.1]},
                  {"meshes": M(91, 92), "off": [0.25, 0.05, 0.2], "rot": [0, 0, 38]},
                  {"meshes": M(89, 90), "off": [-0.05, 0.3, 0.05], "rot": [42, 0, 0]},
                  {"meshes": M(85, 86), "off": [-0.45, 0.28, 0.3], "rot": [0, 0, 62]},
                  {"meshes": M(93, 94), "off": [0.3, 0.32, -0.25], "rot": [0, 0, -115]},
                  {"meshes": M(73, 74), "off": [0.1, 0.05, -0.35], "rot": [78, 0, 0]}]}],
     ANS("prop pile in the aisle corner", "copies of the stone pots, a planter and a hanging brazier are dumped into ONE HEAP "
         "at the east end of the north side aisle, beside the octagonal stone basin and behind the last drape: pots tilted "
         "into and through each other, one lying on its side on top of the heap, the brazier on the floor with its chains - "
         "duplicated real props jammed together (failed spawns)", 7.9, 4.0, "semantics-logic"),
     "Clones of real scene props piled interpenetrating in the north-east aisle corner")

# ---- S1 ladder L3: near-spawn variants (same bugs, spawn inside a small inspection
# zone facing the bug; see harness/tasks.py LADDER_NEAR - single source of truth) ----
import math
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.tasks import LADDER_NEAR  # noqa: E402

for slug, nd in LADDER_NEAR.items():
    (sx, sz), (bx, bz) = nd["spawn"], nd["bug"]
    # env convention: yawDeg -90 faces +x; facing dir = (-sin yaw, -cos yaw)
    yaw = round(math.degrees(math.atan2(-(bx - sx), -(bz - sz))))
    cfg = json.loads((OUT / f"{slug}.json").read_text())
    cfg["name"] = f"{slug}-near"
    cfg["spawn"] = {"scene": "sponza", "pos": SPW(sx, sz), "yawDeg": yaw}
    (OUT / f"{slug}-near.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    ans_src = OUT / f"{slug}.answers.json"
    (OUT / f"{slug}-near.answers.json").write_text(ans_src.read_text())
    print("wrote", f"{slug}-near", f"yaw={yaw}")

print("done:", len(list(OUT.glob('sp*.json'))), "sp files")
