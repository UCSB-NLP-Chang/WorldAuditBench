"""Canonical TC scorer: LLM-as-judge "did the tester find the bug".

The single scored metric (project decision, 2026-08-29): a planted bug counts as FOUND iff at
least one emitted flag's description is judged (by an LLM judge, temperature 0) to describe the
planted defect. Flag position is NOT scored - it is reported only as an auxiliary localization
diagnostic. Any flag in a clean episode is a false positive.

Usage: python -m judge.judge_sem runs/tc-<model> [runs/tc-<model2> ...] [--out reports/...]
- ALL flags in bug episodes are judged (no radius gating); identical (case, note) pairs are
  deduplicated and cached in runs/judge_cache.json (idempotent, resumable)
- Outputs: per model x case found/FP matrix, totals, judge-based P/R/F1, auxiliary loc-err
"""
import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from judge.score_flags import resolve_answers
from agent.vla.vlm import VLMClient

GT = {
    "tc01": "The wooden door closes again BY ITSELF about 2 seconds after being opened (auto-closes without anyone touching it).",
    "tc02": "The wooden door has NO opening animation - it snaps instantly to fully open when used, instead of swinging open smoothly.",
    "tc03": "The wooden door's opening animation stops HALFWAY - the door is stuck half-open and still blocks passage.",
    "tc04": "A wooden crate slides back and forth ON ITS OWN, without anyone touching it.",
    "tc05": "The player can slip INSIDE the stone pillar through one of its faces and then is permanently stuck inside the solid geometry.",
    "tc06": "A chest behind a CLOSED iron gate can be opened by interacting THROUGH the closed gate - the interaction ignores the solid barrier.",
    "tc07": "The whole screen is covered by an abnormal red/pink COLOR TINT (corrupted color grading).",
    "tc08": "An iron portcullis gate stands in the middle of the open walkway, unattached to any wall - an OUT-OF-PLACE asset that does not belong in this scene.",
    "tc09": "A wooden crate is partially SUNK/EMBEDDED into the floor (its lower half is below ground level).",
    "tc10": "An INVISIBLE obstacle blocks movement in the corridor - something solid is there but nothing is visible at that spot.",
    "torch": "One of the two torch flames is FROZEN/STATIC - it does not flicker or animate over time (while the other torch animates normally).",
    # SP suite (Sponza-native mutations; taxonomy v2)
    "sp01": "A potted plant FLOATS in mid-air about half a meter above the floor (its identical sibling pots sit on the ground).",
    "sp02": 'One potted plant lies TIPPED OVER (about 65 degrees) and HALF SUNK/CLIPPED into the floor - the lower half of the pot, part of its rim and part of the plant are below floor level, the other half sticks out at an angle, while its identical siblings stand upright.',
    "sp03": 'One potted plant is abnormally OVERSIZED - nearly three times the size of its identical sibling pots, chest-high and over a metre wide.',
    "sp04": "The same potted plant is SPAWNED TWICE almost exactly on top of itself - a co-located duplicate: doubled/overlapping surfaces, doubled rim/base edges, abnormally dense foliage on that one pot.",
    "sp05": "An INVISIBLE barrier blocks the hall midway - movement is stopped where nothing visible is in the way.",
    "sp06": "A solid-looking floor area has no collision: walking onto it makes the player fall through / drop below the floor. From the player's point of view this manifests as suddenly being RESET/TELEPORTED BACK TO THE START when crossing that area.",
    "sp07": "One hanging DRAPE/CURTAIN (may be called a banner) has NO COLLISION - the player can walk straight through it (into the side aisle), while every other drape is a solid barrier that stops the player. (Reports about some object FLOATING or lacking support are a DIFFERENT defect, not this one.)",
    "sp08": "A potted plant TREMBLES/VIBRATES rapidly in place on its own (physics-solver jitter) - constant small shaking, not smooth movement.",
    "sp09": "One stone floor POT (potted plant) has a MISSING TEXTURE - it renders as abnormal flat solid magenta/pink (a placeholder colour, broken texture).",
    "sp10": "A hanging DRAPE/CURTAIN (may be called a banner) looks normal from the main hall but is INVISIBLE/missing when viewed from BEHIND (from the side aisle), while the neighboring drapes remain visible from behind - a viewpoint-dependent rendering (backface-culling-style) defect on that one drape.",
    "sp11": "A potted plant RENDERS ON TOP of everything - it stays visible through columns/objects that should occlude it.",
    "sp12": "A potted plant that was present DISAPPEARS after the player walks away from the area, and is still gone on returning (object unloaded and never respawned - a streaming/persistence bug).",
    "sp13": "After the player leaves the area and returns, a potted plant is AT A DIFFERENT POSITION than before (its state/position was not saved - resets/relocates on each revisit).",
    "sp14": "A drape/curtain (may be called a banner) shows a TEXTURE-LOD/streaming POP: from afar its texture is an abnormal blocky ultra-low-resolution version, and it abruptly pops to sharp when approached (or blurry when walking away).",
    "sp15": 'A PILE / HEAP of duplicated props (copies of the stone pots, a planter and a hanging brazier) jammed INTO EACH OTHER in the corner of a side aisle (north-east corner, behind the last drape) - pots tilted through one another, one lying on its side, a brazier on the floor (failed spawns).',
    # HS suite (Family House mutations, 2026-09-06; type-for-type mirror of SP)
    "hs01": "A dining chair FLOATS in mid-air about half a meter above the floor (its identical sibling chairs stand on the floor).",
    "hs02": 'A kitchen bar stool is TIPPED OVER (about 35 degrees) and SUNK/CLIPPED into the floor - its legs are under the floor and only the tilted seat shows above it, while the stools next to it stand upright.',
    "hs03": "One chair upstairs (the desk chair in the kids room) is abnormally OVERSIZED - much bigger than a normal chair, taller than the desk it stands at.",
    "hs04": "The same armchair is SPAWNED TWICE almost exactly on top of itself - a co-located duplicate: doubled/overlapping surfaces, flickering/z-fighting shell on that one armchair.",
    "hs05": "An INVISIBLE barrier blocks the entrance hall - movement is stopped where nothing visible is in the way.",
    "hs06": "A solid-looking floor area in the hall has no collision: walking onto it makes the player fall through / drop below the floor. From the player's point of view this manifests as suddenly being RESET/TELEPORTED BACK TO THE START when crossing that area.",
    "hs07": "The kitchen island/counter has NO COLLISION - the player can walk straight through it, while every other piece of furniture is solid. (Reports about some object FLOATING or lacking support are a DIFFERENT defect, not this one.)",
    "hs08": "A floor lamp TREMBLES/VIBRATES rapidly in place on its own (physics-solver jitter) - constant small shaking, not smooth movement.",
    "hs09": "The TV cabinet/console has a MISSING TEXTURE - it renders as abnormal flat solid magenta/pink (placeholder color, broken texture).",
    "hs10": "The living-room SOFA looks normal from the front (TV side) but is INVISIBLE/missing when viewed from BEHIND (window side) - a viewpoint-dependent rendering (backface-culling-style) defect on that sofa.",
    "hs11": "The master BED upstairs RENDERS ON TOP of everything - it stays visible through the bedroom walls / furniture that should occlude it (seen from the landing or other rooms).",
    "hs12": "A potted plant that was present in the living room DISAPPEARS after the player walks away, and is still gone on returning (object unloaded and never respawned - a streaming/persistence bug).",
    "hs13": "After the player leaves the dining room and returns, a dining chair is AT A DIFFERENT POSITION than before (its state/position was not saved - resets/relocates on each revisit).",
    "hs14": "The sofa in the upstairs lounge shows a geometry LOD POP: from more than a few metres away it is drawn as a crude flat grey BOX (a blocky placeholder) and abruptly pops into the real sofa when approached (or back to the box when walking away).",
    "hs15": "A PILE of duplicated furniture (copies of a dining chair, a bar stool, a nightstand and an armchair) sits jammed INTO EACH OTHER in a corner of the kids room upstairs - interpenetrating/overlapping objects where nothing should stand (failed spawns).",
    "wt01": 'A BOULDER FLOATS in mid-water about 1.6 m above the sand with open water underneath it (the other rocks rest on the seabed).',
    "wt02": "A school of barramundi fish swims HALF-BURIED IN THE SAND of the open lane just north of the start - the fish bodies clip through the seabed, only backs and fins show above the sand (fish inside/through the ground).",
    "wt03": 'One of the three big barramundi is GIANT - about six times the size of its two identical companions, a fish nearly six metres long (abnormally oversized fish).',
    "wt04": 'The big mossy rock set west of the start is spawned TWICE - a second identical copy of the rock set sits shifted and turned into the first, the same rock shapes interpenetrating / passing through each other.',
    "wt05": 'An INVISIBLE WALL / barrier right across the sandy lane a few metres north of the start blocks the diver although nothing is visible there.',
    "wt06": 'The diver FALLS/SINKS THROUGH the solid-looking sand in one spot (a hole in the seabed) and drops into darkness, then respawns.',
    "wt07": "The tall boulder north-east of the start has NO COLLISION - the diver swims straight through it while every other rock is solid.",
    "wt08": 'A staghorn coral SHAKES/VIBRATES rapidly in place (physics jitter) instead of swaying gently.',
    "wt09": 'A big rock face renders as flat bright MAGENTA/PINK (missing texture placeholder).',
    "wt10": 'The big boulder east of the reef centre is visible from the south (start side) but DISAPPEARS / is invisible when viewed from its north side.',
    "wt11": "The school of small SILVER FISH around the big rock north-east of the reef RENDERS THROUGH the rock and corals - the fish stay visible through objects that should hide them (x-ray / no depth test).",
    "wt12": 'After you visit the big mossy rock set west of the start (with its corals) and swim away, the whole rock set and its corals are UNLOADED and GONE when you come back (an empty patch of sand where the rocks stood).',
    "wt13": 'The boulder beside the start lane CHANGES SIDES / POSITION each time you leave the start and come back - it moves about 8 m across the lane (state reset).',
    "wt14": 'A coral cluster shows as crude blocky BLOBS from a few metres away and POPS into detailed corals only when very close (LOD pop).',
    "wt15": 'A PILE of nine IDENTICAL copies of the same staghorn coral, all facing the same way, stacked into one another in one heap on the open sand (failed spawns / duplicated objects).',
    "wt16": 'The three big barramundi swim BACKWARDS / TAIL-FIRST - they move in the direction of their tails, heads pointing away from where they go.',
    "wt17": 'A school of barramundi by the eastern ridge swims UPSIDE DOWN / belly-up (rolled 180 degrees).',
    "af01": 'One of the three barrels east of the start FLOATS about 1.5 m above the tarmac with open air under it.',
    "af02": 'The tool cart by the generator is TIPPED OVER (about 45 degrees) and SUNK/CLIPPED into the tarmac - its lower half, wheels included, is under the ground and the tarmac cuts through its body.',
    "af03": "The fire hydrant north-east of the start is abnormally OVERSIZED - about three times its normal size, a hydrant taller than a person.",
    "af04": "The military crate north-east of the start is DOUBLE-SPAWNED: two copies almost on top of each other, a slightly offset duplicate interpenetrating it, faces flicker / z-fight.",
    "af05": 'An INVISIBLE WALL right across the tarmac north of the north barrier row blocks the walker although nothing is visible there.',
    "af06": 'A HOLE in the ground: the walker falls through the solid-looking tarmac at one spot about 20 m south of the start (centre line of the strip) and respawns.',
    "af07": 'One concrete road barrier in the north row has NO COLLISION - the walker passes straight through it.',
    "af08": 'The street lamp east of the barrier row JITTERS / vibrates rapidly in place.',
    "af09": 'The wooden crate in the north-east cluster renders flat bright MAGENTA (missing texture).',
    "af10": 'A road barrier in the north row is visible from the south but INVISIBLE from its north side (back-face culling).',
    "af11": 'The red car parked by the stone gate renders THROUGH other objects in front of it - visible through the gate pillars, barriers and crates (x-ray / no depth test).',
    "af12": 'The crate cluster north-east of the start UNLOADS / disappears after being visited and left.',
    "af13": 'A barrel east of the start is at a DIFFERENT POSITION each time the walker comes back (state reset / jump of ~3 m).',
    "af14": 'The generator / tool cart / jerrycan group shows as crude grey BLOCKS from a few metres away and POPS into detailed props up close (LOD pop).',
    "af15": 'Nine barrels, crates and jerrycans are PILED on top of each other in one solid heap on the open tarmac south-east of the start (failed spawns).',
    "af16": "One concrete road barrier in the north row is UPSIDE DOWN - flipped over, resting on its top, while the others stand normally.",
    "af17": 'The street lamp east of the start casts NO SHADOW at all while the matching west lamp and every other prop cast shadows.',
    "wl01": "The big boulder right next to the start FLOATS about 3 m above the meadow with open air under it.",
    "wl02": 'The tall pine west of the start is TIPPED OVER (about 35 degrees) and SUNK into the ground - its trunk goes into the meadow and its lower branches stab through the grass (clipping into the terrain).',
    "wl03": "One square patch of the meadow south-west of the start has its GRASS rendered at about four times normal SCALE - blades taller than a person, the patch ending abruptly along straight edges (wrong-scale grass).",
    "wl04": 'The big boulder next to the start is DOUBLE-SPAWNED: a second identical copy of the boulder sits shifted and turned into the first, the two rock shapes passing through each other.',
    "wl05": 'An INVISIBLE WALL across the meadow north of the start blocks the walker although nothing is visible there.',
    "wl06": 'A HOLE in the ground: the walker falls through the solid-looking meadow north-east of the start and respawns.',
    "wl07": 'The big boulder next to the start has NO COLLISION - the walker passes straight through it.',
    "wl08": 'A bush north-east of the start JITTERS / vibrates rapidly in place.',
    "wl09": "The boulder on the slope north-east of the start renders flat bright MAGENTA (missing texture placeholder).",
    "wl10": 'The boulder on the north-east slope is visible from the south but INVISIBLE from its north side (back-face culling).',
    "wl11": 'The boulder on the north-east slope renders THROUGH trees, bushes and the hillside in front of it (x-ray / no depth test).',
    "wl12": 'The big boulder right next to the start UNLOADS / disappears once you have walked away from it - gone when you come back.',
    "wl13": 'The tall pine west of the start is at a DIFFERENT POSITION each time the walker comes back after walking away (state reset / jump of ~10 m).',
    "wl14": 'The tall pine west of the start shows as a crude flat-shaded CONE from more than ~15 m away and POPS into a detailed tree up close (LOD pop).',
    "wl15": 'Nine identical small boulders are JAMMED into one another in one tight heap on the open grass south-west of the start, near the water (failed spawns).',
    "wl16": "A square patch of the ground east of the start is MISSING - a hole in the terrain mesh showing the void / the distant hills through it, yet the walker can still cross the gap on invisible ground (missing terrain geometry).",
    "wl17": "The big tree north-west of the start is UPSIDE DOWN - its round crown rests on the ground and its bare trunk points straight up into the sky.",
    "ct01": 'The big tree east of the front door FLOATS more than a metre above the ground - its roots hang in the air.',
    "ct02": 'The stone picnic table in the west garden is TIPPED OVER (about 40 degrees) and SUNK/CLIPPED into the lawn - one half of the table is under the grass, the other half sticks up in the air.',
    "ct03": "One of the two identical garden benches in the west garden is abnormally OVERSIZED - more than twice the size of the other bench and the table.",
    "ct04": 'The garden bench east of the picnic table is DOUBLE-SPAWNED: a second identical bench sits shifted and turned into the first one, seat boards and legs passing through each other.',
    "ct05": 'An INVISIBLE WALL across the front path, between the gate and the door, blocks the walker although nothing is visible there.',
    "ct06": "A HOLE in the path: the walker falls through the solid-looking flagstones of the front path, drops below the garden and respawns at the start.",
    "ct07": "The big tree east of the front door has NO COLLISION - the walker passes straight through its trunk while everything else is solid.",
    "ct08": "The small lantern post west of the path (by the pond bank) JITTERS / trembles in place on its own.",
    "ct09": "The stone well on the hill to the west renders flat bright MAGENTA (missing texture placeholder).",
    "ct10": 'The tree behind the cottage is visible from the south but INVISIBLE from its north side (back-face culling).',
    "ct11": 'The picture frames inside the cottage show THROUGH the front wall - visible from outside, floating on the facade (x-ray / no depth test).',
    "ct12": "The tree behind the cottage UNLOADS / disappears after being visited and left.",
    "ct13": "The tall lamp post standing in the pond west of the path is at a DIFFERENT POSITION each time the walker comes back (state reset / jump of ~2.5 m).",
    "ct14": 'The big tree east of the front door shows as a crude green CONE from a few metres away and POPS into a detailed tree up close (LOD pop).',
    "ct15": "Nine small stone tables are PILED on top of each other in one heap on the lawn east of the front path (failed spawns / duplicated objects).",
    "ct16": 'The cottage FRONT DOOR is MISSING - the doorway is an empty opening showing the room inside (no door, no handle), yet an invisible barrier still blocks the doorway so the walker cannot step in (missing door / phantom collision).',
    "ct17": 'The TIME OF DAY FLICKERS - the whole scene cuts back and forth between full daylight and night about once a second, instant cuts instead of the normal slow cross-fading cycle.',
    "af18": "The parked red car by the stone gate south of the start MOVES when the walker bumps into it - it rolls / slides away, a parked vehicle that a person can push around (every other vehicle stays put).",

}

# human-readable case labels: reports must never show a bare case id
LABELS = {
    "tc01": "auto-closing door", "tc02": "instant-open door", "tc03": "half-stuck door",
    "tc04": "drifting crate", "tc05": "wall trap", "tc06": "interact-through-gate",
    "tc07": "screen tint", "tc08": "out-of-place gate", "tc09": "sunken crate",
    "tc10": "invisible obstacle", "torch": "frozen flame",
    "sp01": "floating pot", "sp02": "pot clipped into floor", "sp03": "oversized pot",
    "sp04": "double-spawned pot (z-fight/doubling)", "sp05": "invisible wall", "sp06": "fall-through floor",
    "sp07": "no-collision drape", "sp08": "trembling pot (physics jitter)", "sp09": "missing-texture drape",
    "sp10": "drape invisible from behind", "sp11": "x-ray pot (renders through occluders)",
    "sp12": "pot unloaded after leaving the area", "sp13": "pot position resets on revisit",
    "sp14": "texture LOD pop drape", "sp15": "prop pile at world origin",
    "sp00": "clean hall (no bug)",
    "hs01": "floating dining chair", "hs02": "bar stool clipped into floor", "hs03": "oversized dining chair",
    "hs04": "double-spawned armchair (z-fight/doubling)", "hs05": "invisible wall (hall)", "hs06": "fall-through hall floor",
    "hs07": "no-collision kitchen island", "hs08": "trembling floor lamp (physics jitter)", "hs09": "missing-texture TV cabinet",
    "hs10": "sofa invisible from behind", "hs11": "x-ray coffee table (renders through occluders)",
    "hs12": "plant unloaded after leaving the area", "hs13": "dining chair position resets on revisit",
    "hs14": "texture LOD pop rug", "hs15": "furniture pile in the hall",
    "hs00": "clean house (no bug)",
    "wt00": 'clean reef (no bug)',
    "wt01": 'floating boulder',
    "wt02": "fish clipping into the seabed",
    "wt03": "giant fish",
    "wt04": 'double-spawned rock',
    "wt05": 'invisible wall (lane)',
    "wt06": 'hole in the seabed',
    "wt07": "no-collision tall rock",
    "wt08": 'trembling coral',
    "wt09": 'magenta rock face',
    "wt10": 'rock invisible from behind',
    "wt11": "x-ray silver fish",
    "wt12": 'rock set unloads',
    "wt13": 'lane boulder jumps across the lane',
    "wt14": 'coral LOD pop',
    "wt15": 'coral pile',
    "wt16": 'fish swim backwards',
    "wt17": 'fish swim upside down',
    "af00": 'clean airfield (no bug)',
    "af01": 'floating barrel',
    "af02": "tilted sunken tool cart",
    "af03": "giant fire hydrant",
    "af04": 'double-spawned crate',
    "af05": 'invisible wall',
    "af06": 'hole in the ground',
    "af07": 'no-collision barrier',
    "af08": 'trembling street lamp',
    "af09": 'missing-texture crate',
    "af10": 'barrier invisible from behind',
    "af11": 'x-ray car',
    "af12": 'unloaded crate cluster',
    "af13": 'barrel position resets',
    "af14": 'prop LOD pop',
    "af15": 'prop pile',
    "af16": "upside-down barrier",
    "af17": 'street lamp casts no shadow',
    "wl00": 'clean wilderness (no bug)',
    "wl01": 'floating boulder',
    "wl02": 'sunken pine',
    "wl03": "giant grass patch",
    "wl04": 'double-spawned boulder',
    "wl05": 'invisible wall',
    "wl06": 'hole in the ground',
    "wl07": 'no-collision boulder',
    "wl08": 'trembling shrub',
    "wl09": 'missing-texture boulder',
    "wl10": 'boulder invisible from behind',
    "wl11": 'x-ray boulder',
    "wl12": 'unloaded boulder',
    "wl13": 'tree position resets',
    "wl14": 'tree LOD pop',
    "wl15": 'boulder heap',
    "wl16": "missing terrain patch",
    "wl17": "upside-down tree",
    "ct00": 'clean cottage (no bug)',
    "ct01": 'floating tree',
    "ct02": "tilted sunken picnic table",
    "ct03": "giant garden bench",
    "ct04": 'double-spawned bench',
    "ct05": 'invisible wall',
    "ct06": 'hole in the path',
    "ct07": 'no-collision fence',
    "ct08": "trembling lantern post",
    "ct09": "missing-texture well",
    "ct10": 'tree invisible from behind',
    "ct11": 'x-ray picture frames',
    "ct12": 'unloaded tree',
    "ct13": "lamp post position resets",
    "ct14": 'tree LOD pop',
    "ct15": "table pile",
    "ct16": "missing front door",
    "ct17": "time of day flickers",
    "sp02": 'pot tipped into the floor',
    "sp09": "missing-texture pot",
    "sp15": "prop pile in the aisle corner",
    "hs03": "oversized kids-room chair (upstairs)",
    "hs11": "x-ray bed (renders through walls)",
    "hs14": "LOD pop sofa (upstairs)",
    "hs15": "furniture pile in the kids room",
    "af18": "pushable parked car",

}

JUDGE_PROMPT = """You are grading a game QA tester's bug report against the ground-truth bug that was planted.

GROUND-TRUTH BUG: {gt}

TESTER'S REPORT: "{note}"

Question: does the tester's report describe THIS same defect/phenomenon (allowing different wording and minor detail differences)? To count as a match the report must describe the same TYPE of defect happening to the same KIND of object/place as the ground truth. A report about a DIFFERENT phenomenon or a DIFFERENT object (e.g. reporting "an invisible wall" when the actual bug is a crate sunk into the floor; calling a floating object "a collision problem"; or reporting some other object elsewhere in the scene) counts as NOT a match.

First state in ONE sentence what object and defect the report describes vs what the ground truth describes, then give the verdict.
Answer format: one line of reasoning, then on the final line exactly one JSON object: {{"match": true}} or {{"match": false}}"""


def load_adjudications():
    """Manual adjudication overlay: every judge-MATCHED positive is human-audited; documented
    overrides (with written reasons) live in judge/adjudications.json and take precedence."""
    p = Path(__file__).resolve().parent / "adjudications.json"
    if not p.exists():
        return {}
    return {k: v["verdict"] for k, v in json.loads(p.read_text()).items()}


def collect(run_bases):
    cache_ans = {}
    items = []
    for base in run_bases:
        for md in sorted(Path(base).glob("*/meta.json")):
            meta = json.loads(md.read_text())
            if meta.get("kind") != "audit":
                continue
            task = meta["task"]
            case, variant = task.split("_")[1], task.split("_")[2]
            flags = meta.get("flags", [])
            ans = None
            if variant == "bug":
                cfg = meta["config"]
                if cfg not in cache_ans:
                    cache_ans[cfg] = resolve_answers(cfg)
                ans = cache_ans[cfg][0] if cache_ans[cfg] else None
            items.append(dict(dir=md.parent.name,
                              model=meta.get("model", "?").split("/")[-1],
                              case=case, variant=variant, flags=flags, answer=ans))
    return items


def aux_loc_err(answer, flag):
    """Auxiliary only: extent-aware horizontal distance from flag to the bug region."""
    if not answer or answer.get("global"):
        return None
    ex, ez = answer.get("extent_x", 0), answer.get("extent_z", 0)
    dx = max(abs(flag["pos"][0] - answer["position"][0]) - ex, 0)
    dz = max(abs(flag["pos"][2] - answer["position"][2]) - ez, 0)
    return round(math.hypot(dx, dz), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_bases", nargs="+")
    ap.add_argument("--out", default="reports/tc-night-0827/judge-matrix.md")
    ap.add_argument("--cache", default="runs/judge_cache_v3.json")   # v3: reasoned verdict (one-sentence rationale before match)
    args = ap.parse_args()

    items = collect(args.run_bases)
    cache_p = Path(args.cache)
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}

    todo = {}
    for it in items:
        # everything except clean controls carries a planted defect (bug / l1 / l2 / l3)
        if it["variant"] == "clean":
            continue
        for f in it["flags"]:
            note = f.get("note", "").strip()
            key = f"{it['case']}||{note.lower()}"
            if key not in cache:
                todo[key] = (it["case"], note)
    print(f"{len(todo)} deduplicated candidate notes to judge ({len(cache)} cached)")

    if todo:
        client = VLMClient(base_url="http://localhost:8010/v1",
                           model="Qwen/Qwen3-VL-30B-A3B-Instruct", temperature=0.0, max_tokens=160)
        for n, (key, (case, note)) in enumerate(todo.items(), 1):
            r = client.chat([{"role": "user", "content": JUDGE_PROMPT.format(gt=GT[case], note=note)}])
            m = re.search(r'"match"\s*:\s*(true|false)', r["text"], re.I)
            cache[key] = (m.group(1).lower() == "true") if m else False
            if n % 25 == 0:
                print(f"  judged {n}/{len(todo)}")
                cache_p.write_text(json.dumps(cache))
        cache_p.write_text(json.dumps(cache))

    # per model x case: found (judge) / clean FP; totals; P/R/F1; aux loc-err
    adjud = load_adjudications()
    verdict = lambda key: adjud.get(key, cache.get(key, False))
    per = defaultdict(lambda: dict(nb=0, found=0, nc=0, fp=0, locs=[]))
    prf = defaultdict(lambda: [0, 0, 0])   # model -> [TP, FP, FN]
    for it in items:
        m = it["model"]
        k = (m, it["case"])
        if it["variant"] == "clean":
            per[k]["nc"] += 1
            per[k]["fp"] += len(it["flags"]) > 0
            prf[m][1] += len(it["flags"])
            continue
        per[k]["nb"] += 1
        hit = False
        for f in it["flags"]:
            note = f.get("note", "").strip()
            if verdict(f"{it['case']}||{note.lower()}"):
                hit = True
                d = aux_loc_err(it["answer"], f)
                if d is not None:
                    per[k]["locs"].append(d)
        per[k]["found"] += hit
        tp = 1 if hit else 0
        prf[m][0] += tp
        prf[m][1] += len(it["flags"]) - tp
        prf[m][2] += 1 - tp

    models = sorted({m for m, _ in per})
    cases = sorted({c for _, c in per})
    lines = [f"# Canonical scoring - LLM-judge 'bug found?' (judge: Qwen3-VL-30B-A3B, temp 0)",
             "",
             "Found = >=1 flag whose description the judge matches to the planted defect (position not scored).",
             "FP = any flag in a clean episode. Aux loc-err = extent-aware distance of matching flags (diagnostic only).",
             "",
             "| case | " + " | ".join(models) + " |",
             "|---|" + "---|" * len(models)]
    for c in cases:
        row = [f"{c} {LABELS[c]}" if c in LABELS else c]
        for m in models:
            v = per.get((m, c))
            if not v:
                row.append("-")
                continue
            loc = f" loc {sum(v['locs'])/len(v['locs']):.1f}m" if v["locs"] else ""
            row.append(f"found {v['found']}/{v['nb']} FP {v['fp']}/{v['nc']}{loc}")
        lines.append("| " + " | ".join(row) + " |")

    lines.append("\n## Totals and P/R/F1 (found-based; at most 1 TP per instance; surplus and clean flags are FP)\n")
    lines.append("| model | found | clean FP eps | P | R | F1 | flags |")
    lines.append("|---|---|---|---|---|---|---|")
    for m in models:
        nb = sum(v["nb"] for (mm, _), v in per.items() if mm == m)
        found = sum(v["found"] for (mm, _), v in per.items() if mm == m)
        nc = sum(v["nc"] for (mm, _), v in per.items() if mm == m)
        fp_eps = sum(v["fp"] for (mm, _), v in per.items() if mm == m)
        tp, fp, fn = prf[m]
        p = tp / (tp + fp) if tp + fp else 0
        r = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * p * r / (p + r) if p + r else 0
        lines.append(f"| {m} | {found}/{nb} | {fp_eps}/{nc} | {p:.2f} | {r:.2f} | {f1:.2f} | {tp + fp} |")

    out = "\n".join(lines) + "\n"
    Path(args.out).write_text(out)
    print(out)


if __name__ == "__main__":
    main()
