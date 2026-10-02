"""Generate the TC test environments: one isolated bug/clean config pair per bug,
with byte-identical geometry between the pair.

Usage: python scripts/tools/gen_testcases.py   (idempotent; overwrites environments/threejs/runtime/configs/tc*.json)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "environments/threejs/runtime" / "configs"

CORRIDOR = lambda partitions=(), lights=(3, 6, 9, 12, 15): {
    "type": "corridor", "id": "c", "length": 16, "width": 4, "height": 3,
    "partitions": list(partitions), "lightsX": list(lights),
}
SPAWN = {"scene": "c", "yawDeg": -90}
LOC = lambda x, z, **kw: {"scene": "c", "local": [x, z], **kw}

def emit(name, scenes, objects, bugs, answers, targets, meta_desc):
    cfg = {
        "name": name,
        "meta": {"title": name, "desc": meta_desc},
        "seed": 5, "scenes": scenes,
        "spawn": SPAWN if scenes[0]["type"] == "corridor" else {"scene": "sponza", "yawDeg": -90},
        "objects": objects, "bugs": bugs, "targets": targets,
    }
    (OUT / f"{name}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    if answers:
        (OUT / f"{name}.answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=1))
    print("wrote", name, f"({len(bugs)} bugs)")

# -- tc01 auto-closing door (door_autoclose) --
door_layout = dict(
    scenes=[CORRIDOR(partitions=[{"x": 7, "openWidth": 2, "openHeight": 3}])],
    objects=[{"type": "door", "id": "door_a", "at": LOC(7.2, -1), "width": 2, "sign": 1}],
    targets={"zone_tc": LOC(7.2, 0)})
emit("tc01-autoclose-bug", **door_layout,
     bugs=[{"type": "door_autoclose", "target": "door_a", "afterMs": 2000}],
     answers=[{"name": "auto-closing door", "where": "wooden door closes by itself ~2s after opening",
               "at": LOC(7.2, 0), "bug": "door_autoclose", "level": "L3"}],
     meta_desc="Corridor door that closes by itself 2s after opening")
emit("tc01-autoclose-clean", **door_layout, bugs=[], answers=None, meta_desc="Corridor door: normal")

# -- tc02 instant-open door / tc03 half-stuck door (direct-interact door;
#    levers proved inoperable for VLM agents: 0/40) --
door2_layout = dict(
    scenes=[CORRIDOR(partitions=[{"x": 7, "openWidth": 2, "openHeight": 3}])],
    objects=[{"type": "door", "id": "door_a", "at": LOC(7.2, -1), "width": 2, "sign": 1}],
    targets={"zone_tc": LOC(7.2, 0)})
emit("tc02-accel-bug", **door2_layout,
     bugs=[{"type": "anim_accelerated", "target": "door_a", "factor": 10}],
     answers=[{"name": "instant-open door", "where": "door snaps to fully open with no animation (should swing smoothly)",
               "at": LOC(7.2, 0), "bug": "anim_accelerated", "level": "L3"}],
     meta_desc="Door snaps open instantly with no animation")
emit("tc02-accel-clean", **door2_layout, bugs=[], answers=None, meta_desc="Door: normal")
emit("tc03-interrupt-bug", **door2_layout,
     bugs=[{"type": "anim_interrupted", "target": "door_a", "t": 0.5}],
     answers=[{"name": "half-stuck door", "where": "door opens only halfway, jams, and still blocks passage",
               "at": LOC(7.2, 0), "bug": "anim_interrupted", "level": "L3"}],
     meta_desc="Door jams half-open and still blocks passage")
emit("tc03-interrupt-clean", **door2_layout, bugs=[], answers=None, meta_desc="Door: normal")

# -- tc04 self-drifting crate (drift) -- moving/static pair --
drift_layout = dict(
    scenes=[CORRIDOR()],
    objects=[
        {"type": "crate", "id": "crate_m", "at": LOC(6, -1), "solid": False},
        {"type": "crate", "id": "crate_s", "at": LOC(6, 1), "solid": False}],
    targets={"zone_tc": LOC(6, 0)})
emit("tc04-drift-bug", **drift_layout,
     bugs=[{"type": "drift", "target": "crate_m", "axis": "x", "speed": 0.25, "range": 2}],
     answers=[{"name": "self-drifting crate", "where": "south crate slides back and forth on its own",
               "at": LOC(6, -1), "extent_x": 2, "bug": "drift", "level": "L3"}],
     meta_desc="One crate drifts back and forth untouched")
emit("tc04-drift-clean", **drift_layout, bugs=[], answers=None, meta_desc="Two crates: static, normal")

# -- tc05 wall trap (wall_trap) vs solid pillar --
emit("tc05-walltrap-bug",
     scenes=[CORRIDOR()],
     objects=[],
     bugs=[{"type": "wall_trap", "at": LOC(7, 0), "size": [1.2, 2.8, 1.2]}],
     answers=[{"name": "wall trap", "where": "stone pillar: the south face lets you slip inside; once inside you are stuck",
               "at": LOC(7, 0), "bug": "wall_trap", "level": "L2"}],
     targets={"zone_tc": LOC(7, 0)},
     meta_desc="Pillar with one enterable face that traps the player inside")
emit("tc05-walltrap-clean",
     scenes=[CORRIDOR()],
     objects=[{"type": "pillar", "id": "pillar_a", "at": LOC(7, 0), "size": [1.2, 2.8, 1.2]}],
     bugs=[], answers=None, targets={"zone_tc": LOC(7, 0)},
     meta_desc="Solid pillar: collision normal")

# -- tc06 interact through closed gate (interact_through_wall) --
tw_layout = dict(
    scenes=[CORRIDOR(partitions=[{"x": 8, "openWidth": 3, "openHeight": 3}])],
    objects=[
        {"type": "portcullis", "id": "gate_b", "at": LOC(8.2, 0), "width": 3, "height": 3},
        {"type": "chest", "id": "chest_b", "at": LOC(9.0, 0.5), "yaw": 0, "gem": "gem_b", "solid": True}],
    targets={"zone_tc": LOC(8.2, 0)})
emit("tc06-throughwall-bug", **tw_layout,
     bugs=[{"type": "interact_through_wall", "target": "chest_b"}],
     answers=[{"name": "interact through barrier", "where": "the chest behind the closed gate can be opened through the gate",
               "at": LOC(8.2, 0), "bug": "interact_through_wall", "level": "L3"}],
     meta_desc="Chest can be opened through the closed iron gate")
emit("tc06-throughwall-clean", **tw_layout, bugs=[], answers=None,
     meta_desc="Gate correctly blocks interaction")

# -- tc07 full-screen tint (corrupted_frame) --
tint_layout = dict(
    scenes=[CORRIDOR()],
    objects=[{"type": "crate", "id": "c1", "at": LOC(6, -1.2), "solid": True},
             {"type": "crate", "id": "c2", "at": LOC(9, 1.2), "solid": True}],
    targets={"zone_tc": LOC(7, 0)})
emit("tc07-tint-bug", **tint_layout,
     bugs=[{"type": "corrupted_frame", "color": "#ff0033", "opacity": 0.35}],
     answers=[{"name": "screen tint", "where": "the whole screen is polluted by a red color tint",
               "at": LOC(7, 0), "bug": "corrupted_frame", "level": "L1", "global": True}],
     meta_desc="Full-screen red tint")
emit("tc07-tint-clean", **tint_layout, bugs=[], answers=None, meta_desc="Rendering normal")

# -- tc08 out-of-place asset (extra_asset, Sponza) --
sponza = [{"type": "gltf", "id": "sponza", "url": "/assets/sponza/Sponza.gltf"}]
SLOC = lambda x, z: {"scene": "sponza", "spawnOffset": [x, z], "snap": True}
emit("tc08-extra-bug", scenes=sponza, objects=[],
     bugs=[{"type": "extra_asset", "object": {"type": "portcullis", "id": "odd_gate",
                                              "at": SLOC(5, 0), "width": 3, "height": 3}}],
     answers=[{"name": "out-of-place gate", "where": "an iron portcullis stands mid-walkway, attached to nothing",
               "at": SLOC(5, 0), "bug": "extra_asset", "level": "L1"}],
     targets={"zone_tc": SLOC(5, 0)},
     meta_desc="A portcullis appears out of nowhere in the Sponza walkway")
emit("tc08-extra-clean", scenes=sponza, objects=[], bugs=[], answers=None,
     targets={"zone_tc": SLOC(5, 0)}, meta_desc="Sponza walkway: normal")

# -- tc09 sunken crate (sink = float with negative dy) --
sink_layout = dict(
    scenes=[CORRIDOR()],
    objects=[{"type": "crate", "id": "k1", "at": LOC(5, -1), "solid": True},
             {"type": "crate", "id": "k2", "at": LOC(6.5, 0), "solid": True},
             {"type": "crate", "id": "k3", "at": LOC(8, 1), "solid": True}],
    targets={"zone_tc": LOC(6.5, 0)})
emit("tc09-sink-bug", **sink_layout,
     bugs=[{"type": "float", "target": "k2", "dy": -0.4}],
     answers=[{"name": "sunken crate", "where": "the middle crate's lower half is buried in the floor",
               "at": LOC(6.5, 0), "bug": "sink", "level": "L1"}],
     meta_desc="Middle crate half-sunk into the floor")
emit("tc09-sink-clean", **sink_layout, bugs=[], answers=None, meta_desc="Three crates resting normally")

# -- tc10 invisible obstacle (solid crate + vanish) --
emit("tc10-invisible-bug",
     scenes=[CORRIDOR()],
     objects=[{"type": "crate", "id": "ghost_c", "at": LOC(7, 0), "solid": True}],
     bugs=[{"type": "vanish", "target": "ghost_c"}],
     answers=[{"name": "invisible obstacle", "where": "an invisible but solid crate blocks the middle of the corridor",
               "at": LOC(7, 0), "bug": "invisible_obstacle", "level": "L2"}],
     targets={"zone_tc": LOC(7, 0)},
     meta_desc="Invisible crate blocking the corridor")
emit("tc10-invisible-clean",
     scenes=[CORRIDOR()], objects=[], bugs=[], answers=None,
     targets={"zone_tc": LOC(7, 0)}, meta_desc="Corridor clear")

print("done:", len(list(OUT.glob('tc*.json'))), "tc files")
