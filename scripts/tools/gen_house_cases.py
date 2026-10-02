"""Generate the HS test suite: bugs implanted as mutations of the Family House scene
(environments/threejs/runtime/house/house.js), the second real environment of the benchmark (2026-09-06).

Same design as scripts/tools/gen_sponza_cases.py (SP suite):
- every bug is a mutation of the scene's OWN elements, judged against internal consistency
  (4 identical dining chairs, 3 bar stools, 2 nightstands, 2 living-room armchairs ...);
- the 15 cases mirror sp01..sp15 type-for-type (same bug implementations in environments/threejs/runtime/bugs.js), so
  results are comparable across environments;
- ONE shared clean config (hs00-clean); every bug config differs from it by one mutation;
- a uniform neutral patrol instruction (agent/vla/tasks.py) - no per-case priming.

Object names are TAG#n in placement order (environments/threejs/runtime/house/house.js assignNames); positions below are
the furnishing-plan coordinates (verified by agent/vla/hs_verify.py against the live scene).
World axes: x east, z south (front door at z=+5), y up; upper floor at y=3.

Usage: python scripts/tools/gen_house_cases.py   (idempotent; overwrites environments/threejs/runtime/configs/hs*.json)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "environments/threejs/runtime" / "configs"

HOUSE = [{"type": "house", "id": "house"}]
SPAWN = {"scene": "house", "pos": [0.55, 0.0, 3.9], "yawDeg": 0}   # hall by the front door, facing north
PLAYER = {"radius": 0.22}
BOUNDS = {"minX": -6.6, "maxX": 6.6, "minZ": -4.6, "maxZ": 4.6}


# verification viewpoints for tools (scratch packed_shots.py): [x, y, z, yaw, pitch] camera specs per case
VIEWS = {
    "hs03-scale": [[2.5, 3.0, -2.3, 4.0, 3.5, -3.6]],
    "hs11-xray": [[0.6, 3.0, -0.4, -3.25, 3.5, -0.05], [-2.8, 3.0, 3.0, -3.25, 3.5, -0.05]],
    "hs14-lodpop": [[0.8, 3.0, 2.8, 4.4, 3.5, -0.04], [3.0, 3.0, 1.0, 4.4, 3.5, -0.04]],
    "hs15-spawnpile": [[2.4, 3.0, -1.6, 2.9, 3.4, -3.3], [3.6, 3.0, -2.0, 2.9, 3.4, -3.3]],
}
def _view(cx, cy, cz, tx, ty, tz):
    import math
    return [cx, cy, cz, round(math.atan2(-(tx - cx), -(tz - cz)), 3), round(math.atan2(ty - (cy + 1.6), math.hypot(tx - cx, tz - cz)), 3)]


def emit(name, bugs, answers, desc):
    cfg = {
        "name": name,
        "meta": {"title": name, "desc": desc},
        "seed": 5,
        "scenes": HOUSE,
        "spawn": SPAWN,
        "player": PLAYER,
        "bounds": BOUNDS,
        # boundary notice zones (core.js): pushing against the locked front door / glass door shows the
        # "edge of the explorable area" notice for 1.5 s (composited into the agent's frames as well)
        "notice": [{"x": 0.0, "z": 4.85, "r": 0.8}, {"x": 0.7, "z": -4.85, "r": 0.8}],
        "objects": [],
        "bugs": bugs,
        # zone_far: the upstairs lounge (patrol end point; audit runs only log the distance)
        "targets": {"zone_far": [4.4, 3.0, 3.2]},
    }
    if name in VIEWS:
        cfg["views"] = [_view(*v) for v in VIEWS[name]]
    (OUT / f"{name}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    if answers:
        (OUT / f"{name}.answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=1))
    print("wrote", name)


ANS = lambda name, where, x, y, z, cat, **kw: [{
    "name": name, "where": where, "at": [x, y, z], "category": cat, **kw}]

# carrier positions (plan coordinates)
CHAIR = {1: (5.11, 2.91), 2: (5.11, 1.49), 3: (3.69, 1.49), 4: (3.69, 2.91)}   # dining chairs around the table (4.4, 2.2)
STOOL = {1: (3.7, -1.75), 2: (4.4, -1.75), 3: (5.1, -1.75)}                    # kitchen bar stools
ARMCHAIR = {1: (-6.1, 0.9), 2: (-6.1, 2.6)}                                    # living-room armchairs

emit("hs00-clean", [], None, "Family house, untouched")

# ---- geometry-space ----
emit("hs01-float",
     [{"type": "mesh_offset", "meshes": ["DINING_CHAIR#1"], "dy": 0.45}],
     ANS("floating chair", "one dining chair hovers ~0.45 m above the floor (its three siblings stand on the floor)",
         *CHAIR[1][:1], 0.0, CHAIR[1][1], "geometry-space"),
     "One dining chair floats in mid-air")
# v2 (2026-09-14 review): a stool merely lowered 0.3 m read as a shorter stool; now tipped over 34 degrees about its base
# (seat leaning back into the kitchen) AND sunk 0.28 m, so its front legs are under the floor and the seat cuts through it
emit("hs02-clip",
     [{"type": "mesh_tilt", "meshes": ["BAR_STOOL#3"], "deg": 34, "axis": "x", "dy": -0.28}],
     ANS("sunken bar stool", "one of the three identical kitchen bar stools is tipped over at about 35 degrees and sunk into "
         "the floor - its legs are under the floor and only the tilted seat sticks out just above the floor, while the two "
         "stools next to it stand upright", STOOL[3][0], 0.0, STOOL[3][1], "geometry-space"),
     "One bar stool is tilted and sunk into the kitchen floor")
# v2 (2026-09-12 review): the 1.8x dining chair clipped its neighbours and looked unnatural; now the kids-room desk
# chair upstairs at 1.7x (a chair taller than its desk), shifted clear of the desk
emit("hs03-scale",
     [{"type": "mesh_scale", "meshes": ["CHAIR#1"], "factor": 1.7, "shift": [0, 0.18]}],
     ANS("oversized chair", "the desk chair in the kids room upstairs is ~1.7x normal size - taller than the desk it stands at",
         4.0, 3.0, -3.6, "geometry-space"),
     "The kids-room desk chair upstairs is abnormally oversized")
emit("hs04-doublespawn",
     [{"type": "mesh_clone", "meshes": ["ARMCHAIR#2"], "offset": [0.09, 0.03, 0.07]}],
     ANS("double-spawned armchair", "the same armchair is spawned twice almost exactly on top of itself - "
         "doubled/shimmering surfaces (z-fighting)", ARMCHAIR[2][0], 0.0, ARMCHAIR[2][1], "geometry-space"),
     "Co-located duplicate armchair (double spawn, z-fighting)")

# ---- collision-physics ----
# hall is 3.5 m wide; the wall spans it at z=0.9 (north half reachable around via dining->kitchen)
emit("hs05-airwall",
     [{"type": "air_wall", "at": [0.0, 0.0, 0.9], "size": [3.4, 2.6, 0.4]}],
     ANS("air wall", "invisible barrier across the entrance hall; nothing visible there", 0.0, 0.0, 0.9,
         "collision-physics", extent_x=1.7),
     "Invisible wall across the hall")
emit("hs06-hole",
     [{"type": "floor_hole", "at": [0.6, 0.0, -1.9], "size": [1.4, 1.4]}],
     ANS("floor without collision", "player falls through solid-looking hall floor here and respawns", 0.6, 0.0, -1.9,
         "collision-physics", extent_x=0.7, extent_z=0.7),
     "Hall floor region without collision (fall-through)")
emit("hs07-ghostisland",
     [{"type": "mesh_nosolid", "meshes": ["KITCHEN_ISLAND#1"]}],
     ANS("no-collision island", "the kitchen island can be walked straight through (every other piece of furniture is solid)",
         4.4, 0.0, -2.6, "collision-physics", extent_x=1.0, extent_z=0.45),
     "Kitchen island has no collision")
emit("hs08-jitter",
     [{"type": "mesh_tremble", "meshes": ["FLOOR_LAMP#1"], "amp": 0.03}],
     ANS("trembling floor lamp", "the living-room floor lamp trembles/vibrates in place on its own (physics solver oscillation)",
         -6.45, 0.0, -0.75, "collision-physics"),
     "Living-room floor lamp trembles in place (physics jitter)")

# ---- visual-consistency ----
emit("hs09-magenta",
     [{"type": "mesh_missing_tex", "meshes": ["TV_CONSOLE#1"]}],
     ANS("missing texture", "the TV cabinet renders flat solid magenta (texture missing)", -3.2, 0.0, -0.86,
         "visual-consistency"),
     "Missing-texture magenta TV cabinet")
# visible from the room's front/north side, invisible when viewed from behind (south, window side)
# v2 (2026-09-15): the throw pillows on the sofa are culled with it (they used to stay behind, floating in mid-air)
emit("hs10-backcull",
     [{"type": "mesh_sideview_cull", "meshes": ["SOFA#1", "PILLOW#1"], "normal": [0, 0, 1]}],
     ANS("sofa invisible from behind", "the living-room sofa looks normal from the TV side but is invisible when viewed "
         "from behind it - walk round the sofa into the gap between its back and the window wall (still inside the room) "
         "and it disappears; step back in front of it and it is there again", -3.2, 0.0, 2.35, "visual-consistency"),
     "Sofa culled from the back side (viewpoint-dependent rendering)")
# v2 (2026-09-12 review): the x-ray coffee table read as a sofa pattern; now the master bed upstairs, drawn through the
# bedroom walls (seen from the landing and the lounge)
emit("hs11-xray",
     [{"type": "mesh_xray", "meshes": ["BED#1"]}],
     ANS("x-ray bed", "the master bed upstairs renders on top of everything - visible through the bedroom walls from the landing",
         -3.25, 3.0, -0.05, "visual-consistency", extent_x=0.8, extent_z=1.0),
     "Master bed renders through walls")

# ---- spatiotemporal-state ----
emit("hs12-unload",   # v2 (2026-09-12): exitR 7 -> 5: leaving the living room is enough
     [{"type": "mesh_despawn_on_leave", "meshes": ["PLANT#1"], "enterR": 3.5, "exitR": 5.0}],
     ANS("unloaded plant", "after you visit the living-room corner and walk away, the potted plant is unloaded and "
         "is gone when you come back", -6.35, 0.0, 4.4, "spatiotemporal-state"),
     "Living-room plant despawns after the player leaves the area (streaming bug)")
emit("hs13-statereset",   # v2 (2026-09-12): exitR 7 -> 5: leaving the dining room is enough
     [{"type": "mesh_reset_on_leave", "meshes": ["DINING_CHAIR#2"], "offset": [1.2, 0, -0.8], "enterR": 3.5, "exitR": 5.0}],
     ANS("state-reset chair", "each time you leave the dining room and return, one dining chair is at a different "
         "position (state not saved)", CHAIR[2][0], 0.0, CHAIR[2][1], "spatiotemporal-state", extent_x=0.7, extent_z=0.5),
     "Dining chair relocates every time the player leaves and returns (unsaved state)")
# v2 (2026-09-12 review): the rug has no texture map, so the mip drop never showed; now a geometry LOD pop on the
# upstairs lounge sofa (a crude flat box from more than ~3.5 m, the real sofa up close)
emit("hs14-lodpop",
     [{"type": "mesh_lod_pop", "meshes": ["SOFA#2"], "dist": 3.5, "proxy": True, "color": "#6d6a66"}],
     ANS("LOD pop", "beyond ~3.5 m the sofa in the upstairs lounge is drawn as a crude flat grey box and pops into the "
         "real sofa when you approach", 4.4, 3.0, -0.04, "visual-consistency", extent_x=1.3),
     "Upstairs lounge sofa pops between a crude box and the real model with distance (LOD bug)")

# ---- semantics-logic ----
# v2 (2026-09-12 review): the hall pile was too easy; now in the kids room upstairs
emit("hs15-spawnpile",
     [{"type": "mesh_pile", "at": [2.9, 3.0, -3.3],
       "groups": [{"meshes": ["DINING_CHAIR#4"], "off": [-0.2, 0, -0.1]},
                  {"meshes": ["BAR_STOOL#1"], "off": [0.22, 0, 0.15]},
                  {"meshes": ["NIGHTSTAND#1"], "off": [-0.05, 0.3, 0.05]},
                  {"meshes": ["ARMCHAIR#1"], "off": [0.1, 0.05, -0.3]}]}],
     ANS("prop pile in the kids room", "copies of a dining chair, a bar stool, a nightstand and an armchair are jammed into "
         "each other in a corner of the kids room upstairs - duplicated real furniture dumped there (failed spawns)",
         2.9, 3.0, -3.3, "semantics-logic"),
     "Clones of real furniture piled interpenetrating in the kids room upstairs")

print("done:", len(list(OUT.glob('hs*.json'))), "hs files")


# ---- S1 ladder L3: near-spawn variants (spawn at the verified S3 viewpoint facing the bug;
# see agent/vla/tasks.py HS_LADDER_NEAR - single source of truth) ----
import math, sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent.vla.tasks import HS_LADDER_NEAR  # noqa: E402

for slug, nd in HS_LADDER_NEAR.items():
    cfg = json.loads((OUT / f"{slug}.json").read_text())
    sx, sz = nd["spawn"]; bx, bz = nd["bug"]
    yaw = round(math.degrees(math.atan2(-(bx - sx), -(bz - sz))), 1)   # forward = (-sin yaw, -cos yaw)
    cfg["name"] = f"{slug}-near"
    cfg["meta"] = dict(cfg.get("meta", {}), title=f"{slug}-near", desc=cfg.get("meta", {}).get("desc", "") + " (L3 near spawn)")
    cfg["spawn"] = {"scene": "house", "pos": [sx, nd.get("y", 0.0), sz], "yawDeg": yaw}
    (OUT / f"{slug}-near.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    ans_src = OUT / f"{slug}.answers.json"
    if ans_src.exists():
        (OUT / f"{slug}-near.answers.json").write_text(ans_src.read_text())
    print("wrote", f"{slug}-near", f"yaw={yaw}")
