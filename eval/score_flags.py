"""flag <-> answers matching (S2+).

- position-threshold matching (default 3m; per-answer radius supported)
- clean control group: every flag is a false positive
- answer positions are resolved on the human.html page side (the at-specs in
  configs/*.answers.json depend on runtime anchors such as Sponza floor points)
"""
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def resolve_answers(config_name, gpu="gl-egl"):
    """Open the human entry (non-agent) and resolve answers' at-specs into world coordinates."""
    answers_path = REPO / "env" / "configs" / f"{config_name}.answers.json"
    if not answers_path.exists():
        return []
    spec = json.loads(answers_path.read_text())
    from harness.bridge import Bridge
    with Bridge(gpu=gpu) as br:
        br.open_env(config_name, agent=False)
        return br.page.evaluate("list => window.__resolveAnswers(list)", spec)


def match_flags(flags, answers, radius=3.0):
    """flags: [{pos:[x,y,z], note}], answers: [{name, position:[x,y,z], ...}]
    Returns per-answer hits + precision/recall. Each flag matches at most one answer (the nearest)."""
    hits = {i: None for i in range(len(answers))}
    used = set()
    for fi, f in enumerate(flags):
        best, best_d = None, 1e9
        for ai, a in enumerate(answers):
            if hits[ai] is not None:
                continue
            d = math.hypot(f["pos"][0] - a["position"][0], f["pos"][2] - a["position"][2])
            if d < radius and d < best_d:
                best, best_d = ai, d
        if best is not None:
            hits[best] = dict(flag_idx=fi, dist=round(best_d, 2))
            used.add(fi)
    tp = sum(1 for v in hits.values() if v)
    fp = len(flags) - tp
    fn = len(answers) - tp
    return dict(
        tp=tp, fp=fp, fn=fn,
        precision=round(tp / len(flags), 3) if flags else None,
        recall=round(tp / len(answers), 3) if answers else None,
        per_answer={answers[i]["name"]: v for i, v in hits.items()},
        unmatched_flags=[f for i, f in enumerate(flags) if i not in used],
    )
