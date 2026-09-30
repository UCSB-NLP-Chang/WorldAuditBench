import json

from agent.dashboard import build_html, collect_runs, load_run
from agent.env.fake import FakeEnv
from agent.loop import LoopConfig, run_episode
from agent.tests.fake_llm import FakeLLM
from agent.types import ObsConfig

MV = {"content": "I expect the corridor to continue.", "reasoning": "hmm, corridor", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
SCRIPT = [
    MV,
    {"content": "Let me watch.", "tools": [("wait", {"seconds": 1.0}), ("write_notes", {"text": "a1: pot looks big"})]},
    {"content": "Compare.", "tools": [("inspect", {"refs": ["a0", "a1"]}), ("inspect", {"refs": ["a1"], "region": [0.1, 0.55, 0.45, 1.0]})]},
    {"content": "Flag it.", "tools": [("flag_bug", {"description": "floating pot", "category": "geometry",
                                                    "status": "suspect", "evidence": ["a1"]})]},
    MV, MV, MV,
    {"content": "", "tools": [("history", {"from_action": 1, "to_action": 2})]},
    {"content": "", "tools": [("update_bug", {"id": "b1", "status": "confirmed"}), ("inspect", {"refs": ["zzz"]})]},
    {"content": "", "tools": [("done", {"summary": "found it"})]},
]


def _episode(tmp_path, name="ep"):
    d = tmp_path / name
    run_episode(FakeEnv(wall_x=3.5), FakeLLM(list(SCRIPT)), "Patrol.", "fake", 0, d,
                LoopConfig(obs=ObsConfig(mode="film", film_dt=0.5), context_limit=7000, keep_recent=2,
                           max_actions=20, max_calls=30))
    (d / "meta.json").write_text(json.dumps(dict(task="audit_fake_bug", config="fake", model="fake-vlm", seed=0,
                                                 outcome="done", steps_used=5, calls=11, compactions=1,
                                                 cached_ratio=0.5, obs="film", tools=["memory", "bugs", "notes"],
                                                 flags=[{"id": "b1", "status": "confirmed", "note": "floating pot",
                                                         "category": "geometry", "evidence": ["a1"], "pos": [0, 1.7, 0],
                                                         "action": 1, "simT": 0.2}],
                                                 tool_counts={"move": 4, "inspect": 2}, started="2026-09-08 10:00:00",
                                                 ended="2026-09-08 10:05:00", vlm_usage={"prompt_tokens": 100})))
    return d


def test_load_run_builds_turns_with_tools_frames_and_events(tmp_path):
    d = _episode(tmp_path)
    run = load_run(d, tmp_path)
    assert run["id"] == "ep" and run["meta"]["task"] == "audit_fake_bug"
    turns = run["turns"]
    assert turns[0]["kind"] == "start" and turns[0]["frames"][0]["ref"] == "a0"
    assert turns[0]["frames"][0]["url"] == "ep/frames/a000.jpg"          # relative to the html dir
    t1 = turns[1]
    assert t1["call"] == 1 and t1["content"].startswith("I expect") and t1["reasoning"] == "hmm, corridor"
    assert [c["name"] for c in t1["tool_calls"]] == ["move"]
    assert t1["tool_calls"][0]["args"] == {"distance_m": 1.0, "direction": "forward"}
    assert "a1 move forward 1.0m" in t1["tool_calls"][0]["result"]
    assert [f["ref"] for f in t1["tool_calls"][0]["frames"]][-1] == "a1"
    assert t1["tool_calls"][0]["action"]["index"] == 1 and t1["tool_calls"][0]["action"]["blocked"] is False
    assert t1["usage"]["prompt_tokens"] > 0                                # joined from calls.jsonl
    t2 = turns[2]
    assert [c["name"] for c in t2["tool_calls"]] == ["wait", "write_notes"]
    assert len(t2["tool_calls"][0]["frames"]) == 4                        # 3 film + final
    assert "1 entry" in t2["tool_calls"][1]["result"]
    t3 = turns[3]
    assert t3["tool_calls"][0]["name"] == "inspect" and [f["ref"] for f in t3["tool_calls"][0]["frames"]] == ["a0", "a1"]
    assert t3["tool_calls"][0]["frames"][0]["url"].endswith("a000.jpg")
    crop = t3["tool_calls"][1]["frames"][0]
    assert crop["ref"] == "a1#c1" and crop["kind"] == "crop" and "region" in crop["caption"] and "_c01" in crop["url"]
    t4 = turns[4]
    assert t4["tool_calls"][0]["name"] == "flag_bug" and t4["tool_calls"][0]["bug"] == {"id": "b1", "status": "suspect"}
    err = [c for t in turns for c in t.get("tool_calls", []) if c["name"] == "inspect" and c["error"]]
    assert err and "zzz" in err[0]["result"]
    upd = [c for t in turns for c in t.get("tool_calls", []) if c["name"] == "update_bug"][0]
    assert upd["bug"] == {"id": "b1", "status": "confirmed"}
    comp = [t for t in turns if t["kind"] == "compaction"]
    assert len(comp) == 1 and "Continuation #1" in comp[0]["header"] and "NOTE:" in comp[0]["notes"]
    assert run["path"][0]["index"] == 0 and run["path"][-1]["index"] == 5
    assert any(p["blocked"] for p in run["path"])
    assert run["ledger"][0]["id"] == "b1" and run["ledger"][0]["status"] == "confirmed"
    assert run["thumb"] == "ep/frames/a000.jpg"


def test_collect_runs_recurses_and_build_html_embeds_data(tmp_path):
    _episode(tmp_path / "tagA", "audit_fake_bug-p1-s0")
    _episode(tmp_path / "tagB", "audit_fake_bug-p1-s1")
    runs = collect_runs(tmp_path, tmp_path)
    assert sorted(r["id"] for r in runs) == ["tagA/audit_fake_bug-p1-s0", "tagB/audit_fake_bug-p1-s1"]
    html = build_html(runs, "runs")
    assert "tagA/audit_fake_bug-p1-s0/frames/a000.jpg" in html
    assert "floating pot" in html and "write_notes" in html and "inspect" in html
    assert "</script>" not in json.dumps(runs).replace("</", "<\\/") or "<\\/" in html


def test_legacy_region_inspects_get_their_crop_derived_at_build_time(tmp_path):
    """Runs recorded before crops were archived have image_ref=a<N> plus a caption with the region;
    the dashboard derives the crop (deterministic) and shows it instead of the parent frame."""
    import json
    d = _episode(tmp_path)
    rows = [json.loads(l) for l in (d / "transcript.jsonl").read_text().splitlines() if l.strip()]
    for r in rows:                                   # rewrite the archived crop ref back to the legacy form
        if isinstance(r.get("content"), list):
            for part in r["content"]:
                if part.get("type") == "image_ref" and "#c" in part["ref"]:
                    part["ref"] = part["ref"].split("#")[0]
    (d / "transcript.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    idx = [l for l in (d / "frames" / "index.jsonl").read_text().splitlines() if '"crop"' not in l]
    (d / "frames" / "index.jsonl").write_text("\n".join(idx) + "\n")
    for f in (d / "frames").glob("*_c*.jpg"):
        f.unlink()
    run = load_run(d, tmp_path)
    crop = [c for t in run["turns"] for c in t.get("tool_calls", []) if c["name"] == "inspect" and c["args"].get("region")][0]
    assert crop["frames"][0]["ref"] == "a1#c1" and crop["frames"][0]["kind"] == "crop"
    assert (d / "frames" / "a001_c01.jpg").exists()
