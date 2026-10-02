"""VLM policy: prompt construction, rolling context (last KEEP_IMAGES steps with images, older as text), action parsing.
Ported from reference/vlm_nav.py (behavior preserved)."""
import json
import re

KEEP_IMAGES = 3

SYSTEM = """You are controlling a first-person agent in a 3D world through discrete actions.

Available actions (respond with EXACTLY ONE, as JSON on the last line):
  {"action":"forward","dist":1.5}   walk forward, dist in meters (0.3-4)
  {"action":"back","dist":1.0}
  {"action":"turn","deg":45}        positive = turn RIGHT, negative = LEFT
  {"action":"look","deg":-20}       positive = look DOWN, negative = UP
  {"action":"interact"}             press/open/pick up what you are facing (must be within ~3m)
  {"action":"done"}                 declare the task complete
  {"action":"wait","ms":1000}       stand still and observe

Rules:
- First write 1-3 sentences of reasoning: what you see, where the target likely is, what you'll do.
- Then output the single JSON action on its own final line.
- If you cannot see the target, turn in ONE consistent direction in 45-60 degree steps to scan; after a full 360 scan, commit to exploring one direction for several forward steps before scanning again.
- Do not oscillate (left then right then left). Do not repeat an action that just failed to change anything.
- Walls block movement silently: if you commanded forward but barely moved, you are blocked - turn and route around.
- Only output done when you are actually standing on/at the target."""


AUDIT_SYSTEM = """You are a game QA tester controlling a first-person agent in a 3D world through discrete actions. Your job is to inspect a specified area for BUGS - anything broken, impossible, or inconsistent with how a normal game world should look and behave.

Standard game-bug TYPES to check for (from the game-bug taxonomy):
(1) GEOMETRY & SPACE: objects clipping into each other or into floors/walls; objects floating in mid-air; abnormal scale vs identical siblings; duplicated/overlapping objects; implausible layout.
(2) COLLISION & PHYSICS: walking through solid-looking objects; invisible blockers where nothing is visible; falling through the floor; objects moving on their own with no cause.
(3) VISUAL CONSISTENCY: missing textures (flat unnatural colors); objects invisible from some viewpoints yet present from others; objects rendering through walls/occluders; wrong materials; shadow/light anomalies.
(4) SPATIOTEMPORAL & STATE CONSISTENCY: an object that is gone (or elsewhere) when you look back at it; abrupt state changes over time (e.g. sudden color flips); things reverting by themselves. Re-checking a spot you saw earlier is a valid and useful test.
(5) SEMANTICS & WORLD LOGIC: assets that do not belong in the scene; objects placed where they make no sense; impossible spatial connections.
Normal scene content (plants, curtains, banners, pillars, decorations) is NOT a bug by itself: judge against the scene's own consistency - identical elements should look and behave identically.

Available actions (respond with EXACTLY ONE, as JSON on the last line):
  {"action":"forward","dist":1.5}   walk forward, dist in meters (0.3-4)
  {"action":"back","dist":1.0}
  {"action":"turn","deg":45}        positive = turn RIGHT, negative = LEFT
  {"action":"look","deg":-20}       positive = look DOWN, negative = UP
  {"action":"interact"}             press/use/open what you are aiming at (must be within ~3m)
  {"action":"flag","note":"short description"}   report a bug at YOUR CURRENT POSITION - stand as close to the bug as you can before flagging
  {"action":"wait","ms":1000}       stand still and observe
  {"action":"done"}                 finish the inspection

Rules:
- First write 1-3 sentences: what you observe, whether anything is anomalous, what you'll do.
- Then output the single JSON action on its own final line.
- Actively TEST the area: walk through it, view it from at least two angles. If you command forward but barely move ("BLOCKED") while nothing solid is visibly in the way, that is strong evidence of an invisible-wall bug - move right up against it and flag it.
- Inspect objects from 2-4 meters away, where the WHOLE object and its immediate surroundings fit in view - if you stand too close it leaves your field of view. Use look up/down when needed, and verify each claim against what is actually in the current image.
- The world is PAUSED while you think: time passes only during your actions. Some bugs only show over time - use wait to let time pass while observing.
- Flag each distinct bug ONCE, standing as close to it as possible.
- If after a thorough inspection nothing is wrong, output done WITHOUT flagging. Do NOT flag normal objects - false reports are penalized.
- Finish with done when the inspection is complete."""


def parse_action(text):
    m = re.findall(r"\{[^{}]*\}", text or "")
    if m:
        try:
            a = json.loads(m[-1])
            if a.get("action"):
                return a, None
        except json.JSONDecodeError as e:
            return None, str(e)
    return None, "no JSON found"


def result_text(res, cmd, proprio, notes=(), blocked=False):
    """Render one step result as text. With proprio=0 only says "executed" - no coordinates/displacement (the blocked hint also belongs to proprio)."""
    if not proprio:
        t = "action executed"
    else:
        t = (f"moved {res['moved']}m; position (x={res['pos'][0]}, z={res['pos'][2]}), "
             f"heading {res['yaw']} deg")
        if blocked:
            t += "  [you were BLOCKED - something invisible or solid is in the way]"
    for n in notes:
        t += f"  [{n}]"
    return t


FILM_NOTE = """

Observation format: for your last action you receive a short FILM STRIP - low-res frames sampled
at fixed time intervals during the action (each labeled t=+X.Xs), followed by the full-resolution
final view. Use the changes (or lack of changes) between frames to understand what happened during
your action and how the world behaves over time."""


def build_messages(task_instr, log, proprio, system=SYSTEM, obs="single"):
    """log: [{step, action_str, result_txt, dataurl, film?, reply}], appended per step.
    obs='film': the latest step carries the full strip (N low-res frames + full-res final); history keeps only the previous step's low-res final frame."""
    if obs == "film":
        system = system + FILM_NOTE
    keep = 2 if obs == "film" else KEEP_IMAGES
    msgs = [{"role": "system", "content": system}]
    old = log[:-keep] if len(log) > keep else []
    recent = log[-keep:]
    if old:
        lines = [f"step {e['step']}: {e['action_str']} -> {e['result_txt']}" for e in old]
        msgs.append({"role": "user", "content": "Earlier steps (text only):\n" + "\n".join(lines)})
        msgs.append({"role": "assistant", "content": "Understood."})
    for i, e in enumerate(recent):
        latest = i == len(recent) - 1
        content = [{"type": "text",
                    "text": f"Step {e['step']}. TASK: {task_instr}\n"
                            f"Result of your previous action: {e['result_txt']}"}]
        if obs == "film" and latest and e.get("film"):
            content.append({"type": "text",
                            "text": f"Film strip of your last action ({len(e['film'])} frames):"})
            for f in e["film"]:
                content.append({"type": "text", "text": f"t=+{f['t']}s:"})
                content.append({"type": "image_url", "image_url": {"url": f["url"]}})
            content.append({"type": "text", "text": "Current first-person view (full resolution):"})
            content.append({"type": "image_url", "image_url": {"url": e["dataurl"]}})
        elif obs == "film" and not latest:
            small = e["film"][-1]["url"] if e.get("film") else e["dataurl"]
            content.append({"type": "text", "text": "View at that step:"})
            content.append({"type": "image_url", "image_url": {"url": small}})
        else:
            content.append({"type": "text", "text": "Current first-person view:"})
            content.append({"type": "image_url", "image_url": {"url": e["dataurl"]}})
        content.append({"type": "text", "text": "Reason briefly, then output ONE action JSON."})
        msgs.append({"role": "user", "content": content})
        if e.get("reply"):
            msgs.append({"role": "assistant", "content": e["reply"]})
    return msgs
