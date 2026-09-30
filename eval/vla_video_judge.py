#!/usr/bin/env python3
"""Gemini judges the VLA explorer's recordings with the SAME knowledge the VLM agents of the iclr framework get.

For every episode under runs/<tag>/<config>-s0/ (frames every 0.5 s of simulated time), the model receives
  1. the agents' task instruction (scripts/native-agents/launch.py DEFAULT_INSTRUCTION),
  2. the task's public environment description (task-scenes.json, same as the agents' "Environment description"),
  3. the ONE in-context example of the task's subcategory (output/icl-unreal-20260916: definition, 1-3 figures with
     captions, reference answer - the agents read it through read_example), and
  4. the recording as timestamped frames (480x300, the agents' film-frame size),
and must answer with the agents' report structure: a JSON list of bugs {description, category, status, evidence
(timestamps)} - or an empty list.  A second, text-only call grades each reported bug against the planted bug's
ground-truth text with the strict judge prompt of eval/judge_sem.py (an automatic estimate; the VLM arm is graded by
people, so reports are also written to a grades template for the same manual procedure).

usage: .venv/bin/python -m eval.vla_video_judge runs/vla-threejs-v2 --episodes exposed --out reports/vla-gemini-v2
       [--model gemini-3.8-flash] [--thinking medium] [--workers 8] [--limit 3] [--dry-run] [--no-judge]
       .venv/bin/python -m eval.vla_video_judge runs/vla-ue-v1 --env ue --episodes all --out reports/vla-ue-gemini-v1
         (Unreal episodes of harness/vla_ue.py: task = catalog entry of reports/ue-aws-profiles-<date>.json, ground truth = the
          task's English rubric criterion, scene = the public description the agents get, frames 480x270)
GEMINI_API_KEY from the environment or ~/.config/gemini/api_key.
"""
import argparse, base64, concurrent.futures, json, os, pathlib, re, sys, time, threading
from PIL import Image
import io

REPO = pathlib.Path(__file__).resolve().parents[1]
ICLR = pathlib.Path(os.environ.get("GA_ICLR", "/home/ubuntu/game-auditing-iclr"))
sys.path.insert(0, str(REPO))
from eval.judge_sem import GT, JUDGE_PROMPT  # noqa: E402

DEFAULT_INSTRUCTION = ("Inspect the assigned 3D environment for bugs. Explore and gather visual evidence. "
                       "Report each distinct bug with a clear description, category, and evidence frame refs. "
                       "Do not assume every unusual object is a bug. Finish with done.")
CATEGORIES = ["geometry", "collision", "visual", "state", "semantic", "other"]
REPORT_SCHEMA = {"type": "object", "properties": {"bugs": {"type": "array", "items": {"type": "object", "properties": {
    "description": {"type": "string"}, "category": {"type": "string", "enum": CATEGORIES},
    "status": {"type": "string", "enum": ["suspect", "confirmed"]},
    "evidence": {"type": "array", "items": {"type": "string"}}}, "required": ["description", "category", "status", "evidence"]}},
    "summary": {"type": "string"}}, "required": ["bugs", "summary"]}
FRAME_W, FRAME_H = 480, 300


def api_key():
    k = os.environ.get("GEMINI_API_KEY")
    if not k:
        p = pathlib.Path.home() / ".config/gemini/api_key"
        if p.exists(): k = p.read_text().strip()
    if not k: raise SystemExit("GEMINI_API_KEY missing (env or ~/.config/gemini/api_key)")
    return k


def load_catalogs():
    tasks = json.loads((REPO / "reports/eval-task-sets-2026-09-17.json").read_text())["threejs"]["tasks"]
    by_case = {t["source_case"]: t for t in tasks}
    scenes = json.loads((ICLR / "scripts/native-agents/task-scenes.json").read_text())["scenes"]
    scene_of = {tid: s["description"]["en"] for s in scenes for tid in s["task_ids"]}
    sub = json.loads((ICLR / "scripts/native-agents/task-subcategories.json").read_text())["task_subcategories"]
    return by_case, scene_of, sub


def load_ue_catalog(profiles):
    """Unreal bug tasks of the mirrored AWS release: subcategory code, English rubric criterion (ground truth), public scene text."""
    from eval.vla_exposure_ue import CODE
    d = json.loads(pathlib.Path(profiles).read_text())["tasks"]
    scenes = json.loads((ICLR / "scripts/native-agents/task-scenes.json").read_text())["scenes"]
    scene_of = {tid: sc["description"]["en"] for sc in scenes for tid in sc["task_ids"]}
    map_scene = {}   # a task added after the snapshot (S22) takes the public text of the other tasks on its map
    for tid, e in d.items():
        if scene_of.get(tid): map_scene.setdefault(e["policy"].get("map"), scene_of[tid])
    tasks = {}
    for tid, e in d.items():
        if e["case_type"] != "bug": continue
        t = e["task"]; raw = t.get("subcategory") or ""; code = CODE.get(raw, raw if len(raw) == 2 else raw[:2].upper())
        r = (t.get("rubrics_i18n") or {}).get("en") or {}
        scene = scene_of.get(tid) or ((t.get("scene_i18n") or {}).get("en") or "") or map_scene.get(e["policy"].get("map"), "")
        tasks[tid] = {"id": tid, "family": e["family"], "code": code, "gt": r.get("criteria") or t.get("title") or "", "scene": scene}
    return tasks


def example_for(code, icl_dir):
    ctx = json.loads((icl_dir / "context.json").read_text())
    msgs = ctx["messages"]
    for i in range(0, len(msgs) - 1, 2):
        u, a = msgs[i], msgs[i + 1]
        content = u["content"] if isinstance(u["content"], list) else [{"type": "text", "text": u["content"]}]
        first = next((c["text"] for c in content if c.get("type") == "text"), "")
        if first.startswith(code + " "):
            parts = []
            for c in content:
                if c.get("type") == "text": parts.append(("text", c["text"]))
                elif c.get("type") == "image": parts.append(("image", icl_dir / c["path"], c.get("media_type", "image/png")))
            ans = a["content"] if isinstance(a["content"], str) else " ".join(c.get("text", "") for c in a["content"] if c.get("type") == "text")
            return parts, ans
    raise KeyError(code)


def frames_of(ep, dt_ms=50, record_every=10):
    files = sorted(ep.glob("f*.jpg"))
    out = []
    for f in files:
        t = int(f.stem[1:]) * dt_ms / 1000.0   # file names carry the tick index (f01190 = tick 1190 = 59.5 s)
        img = Image.open(f).convert("RGB"); img = img.resize((FRAME_W, round(FRAME_W * img.height / img.width)), Image.BILINEAR)
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=80); out.append((t, buf.getvalue()))
    return out


def build_contents(types, cfg, task, scene, code, example, frames, max_actions=40):
    parts = [types.Part.from_text(text=(
        f"{DEFAULT_INSTRUCTION}\n\nEnvironment description:\n{scene}\n\n"
        "This is an environment auditing run. You did not control the camera: a separate explorer walked through the scene and "
        "the recording below is everything it saw, as frames every 0.5 s of simulated time. Inspect the frames for details. "
        "Report bugs in the structured answer and do not invent observations that are not in the frames.\n"))]
    if example:
        parts.append(types.Part.from_text(text=(
            f"This task's specific subcategory is {code}. Below is its ONE matching demonstration: a category definition, "
            "1-3 real images with figure captions, and a reference answer. It is a supplied demonstration, not a question you need "
            "to answer, and its images are not evidence for the recording below.\n")))
        ex_parts, ans = example
        for p in ex_parts:
            if p[0] == "text": parts.append(types.Part.from_text(text=p[1]))
            else: parts.append(types.Part.from_bytes(data=pathlib.Path(p[1]).read_bytes(), mime_type=p[2]))
        parts.append(types.Part.from_text(text=f"Reference answer: {ans}\n"))
    parts.append(types.Part.from_text(text=f"RECORDING ({len(frames)} frames, chronological, 0.5 s apart):\n"))
    for t, jpg in frames:
        parts.append(types.Part.from_text(text=f"t={t:.1f}s"))
        parts.append(types.Part.from_bytes(data=jpg, mime_type="image/jpeg"))
    parts.append(types.Part.from_text(text=(
        "Now report. Answer as JSON: {\"bugs\": [{\"description\": what is wrong, which object, how you know; "
        "\"category\": one of geometry / collision / visual / state / semantic / other; \"status\": suspect or confirmed; "
        "\"evidence\": the timestamps (like \"t=12.5s\") that show it}], \"summary\": one sentence}. "
        "Report each distinct bug once; an empty list is the right answer if the recording shows no bug.")))
    return parts


def call_gemini(client, types, model, contents, thinking, schema=None, max_tries=5):
    cfg = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level=thinking.upper()) if thinking else None,
                                      response_mime_type="application/json" if schema else None, response_schema=schema)
    delay = 5
    for i in range(max_tries):
        try:
            r = client.models.generate_content(model=model, contents=contents, config=cfg)
            usage = getattr(r, "usage_metadata", None)
            return r.text, {"prompt_tokens": getattr(usage, "prompt_token_count", None), "output_tokens": getattr(usage, "candidates_token_count", None),
                            "thinking_tokens": getattr(usage, "thoughts_token_count", None)}
        except Exception as e:
            msg = str(e)
            if i == max_tries - 1 or not any(k in msg for k in ("429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE", "overloaded")):
                raise
            time.sleep(delay); delay = min(delay * 2, 60)


def judge_report(client, types, model, gt, note):
    text, usage = call_gemini(client, types, model, [types.Part.from_text(text=JUDGE_PROMPT.format(gt=gt, note=note))], thinking="low")
    m = re.findall(r'\{\s*"match"\s*:\s*(true|false)\s*\}', text)
    return (m[-1] == "true") if m else None, text, usage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_base"); ap.add_argument("--out", required=True)
    ap.add_argument("--episodes", default="exposed", help="exposed | all | comma-separated configs")
    ap.add_argument("--model", default="gemini-3.8-flash"); ap.add_argument("--judge-model", default=None)
    ap.add_argument("--thinking", default="medium"); ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--icl-dir", default=str(ICLR / "output/icl-unreal-20260916"))
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--fallback-code", default="{}", help='JSON {config: code} for cases without a subcategory label')
    ap.add_argument("--env", default="threejs", choices=["threejs", "ue"], help="ue: Unreal episodes of harness/vla_ue.py (runs/<tag>/<TASK>/)")
    ap.add_argument("--profiles", default=str(REPO / "reports/ue-aws-profiles-20260918.json"), help="--env ue: mirrored AWS catalog")
    a = ap.parse_args()
    run_base = pathlib.Path(a.run_base); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fallback = json.loads(a.fallback_code)
    if a.env == "ue":
        ue = load_ue_catalog(a.profiles)
        exposure = {r["task"]: r for r in json.loads((run_base / "exposure.json").read_text())} if (run_base / "exposure.json").exists() else {}
        ep_dir = lambda cfg: run_base / cfg
        gt_of = lambda cfg: ue[cfg]["gt"]
        group_of = lambda cfg: ue[cfg]["family"]
        if a.episodes == "exposed": cfgs = [c for c, r in exposure.items() if r.get("exposed")]
        elif a.episodes == "all": cfgs = sorted(p.name for p in run_base.iterdir() if p.is_dir() and (p / "meta.json").exists() and p.name in ue)
        else: cfgs = a.episodes.split(",")
        if a.limit: cfgs = cfgs[:a.limit]
        jobs = [(cfg, {"id": cfg}, ue[cfg]["scene"], ue[cfg]["code"]) for cfg in cfgs]
    else:
        by_case, scene_of, sub = load_catalogs()
        exposure = {r["config"]: r for r in json.loads((run_base / "exposure.json").read_text())} if (run_base / "exposure.json").exists() else {}
        ep_dir = lambda cfg: run_base / f"{cfg}-s0"
        gt_of = lambda cfg: GT.get(cfg[:4])
        group_of = lambda cfg: cfg[:2].upper()
        if a.episodes == "exposed": cfgs = [c for c, r in exposure.items() if r["exposed"]]
        elif a.episodes == "all": cfgs = sorted(p.name[:-3] for p in run_base.glob("*-s0") if (p / "meta.json").exists())
        else: cfgs = a.episodes.split(",")
        if a.limit: cfgs = cfgs[:a.limit]
        jobs = []
        for cfg in cfgs:
            task = by_case[cfg]; code = sub.get(task["id"]) or fallback.get(cfg)
            if not code: print(f"{cfg}: no subcategory label and no fallback, skipped"); continue
            jobs.append((cfg, task, scene_of.get(task["id"], ""), code))
    print(f"{len(jobs)} episodes | model {a.model} thinking {a.thinking} | icl {a.icl_dir}", flush=True)
    if a.dry_run:
        for cfg, task, scene, code in jobs[:5]:
            frames = frames_of(ep_dir(cfg)); ex, ans = example_for(code, pathlib.Path(a.icl_dir))
            print(f"  {cfg}: task {task['id']} code {code} | scene: {scene[:80]}... | example parts {len(ex)} (images {sum(1 for p in ex if p[0]=='image')}) | frames {len(frames)} ({sum(len(j) for _, j in frames)//1024} KB) | GT: {(gt_of(cfg) or '?')[:80]}")
        return
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key())
    judge_model = a.judge_model or a.model
    lock = threading.Lock(); results = {}
    def work(job):
        cfg, task, scene, code = job
        dst = out / f"{cfg}.json"
        if dst.exists():
            with lock: results[cfg] = json.loads(dst.read_text()); return
        t0 = time.time(); frames = frames_of(ep_dir(cfg)); example = example_for(code, pathlib.Path(a.icl_dir))
        contents = build_contents(types, cfg, task, scene, code, example, frames)
        text, usage = call_gemini(client, types, a.model, contents, a.thinking, schema=REPORT_SCHEMA)
        try: report = json.loads(text)
        except Exception: report = {"bugs": [], "summary": "", "parse_error": text[:500]}
        rec = {"config": cfg, "task": task["id"], "subcategory": code, "model": a.model, "thinking": a.thinking, "n_frames": len(frames),
               "report": report, "usage": usage, "gt": gt_of(cfg), "exposed": exposure.get(cfg, {}).get("exposed"), "judged": [], "wall_s": round(time.time() - t0, 1)}
        if not a.no_judge and gt_of(cfg):
            for b in report.get("bugs", []):
                note = f"{b.get('description', '')} (category: {b.get('category')}, {b.get('status')})"
                match, jtext, jusage = judge_report(client, types, judge_model, gt_of(cfg), note)
                rec["judged"].append({"description": b.get("description"), "category": b.get("category"), "status": b.get("status"), "match": match, "judge_text": jtext[-300:]})
        rec["found"] = any(j["match"] for j in rec["judged"]) if rec["judged"] else False
        dst.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        with lock:
            results[cfg] = rec
            print(f"  {cfg:20s} bugs {len(report.get('bugs', [])):2d} matched {sum(1 for j in rec['judged'] if j['match'])} | {rec['wall_s']} s | prompt tokens {usage.get('prompt_tokens')}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(work, jobs))
    rows = [results[c] for c, *_ in jobs if c in results]
    # summary
    import collections
    by = collections.defaultdict(list)
    for r in rows: by[group_of(r["config"])].append(r)
    lines = [f"# Gemini video judge on VLA recordings - {run_base.name}", "", f"model {a.model}, thinking {a.thinking}, ICL example on, {len(rows)} episodes ({a.episodes})", "",
             "| suite | episodes | found (any report matches the planted bug) | reports | matched reports | unmatched reports |", "|---|---|---|---|---|---|"]
    for s, rs in sorted(by.items()):
        rep = sum(len(r["judged"]) for r in rs); mt = sum(sum(1 for j in r["judged"] if j["match"]) for r in rs)
        lines.append(f"| {str(s).upper()} | {len(rs)} | {sum(r['found'] for r in rs)} | {rep} | {mt} | {rep - mt} |")
    rep = sum(len(r["judged"]) for r in rows); mt = sum(sum(1 for j in r["judged"] if j["match"]) for r in rows)
    lines.append(f"| **all** | {len(rows)} | **{sum(r['found'] for r in rows)}** | {rep} | {mt} | {rep - mt} |")
    lines += ["", "## Per episode", "", "| case | found | reports | first matched / first report |", "|---|---|---|---|"]
    for r in rows:
        first = next((j["description"] for j in r["judged"] if j["match"]), (r["judged"][0]["description"] if r["judged"] else "-"))
        lines.append(f"| {r['config']} | {'yes' if r['found'] else 'no'} | {len(r['judged'])} | {str(first)[:110].replace('|', '/')} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n"); print("\n".join(lines[:12]))
    # grades template for the same manual procedure as the VLM arm
    (out / "grades-template.json").write_text(json.dumps({r["task"]: {"target_found": None, "reason": "", "auto_estimate": r["found"], "reports": [j["description"] for j in r["judged"]]} for r in rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
