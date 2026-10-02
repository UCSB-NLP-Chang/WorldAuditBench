#!/usr/bin/env python3
"""Generate props.json: static Poly Haven props placed in the sunken park of the Sketchbook world.
Coordinates are world x/z (metres, +x east, +z south); y is resolved at runtime by a downward ray so the
props sit on whatever surface is there (apron, pads, road).  `yaw` is degrees around +y.
Run: make_props.py > props.json  (build.py embeds props.json as window.__SKETCH_PROPS__)
"""
import json, math

P = []


def add(m, x, z, yaw=0.0, **kw):
    P.append({"m": m, "x": round(x, 2), "z": round(z, 2), "yaw": round(yaw, 1), **kw})


def line(m, x0, z0, x1, z1, n, yaw=None):
    """n props evenly spaced from (x0,z0) to (x1,z1); yaw defaults to the line direction."""
    ang = math.degrees(math.atan2(-(z1 - z0), (x1 - x0))) if yaw is None else yaw
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0
        add(m, x0 + (x1 - x0) * t, z0 + (z1 - z0) * t, ang)


# --- A. spawn plaza (character spawns at (0, -5); cars at (-4,-6) and (5,5)) ---------------------
add("tool_cart", -12, -14, 20)
add("portable_generator", -13.5, -11.5, -10)
add("metal_jerrycan_green", -12.3, -9.8, 40)
add("metal_jerrycan_green", -11.6, -9.3, 100)
add("propane_tank", -14.6, -13.3)
add("barrel_03", 15, -15); add("barrel_03", 15.8, -15.2); add("barrel_03", 15.4, -14.4)
add("old_military_crate", 12, 10, 15)
add("plastic_crate_02", 13.4, 9.7, 5); add("plastic_crate_02", 14.1, 9.5, 35)
add("wooden_crate_02", 12.4, 12.2, 80)
add("industrial_storage_cart", -9, 12, 90)
add("industrial_pastic_container", -8.9, 13.6)
add("plastic_crate_01", -10.2, 12.8, 20)
add("fire_hydrant", 18, -20)
line("concrete_road_barrier", -16, 20, 16, 20, 9, 0)
line("concrete_road_barrier", -10, -22, 10, -22, 6, 0)
for x, z in ((-12, -18), (12, -18), (-12, 16), (12, 16)):   # plaza corners (the z=0 axis dips into the trench)
    add("street_lamp_01", x, z, 90 if x < 0 else -90)

# --- B. the two plaster pads inside the oval (0,-60) and (0,60) ---------------------------------
add("portable_generator", 12, -50, 30); add("barrel_03", 13.2, -51.5); add("barrel_03", 13.9, -50.8)
add("tool_cart", -12, -68, -90)
add("old_military_crate", -12, 52, 10); add("plastic_crate_02", -10.6, 52.4, 60)
add("wooden_crate_02", 12, 70); add("propane_tank", 12.8, 71.2); add("barrel_03", 11.5, 71.4)

# --- C. street lamps on the raised grass bands (y = 21) flanking the sunken track bowl, |x| = 55..65 ---
for z in (-60, -20, 20, 60):
    add("street_lamp_01", -60, z, 90)
    add("street_lamp_01", 60, z, -90)

# --- D. east service road (z = 0, x 60..120) and the apron fence beside the runway (x ~ 140) -------
add("street_lamp_01", 75, -7, 0); add("street_lamp_01", 95, -7, 0)
add("concrete_road_barrier", 74, 6, 0); add("concrete_road_barrier", 78, 6, 0)   # east of the band (x < 69 is the band top)
line("chainlink_panel", 140, -60, 140, 60, 61, 90)   # 2 m modules, continuous run

# --- E. helipad / hangar zone (helipad at (100,-83), hangar box at (122..128,-93..-88)) ------------
add("fire_hydrant", 90, -70)
add("portable_generator", 108, -72); add("metal_jerrycan_green", 109.2, -73.4, 20); add("metal_jerrycan_green", 109.8, -72.9, 70)
add("barrel_03", 112, -96); add("barrel_03", 112.8, -95.4); add("barrel_03", 112.3, -94.6)
add("industrial_storage_cart", 118, -80); add("tool_cart", 116, -78, 45)
add("old_military_crate", 119, -90, 90); add("plastic_crate_01", 119.3, -87.6); add("wooden_crate_02", 130.5, -91)
for x, z in ((94, -92), (106, -92), (94, -74), (106, -74)):
    add("concrete_road_barrier_02", x, z, 0)

# --- F. west road, tower roundabout (-142,0) and the stunt-block rows (x -150..-90, z 25..75) -------
add("street_lamp_01", -70, -7, 0); add("street_lamp_01", -90, -7, 0); add("street_lamp_01", -110, -7, 0)
add("concrete_road_barrier", -74, 6, 0); add("concrete_road_barrier", -78, 6, 0)
add("barrel_03", -150, 12); add("barrel_03", -149.2, 12.5)
line("concrete_road_barrier_02", -148, 22, -100, 22, 7, 0)
add("old_military_crate", -92, 30); add("barrel_03", -93, 32); add("barrel_03", -92.2, 32.6)

# --- G. crater / pit north edge (pit spans x 76..113, z 60..96) -------------------------------------
line("concrete_road_barrier", 80, 57, 112, 57, 5, 0)

json.dump(P, open(__import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "/dev/stdout", "w"))
print(len(P), "props", file=__import__("sys").stderr)
