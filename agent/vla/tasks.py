"""Task definitions: instruction, target, success condition, step budget.

Success is judged by the runner: after each step, dist(pos, targets[target]) < radius;
checkpoints are intermediate targets that must be reached in order (multi-stage tasks).
"""

TASKS = {
    # env0 smoke navigation (walked by the scripted policy; also usable as a VLM warm-up task)
    "corridor_ring": dict(
        config="env0-corridor", target="ring_end", radius=3.0, steps=30,
        instr="You are in a stone corridor. Reach the glowing CYAN ring on the floor at the far end. "
              "On the way there is a closed wooden door: face it within 3 meters and use interact to open it. "
              "Further on, an iron portcullis gate blocks the way; it cannot be pushed open - find the small "
              "lever on the right-hand side near the gate, face it (you may need to look down) and use "
              "interact, then walk through. Finally stand on the cyan ring."),

    # -- S1 navigation probe (env1, Sponza, no bugs) --
    "ring_visible": dict(
        config="env1-sponza-nav", target="ring_cyan", radius=3.0, steps=40,
        instr="Find the glowing CYAN ring lying on the floor and walk onto it. "
              "It is somewhere ahead of you. The task succeeds when you are standing on it."),
    "ring_search": dict(
        config="env1-sponza-nav", target="ring_purple", radius=3.0, steps=40,
        instr="Find the glowing PURPLE ring lying on the floor and walk onto it. "
              "It is NOT in front of you at the start - you will need to turn around and search. "
              "The task succeeds when you are standing on it."),
    "ring_multi": dict(
        config="env1-sponza-nav", target="ring_cyan", radius=3.0, steps=60,
        checkpoints=[("ring_orange", 3.0)],
        instr="Two-stage task. First find the glowing ORANGE ring on the floor and walk onto it. "
              "After you have stood on the orange ring, find the glowing CYAN ring and walk onto that. "
              "Only stepping on them in this order counts."),
}

# -- S2 targeted audit: directional hints minimize navigation difficulty to isolate bug recognition --
_AUDIT_EAST = ("Inspect the area roughly 6 meters straight AHEAD of you, in the middle of the hall. "
               "Walk into and through that area, look around from more than one angle, and test "
               "whether movement behaves normally there.")
_AUDIT_WEST = ("First TURN AROUND (the area is behind you). Then inspect the area roughly 5 meters "
               "ahead of you and slightly to your left, near the wooden crate. Walk around it and "
               "look at it from more than one angle.")

_AUDIT_TORCH = ("TWO torches (wooden post with a flame on top) stand on the walkway a few meters "
                "ahead of you - they are ALREADY clearly visible from your starting position, one "
                "slightly left, one slightly right. Do NOT walk past them. Observe them and their "
                "flames carefully from where you are (or one small step closer). Watch them for "
                "several seconds - use the wait action at least once and observe how they behave "
                "over time - before concluding whether everything looks and behaves the way a "
                "normal game world should.")

for _name, _cfg, _instr, _zone in [
    ("audit_east_bug", "env2-sponza-2bugs", _AUDIT_EAST, "zone_east"),
    ("audit_west_bug", "env2-sponza-2bugs", _AUDIT_WEST, "zone_west"),
    ("audit_east_clean", "env2-sponza-clean", _AUDIT_EAST, "zone_east"),
    ("audit_west_clean", "env2-sponza-clean", _AUDIT_WEST, "zone_west"),
    ("audit_torch_bug", "env2-temporal-bug", _AUDIT_TORCH, "zone_torch"),
    ("audit_torch_clean", "env2-temporal-clean", _AUDIT_TORCH, "zone_torch"),
]:
    TASKS[_name] = dict(config=_cfg, kind="audit", zone=_zone, steps=20, instr=_instr)

# -- TC test cases (environment-layer bugs per Butt et al. taxonomy; bug/clean pairs share instructions) --
_TC = {
    "tc01": ("A wooden door blocks the corridor about 6 meters ahead. Open it with interact, "
             "watch how it behaves for a few seconds, then pass through to the far side. "
             "Verify the door behaves like a normal game door."),
    "tc02": ("A wooden door blocks the corridor about 6 meters ahead. Open it with interact and WATCH carefully how it moves as it opens, then try to pass through. Verify the door behaves like a normal game door."),
    "tc03": ("A wooden door blocks the corridor about 6 meters ahead. Open it with interact and WATCH carefully how it moves as it opens, then try to pass through. Verify the door behaves like a normal game door."),
    "tc04": ("Two wooden crates sit in the corridor about 5 meters ahead. Walk closer, then stand "
             "still and observe the area for several seconds (use wait at least once). "
             "Verify everything behaves normally."),
    "tc05": ("A stone pillar stands in the middle of the corridor ahead. Walk around it and test "
             "its collision by walking against its different sides. Verify physics behaves normally."),
    "tc06": ("A closed iron gate blocks the corridor; a chest is visible behind it through the bars. "
             "The gate cannot be opened. Inspect the area and test whether interactions respect "
             "physical barriers - try interacting with what you can see."),
    "tc07": ("Walk down the corridor and inspect the area. Verify the world renders normally."),
    "tc08": ("Walk forward through the hall for about 8 meters, inspecting whether everything you "
             "see belongs in the scene and renders normally."),
    "tc09": ("Three wooden crates sit in the corridor ahead. Walk up and inspect each of them from "
             "a couple of meters away. Verify they are placed normally."),
    "tc10": ("Walk down the corridor all the way to the far end. Verify movement behaves normally "
             "along the way."),
}
_TC_CFG = {
    "tc01": "tc01-autoclose", "tc02": "tc02-accel", "tc03": "tc03-interrupt",
    "tc04": "tc04-drift", "tc05": "tc05-walltrap", "tc06": "tc06-throughwall",
    "tc07": "tc07-tint", "tc08": "tc08-extra", "tc09": "tc09-sink", "tc10": "tc10-invisible",
}
for _tc, _instr in _TC.items():
    for _v in ("bug", "clean"):
        TASKS[f"audit_{_tc}_{_v}"] = dict(
            config=f"{_TC_CFG[_tc]}-{_v}", kind="audit", zone="zone_tc", steps=15, instr=_instr)

# -- SP suite: Sponza-native bugs (mutations of the real scene; project taxonomy v2) --
# ONE uniform neutral instruction for every case - no per-case priming; the bug/clean split
# and the scene's own regularities are the only signal.
_SP_INSTR = (
    "You are QA-testing this palace atrium hall. Patrol it: walk the full length of the hall "
    "to the far end (about 18 meters ahead), look around along the way, and inspect anything "
    "that seems off - approach it, view it from more than one angle, and re-check it if "
    "needed. Report every bug you find with flag; if the hall is normal, finish with done "
    "without flagging.")
_SP_CFG = {
    "sp01": "sp01-float", "sp02": "sp02-clip", "sp04": "sp04-doublespawn",   # sp03-scale retired 2026-09-16
    "sp05": "sp05-airwall", "sp06": "sp06-hole", "sp07": "sp07-ghostdrape", "sp08": "sp08-jitter",
    "sp09": "sp09-magenta", "sp10": "sp10-backcull", "sp11": "sp11-xray", "sp12": "sp12-unload",
    "sp13": "sp13-statereset", "sp14": "sp14-lodpop", "sp15": "sp15-spawnpile",
}
for _sp, _cfg in _SP_CFG.items():
    TASKS[f"audit_{_sp}_bug"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=25, instr=_SP_INSTR)
TASKS["audit_sp00_clean"] = dict(config="sp00-clean", kind="audit", zone="zone_far", steps=25, instr=_SP_INSTR)

# -- HS suite (2026-09-06): the Family House (environments/threejs/runtime/house/house.js), second real environment.
# Same design as SP: ONE neutral patrol instruction, hs00 clean shared, hsXX = one mutation.
_HS_INSTR = (
    "You are QA-testing this two-storey family house. Patrol it: walk through every room on "
    "the ground floor (living room, study, bathroom, laundry, kitchen, dining room), then take "
    "the stairs and walk through every room upstairs (bedroom, en-suite, dressing room, kids "
    "room, family lounge). Look around along the way and inspect anything that seems off - "
    "approach it, view it from more than one angle, and re-check it if needed. Report every "
    "bug you find with flag; if the house is normal, finish with done without flagging.")
_HS_CFG = {
    "hs01": "hs01-float", "hs02": "hs02-clip", "hs03": "hs03-scale", "hs04": "hs04-doublespawn",
    "hs05": "hs05-airwall", "hs06": "hs06-hole", "hs07": "hs07-ghostisland", "hs08": "hs08-jitter",
    "hs09": "hs09-magenta", "hs10": "hs10-backcull", "hs11": "hs11-xray", "hs12": "hs12-unload",
    "hs13": "hs13-statereset", "hs14": "hs14-lodpop", "hs15": "hs15-spawnpile",
}
for _hs, _cfg in _HS_CFG.items():
    TASKS[f"audit_{_hs}_bug"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=90, instr=_HS_INSTR)
TASKS["audit_hs00_clean"] = dict(config="hs00-clean", kind="audit", zone="zone_far", steps=90, instr=_HS_INSTR)

# -- S1 difficulty ladder (2026-09-02): three priors added cumulatively on top of the
# L0 baseline above (audit_spXX_bug = no priors), hard -> easy:
#   L1  existence prior: told exactly ONE bug is present (clean arm dropped - the prompt
#       asserts a bug, so it cannot honestly run on sp00; L0 already measures clean FP).
#   L2  + type prior: told the bug's taxonomy category plus two textbook examples of it.
#       The example pair is FIXED per category, so for some cases one example coincides
#       with the planted instance (exact-example cases) while sibling cases get type-only
#       information - reported as a sub-split, not hidden.
#   L3  + space prior: spXX-*-near configs spawn inside a small inspection zone that
#       contains the bug; the instruction pins the bug within LADDER_NEAR[r] meters and
#       the runner emits an out-of-zone note (soft fence - no physical walls, which would
#       collide with the airwall bug type).
# LADDER_NEAR is the single source of truth for near spawns; scripts/tools/gen_sponza_cases.py
# imports it to emit the -near configs. sp12/sp13 zones are 12 m because their triggers
# need leaving beyond exitR=9 m from the object and returning.
LADDER_NEAR = {
    "sp01-float":       dict(spawn=(-2.0, -0.3), bug=(0.95, 1.23),  r=6),
    "sp02-clip":        dict(spawn=(3.7, -0.3),  bug=(6.67, 1.23),  r=6),
    "sp04-doublespawn": dict(spawn=(3.7, 0.3),   bug=(6.67, -1.78), r=6),
    "sp05-airwall":     dict(spawn=(-0.8, -0.3), bug=(2.5, -0.3),   r=6),
    "sp06-hole":        dict(spawn=(-7.6, -0.3), bug=(-4.5, -0.3),  r=6),
    "sp07-ghostdrape":  dict(spawn=(2.44, -1.2), bug=(2.44, 1.56),  r=6),
    "sp08-jitter":      dict(spawn=(-4.9, -0.2), bug=(-1.95, 1.22), r=6),
    "sp09-magenta":     dict(spawn=(-4.9, -0.6), bug=(-1.95, -1.8), r=6),   # v3: magenta pot (was a drape)
    "sp10-backcull":    dict(spawn=(-0.49, -1.2), bug=(-0.49, 1.61), r=6),
    "sp11-xray":        dict(spawn=(-4.9, -0.6), bug=(-1.95, -1.8), r=6),
    "sp12-unload":      dict(spawn=(-2.0, -0.3), bug=(0.95, 1.23),  r=12),
    "sp13-statereset":  dict(spawn=(3.7, -0.3),  bug=(6.67, 1.23),  r=12),
    "sp14-lodpop":      dict(spawn=(-4.0, 0.0),  bug=(2.44, 1.56),  r=8),
    "sp15-spawnpile":   dict(spawn=(6.0, 3.6),   bug=(7.9, 4.0),    r=6),   # v4: aisle corner (was the origin)
}

# category names match the AUDIT_SYSTEM taxonomy headings; examples are the two most
# canonical textbook manifestations of each category
_LADDER_CATS = {
    "geometry":  ("GEOMETRY & SPACE",
                  "an object floating in mid-air with no support",
                  "an object clipped halfway into the floor"),
    "collision": ("COLLISION & PHYSICS",
                  "an invisible wall blocking a clear path",
                  "falling through a solid-looking floor"),
    "visual":    ("VISUAL CONSISTENCY",
                  "a missing texture showing as a flat unnatural color",
                  "an object invisible from some viewpoints but visible from others"),
    "state":     ("SPATIOTEMPORAL & STATE CONSISTENCY",
                  "an object that is gone when you come back to where you saw it",
                  "an object that sits at a different position each time you revisit it"),
    "semantic":  ("SEMANTICS & WORLD LOGIC",
                  "an asset dumped somewhere it does not belong",
                  "multiple copies of a prop jammed into one spot"),
}
_CASE_CAT = {
    "sp01": "geometry", "sp02": "geometry", "sp03": "geometry", "sp04": "geometry",   # sp03 kept: the HS map is derived from this one
    "sp05": "collision", "sp06": "collision", "sp07": "collision", "sp08": "collision",
    "sp09": "visual", "sp10": "visual", "sp11": "visual", "sp14": "visual",
    "sp12": "state", "sp13": "state", "sp15": "semantic",
}

_L1_INSTR = (
    "You are QA-testing this palace atrium hall. Exactly ONE bug has been injected into it, "
    "and it is definitely present. Patrol the hall: walk the full length to the far end "
    "(about 18 meters ahead), look around along the way, and inspect anything that seems off "
    "- approach it, view it from more than one angle, and re-check it if needed. Keep "
    "searching until you find the bug, then report it with flag. Flag the injected bug once; "
    "do not flag normal objects.")

_L2_TYPE = (
    " The injected bug is of type {cat}. Two examples of this bug type: {e1}; {e2}. "
    "No other bug type is present - focus on finding this type of bug.")

_L3_INSTR = (
    "You are QA-testing one small area of this palace atrium hall. Exactly ONE bug has been "
    "injected, and it is definitely present within about {r} meters of your starting "
    "position - you start close to it. Stay inside this inspection zone; do not wander "
    "beyond it. Inspect the area thoroughly: view suspicious spots from more than one angle, "
    "walk through the space, and re-check spots you have already seen. Keep searching until "
    "you find the bug, then report it with flag. Flag the injected bug once; do not flag "
    "normal objects.")

for _sp, _cfg in _SP_CFG.items():
    _cat, _e1, _e2 = _LADDER_CATS[_CASE_CAT[_sp]]
    _type_sent = _L2_TYPE.format(cat=_cat, e1=_e1, e2=_e2)
    _r = LADDER_NEAR[_cfg]["r"]
    TASKS[f"audit_{_sp}_l1"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=25,
                                    instr=_L1_INSTR)
    TASKS[f"audit_{_sp}_l2"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=25,
                                    instr=_L1_INSTR + _type_sent)
    TASKS[f"audit_{_sp}_l3"] = dict(config=f"{_cfg}-near", kind="audit", zone="zone_far",
                                    steps=25, instr=_L3_INSTR.format(r=_r) + _type_sent,
                                    inspect_r=_r)


# -- HS S1 difficulty ladder (2026-09-07): same three cumulative priors as the SP ladder above,
# 90-step budget like HS L0. Near spawns = the verified S3 viewpoints (agent/vla/house_routes.py),
# facing the carrier; r is the soft inspection radius (8 m for the leave-and-return state cases,
# whose triggers need > 7 m from the object). scripts/tools/gen_house_cases.py emits the -near configs.
HS_LADDER_NEAR = {
    "hs01-float":       dict(spawn=(5.0, 4.3),   bug=(5.11, 2.91),  r=5),
    "hs02-clip":        dict(spawn=(3.6, -0.3),  bug=(5.1, -1.75),  r=5),
    "hs03-scale":       dict(spawn=(2.6, -2.2),  bug=(4.0, -3.6),   r=5, y=3.0),   # v2: kids-room desk chair upstairs
    "hs04-doublespawn": dict(spawn=(-5.0, 3.9),  bug=(-6.1, 2.6),   r=5),
    "hs05-airwall":     dict(spawn=(0.6, 2.2),   bug=(0.6, 0.9),    r=5),
    "hs06-hole":        dict(spawn=(0.6, 1.0),   bug=(0.6, -1.9),   r=5),
    "hs07-ghostisland": dict(spawn=(4.4, -3.65), bug=(4.4, -2.6),   r=5),
    "hs08-jitter":      dict(spawn=(-4.6, 0.3),  bug=(-6.45, -0.75), r=5),
    "hs09-magenta":     dict(spawn=(-3.2, 1.5),  bug=(-3.2, -0.86), r=5),
    "hs10-backcull":    dict(spawn=(-3.2, 4.3),  bug=(-3.2, 2.35),  r=5),
    "hs11-xray":        dict(spawn=(0.6, -0.5),  bug=(-3.25, -0.05), r=6, y=3.0),  # v2: master bed upstairs, seen from the landing
    "hs12-unload":      dict(spawn=(-4.4, 4.0),  bug=(-6.35, 4.4),  r=8),
    "hs13-statereset":  dict(spawn=(2.7, 1.5),   bug=(5.11, 1.49),  r=8),
    "hs14-lodpop":      dict(spawn=(0.4, 1.4),   bug=(4.4, -0.04),  r=6, y=3.0),   # v2: upstairs lounge sofa, from the landing
    "hs15-spawnpile":   dict(spawn=(2.4, -1.2),  bug=(2.9, -3.3),   r=5, y=3.0),   # v2: kids room upstairs
}
_HS_CASE_CAT = {f"hs{k[2:]}": v for k, v in _CASE_CAT.items()}   # hsXX mirrors spXX type by type

_HS_L1_INSTR = (
    "You are QA-testing this two-storey family house. Exactly ONE bug has been injected into it, "
    "and it is definitely present. Patrol the house: walk through every room on the ground floor "
    "and, via the stairs in the hall, every room upstairs; look around along the way and inspect "
    "anything that seems off - approach it, view it from more than one angle, and re-check it if "
    "needed. Keep searching until you find the bug, then report it with flag. Flag the injected "
    "bug once; do not flag normal objects.")

_HS_L3_INSTR = (
    "You are QA-testing one small area of this family house. Exactly ONE bug has been injected, "
    "and it is definitely present within about {r} meters of your starting position - you start "
    "close to it. Stay inside this inspection zone; do not wander beyond it. Inspect the area "
    "thoroughly: view suspicious spots from more than one angle, walk through the space, and "
    "re-check spots you have already seen. Keep searching until you find the bug, then report it "
    "with flag. Flag the injected bug once; do not flag normal objects.")

for _hs, _cfg in _HS_CFG.items():
    _cat, _e1, _e2 = _LADDER_CATS[_HS_CASE_CAT[_hs]]
    _type_sent = _L2_TYPE.format(cat=_cat, e1=_e1, e2=_e2)
    _r = HS_LADDER_NEAR[_cfg]["r"]
    TASKS[f"audit_{_hs}_l1"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=90, instr=_HS_L1_INSTR)
    TASKS[f"audit_{_hs}_l2"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=90,
                                    instr=_HS_L1_INSTR + _type_sent)
    TASKS[f"audit_{_hs}_l3"] = dict(config=f"{_cfg}-near", kind="audit", zone="zone_far", steps=90,
                                    instr=_HS_L3_INSTR.format(r=_r) + _type_sent, inspect_r=_r)


# -- WT suite (reef dive, standalone page with the __env contract; scripts/tools/gen_water_cases.py) --
_WT_INSTR = (
    "You are QA-testing this shallow reef dive scene as a scuba diver. Explore the whole reef: swim "
    "along the sandy lanes, around the rock ridge to the north-east, through the coral clusters and "
    "kelp stands, and past the rocks to the west and south. Look around along the way and inspect "
    "anything that seems off - approach it, view it from more than one angle, and re-check it if "
    "needed. Report every bug you find with flag; if the reef is normal, finish with done without "
    "flagging.")
_WT_CFG = {
    "wt01": "wt01-float", "wt02": "wt02-clip",   # wt03 / wt04 / wt06 / wt10 / wt13 retired 2026-09-14..16
    "wt05": "wt05-airwall", "wt07": "wt07-ghostrock", "wt08": "wt08-jitter",
    "wt09": "wt09-magenta", "wt11": "wt11-xray", "wt12": "wt12-unload",
    "wt14": "wt14-lodpop", "wt15": "wt15-spawnpile",
    "wt16": "wt16-fishreverse", "wt17": "wt17-fishupside",
}
for _wt, _cfg in _WT_CFG.items():
    TASKS[f"audit_{_wt}_bug"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=90, instr=_WT_INSTR)
TASKS["audit_wt00_clean"] = dict(config="wt00-clean", kind="audit", zone="zone_far", steps=90, instr=_WT_INSTR)

# ---- AF suite: Sketchbook airfield (standalone page + shared harness contract), 90-step budget
_AF_INSTR = (
    "You are QA-testing this airfield scene on foot. Explore the whole central strip: walk north past the "
    "row of concrete barriers and along the tarmac, check the barrels, crates, carts, generators and street "
    "lamps beside the strip, then walk south past the other barrier row. Look around along the way and "
    "inspect anything that seems off - approach it, view it from more than one angle, and re-check it if "
    "needed. Report every bug you find with flag; if the scene is normal, finish with done without flagging.")
_AF_CFG = {
    "af01": "af01-float", "af02": "af02-clip", "af03": "af03-scale", "af04": "af04-doublespawn",
    "af05": "af05-airwall", "af06": "af06-hole", "af07": "af07-ghost", "af08": "af08-jitter",
    "af09": "af09-magenta", "af10": "af10-backcull", "af11": "af11-xray", "af12": "af12-unload",
    "af13": "af13-statereset", "af14": "af14-lodpop", "af15": "af15-spawnpile",
    "af16": "af16-misrotated", "af17": "af17-noshadow", "af18": "af18-pushcar",   # af18 (2026-09-12): the pushable parked car
}
for _af, _cfg in _AF_CFG.items():
    TASKS[f"audit_{_af}_bug"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=90, instr=_AF_INSTR)
TASKS["audit_af00_clean"] = dict(config="af00-clean", kind="audit", zone="zone_far", steps=90, instr=_AF_INSTR)

# ---- WL suite: Beyond Fable wilderness (standalone page + shared harness contract, world seed fixed), 90 steps
_WL_INSTR = (
    "You are QA-testing this wilderness scene on foot. Explore the meadow around the start: the big boulder next "
    "to the start, the tall pine to the west, the bushes to the north, the boulder on the slope to the north-east "
    "and the big tree to the north-west, then the grass and hillsides beyond. Look around along the way and "
    "inspect anything that seems off - approach it, view it from more than one angle, and re-check it if "
    "needed. Report every bug you find with flag; if the scene is normal, finish with done without flagging.")
_WL_CFG = {
    "wl01": "wl01-float", "wl02": "wl02-clip", "wl03": "wl03-scale",   # wl04 retired 2026-09-16
    "wl05": "wl05-airwall", "wl06": "wl06-hole", "wl07": "wl07-ghost", "wl08": "wl08-jitter",
    "wl09": "wl09-magenta", "wl10": "wl10-backcull", "wl11": "wl11-xray", "wl12": "wl12-unload",
    "wl14": "wl14-lodpop", "wl15": "wl15-spawnpile",   # wl13 retired 2026-09-16
    "wl16": "wl16-terrainhole", "wl17": "wl17-upsidedown",   # 2026-09-12: replaced the invisible seam / floating grass
}
for _wl, _cfg in _WL_CFG.items():
    TASKS[f"audit_{_wl}_bug"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=90, instr=_WL_INSTR)
TASKS["audit_wl00_clean"] = dict(config="wl00-clean", kind="audit", zone="zone_far", steps=90, instr=_WL_INSTR)

# ---- CT suite: Mistwood Cottage (standalone page + shared harness contract), 90 steps
_CT_INSTR = (
    "You are QA-testing this cottage scene on foot. Explore the whole garden: walk up the front path to the "
    "cottage door, look at the big tree and the rocks beside the path, go round the cottage to the tree behind "
    "it, then follow the west path and the steps up to the stone well. Look around along the way and inspect "
    "anything that seems off - approach it, view it from more than one angle, and re-check it if needed. "
    "Report every bug you find with flag; if the scene is normal, finish with done without flagging.")
_CT_CFG = {
    "ct01": "ct01-float", "ct02": "ct02-clip", "ct03": "ct03-scale", "ct04": "ct04-doublespawn",
    "ct05": "ct05-airwall", "ct06": "ct06-hole", "ct07": "ct07-ghost", "ct08": "ct08-jitter",
    "ct09": "ct09-magenta", "ct10": "ct10-backcull", "ct11": "ct11-xray", "ct12": "ct12-unload",
    "ct13": "ct13-statereset", "ct14": "ct14-lodpop", "ct15": "ct15-spawnpile",
    "ct17": "ct17-timejump",   # ct16 retired 2026-09-16
}
for _ct, _cfg in _CT_CFG.items():
    TASKS[f"audit_{_ct}_bug"] = dict(config=_cfg, kind="audit", zone="zone_far", steps=90, instr=_CT_INSTR)
TASKS["audit_ct00_clean"] = dict(config="ct00-clean", kind="audit", zone="zone_far", steps=90, instr=_CT_INSTR)
