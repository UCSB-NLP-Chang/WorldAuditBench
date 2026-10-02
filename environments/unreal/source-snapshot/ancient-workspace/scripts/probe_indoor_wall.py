"""Read-only wall survey for the indoor split unit; never saves a level."""
import json
from pathlib import Path
import unreal

r = Path('/home/ubuntu/unreal-auditor/ancient-workspace')
out = r / 'out/indoor-cola-v3'
out.mkdir(parents=True, exist_ok=True)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert level.load_level('/Game/Auditor/AncientCity/TeaHouse')
world = editor.get_editor_world()
unreal.AuditorSceneSetup.prepare_editor_collision(world)
rows = []
raw = []
for z in range(210, 421, 15):
    for x in range(-2200, -1399, 25):
        for y in range(5200, 5901, 25):
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                h = unreal.SystemLibrary.line_trace_single_by_profile(
                    world, unreal.Vector(x, y, z),
                    unreal.Vector(x + dx * 200, y + dy * 200, z),
                    'BlockAll', True, [], unreal.DrawDebugTrace.NONE, True)
                if not h or not h.to_tuple()[0]:
                    continue
                v = h.to_tuple()
                p, n = v[5], v[6]
                if abs(n.z) > .05:
                    continue
                # Test a 90 x 30 cm backing plate, with its long axis along the wall.
                tangent = unreal.Vector(-n.y, n.x, 0)
                samples = []
                for side in [-45, 0, 45]:
                    for height in [-15, 0, 15]:
                        q = p + tangent * side + unreal.Vector(0, 0, height)
                        contact = unreal.SystemLibrary.line_trace_single_by_profile(
                            world, q + n * 5, q - n * 8, 'BlockAll', True,
                            [], unreal.DrawDebugTrace.NONE, True)
                        if contact and contact.to_tuple()[0]:
                            hit = contact.to_tuple()
                            samples.append(dict(point=list(hit[5].to_tuple()),
                                                distance=hit[3], actor=hit[9].get_name()))
                        else:
                            samples.append(None)
                raw.append(dict(point=list(p.to_tuple()), normal=list(n.to_tuple()),
                                actor=v[9].get_name(), samples=samples))
                if all(s and abs(s['distance'] - 5) < .5 for s in samples):
                    rows.append(dict(point=list(p.to_tuple()), normal=list(n.to_tuple()),
                                     actor=v[9].get_name(), samples=samples))
unique = {tuple(round(v, 1) for v in row['point'] + row['normal']): row for row in rows}
(out / 'indoor-wall-candidates.json').write_text(json.dumps(list(unique.values()), indent=2))
(out / 'indoor-wall-raw.json').write_text(json.dumps(raw, indent=2))
