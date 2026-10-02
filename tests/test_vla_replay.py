"""VLA-replay environment behind the native MCP server: playback, refs, proprio text, budget, launcher config."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UPSTREAM))
pytestmark = pytest.mark.skipif(not (UPSTREAM / "agent/tools.py").exists(), reason="pinned upstream not installed")


def make_recording(root, engine="ue", ticks=1200, dt_ms=50, every=10):
    root.mkdir(parents=True)
    frames = [f"f{t:05d}.jpg" for t in range(0, ticks, every)]
    for i, name in enumerate(frames):
        img = Image.new("RGB", (192, 108), (i * 2 % 255, 40, 80))
        ImageDraw.Draw(img).text((10, 10), f"t={i * every * dt_ms / 1000:.1f}", fill="white")
        img.save(root / name, "JPEG")
    with (root / "poses.jsonl").open("w") as f:
        for t in range(ticks):
            held = ["KeyW"] if 200 <= t < 400 else []
            if engine == "ue":
                moved = 11.0 if held and t < 300 else 0.0            # blocked from tick 300: holding W without moving
                row = {"t": t, "pos_cm": [100.0 + 11.0 * min(t, 300), 200.0, 80.0], "yaw": 30.0, "pitch": 0, "moved_cm": moved, "keys": held}
            else:
                moved = 0.1 if held else 0.0
                row = {"t": t, "pos": [0.1 * t, 1.7, 5.0], "yaw": 90.0, "pitch": 0, "moved": moved, "respawned": False, "keys": held}
            f.write(json.dumps(row) + "\n")
    meta = {"task": "T1", "kind": "vla_explore_ue" if engine == "ue" else "vla_explore", "model": "open-p2p-1.2B",
            "ticks": ticks, "dt_ms": dt_ms, "record_every": every, "sim_seconds": ticks * dt_ms / 1000, "frames": frames}
    (root / "meta.json").write_text(json.dumps(meta))
    return root


def config(tmp_path, rec, **extra):
    return {"upstream": str(UPSTREAM), "run_dir": str(tmp_path / "episode"), "environment": "vla-replay",
            "replay_dir": str(rec), "task": "T1", "instruction": "Review the recording.", "scene_description": "A test scene.",
            "max_actions": 3, "max_tool_calls": 40, "observation": "on-demand", "seed": 0, **extra}


def text(result):
    return "\n".join(c.text for c in result.content if c.type == "text")


def images(result):
    return sum(c.type == "image" for c in result.content)


def test_replay_env_frames_poses_and_segments(tmp_path):
    from auditor.mcp_agent.replay import ReplayEnv
    from agent.types import Action, ObsConfig
    env = ReplayEnv(make_recording(tmp_path / "rec"))
    assert env.last_t == 59.5 and env.frame_dt == 0.5
    first = env.reset("T1", 0, ObsConfig(mode="film", film_dt=0.5, film_max=8))
    assert [f.kind for f in first.frames] == ["film"] * 11 + ["final"] and first.frames[0].t_sim == 5.0
    assert first.pose.x == pytest.approx(1.0) and first.pose.y == pytest.approx(2.0)      # cm -> m
    env.seek(10.0)
    obs = env.step(Action("wait", {"seconds": 4.0}))
    assert [round(f.t_sim, 1) for f in obs.frames] == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    assert obs.frames[-1].kind == "final" and obs.sim_elapsed == 4.0
    assert obs.moved == pytest.approx(0.11 * 80, rel=1e-6) and "forward 4.0 s" in obs.events["env_note"]
    assert "recording 10.0-14.0 s" in obs.events["env_note"]
    env.seek(15.0)
    blocked = env.step(Action("wait", {"seconds": 4.0}))                                   # ticks 300-380: W held, no motion
    assert blocked.moved == 0.0 and "forward 4.0 s" in blocked.events["env_note"]
    env.seek(58.0)
    with pytest.raises(ValueError):
        env.step(Action("wait", {"seconds": 4.0}))                                         # beyond the end
    with pytest.raises(ValueError):
        env.seek(10.3)                                                                     # not on the frame grid
    env.seek(0.0)
    tail = env.step(Action("wait", {"seconds": 1.0}))
    assert [f.kind for f in tail.frames] == ["film", "final"]
    m = env.meta()
    assert m["plays"] == 3 and m["frames_coverage"] == pytest.approx((9 + 9 + 3) / 120)


def test_threejs_recording_pose_axes(tmp_path):
    from auditor.mcp_agent.replay import ReplayEnv
    from agent.types import Action, ObsConfig
    env = ReplayEnv(make_recording(tmp_path / "rec", engine="threejs"))
    env.reset("T1", 0, ObsConfig())
    env.seek(12.0)
    obs = env.step(Action("wait", {"seconds": 2.0}))                                       # ticks 241-280: W held
    assert obs.pose.z == pytest.approx(1.7) and obs.pose.y == pytest.approx(5.0)          # y_up -> z, z -> y
    assert obs.moved == pytest.approx(0.1 * 40, rel=1e-6)


def test_mcp_episode_play_tool_and_budget(tmp_path):
    from auditor.mcp_agent.server import Episode
    rec = make_recording(tmp_path / "rec")
    episode = Episode(config(tmp_path, rec))
    try:
        names = set(episode.schemas)
        assert names == {"read_example", "observe", "play", "inspect", "history", "flag_bug", "update_bug", "list_bugs", "write_notes", "done"}
        assert "play(from_s, to_s)" in episode.instructions() and "invisible blocker" in episode.instructions()
        assert "walk through it" not in episode.instructions()
        first = episode.invoke("observe", {})
        assert not first.isError and images(first) == 12 and "Preview frames a0.f*" in text(first)
        assert episode.invoke("play", {"from_s": 10, "to_s": 15}).isError                  # > 4 s
        assert episode.invoke("play", {"from_s": 10.2, "to_s": 12}).isError                # off grid
        assert episode.dispatch.n_actions == 0
        played = episode.invoke("play", {"from_s": 10, "to_s": 14})
        t = text(played)
        assert not played.isError and images(played) == 1
        assert "a1 play 10.0-14.0s -> moved 8.80m" in t and "frames: a1.f0..a1.f6 (film), a1 (final)" in t
        assert "recording 10.0-14.0 s | explorer input: forward 4.0 s" in t and "pos (x=31.80, y=2.00) yaw 30" in t
        again = episode.invoke("play", {"from_s": 10, "to_s": 12})                         # replay, backwards in time
        assert not again.isError and "a2 play 10.0-12.0s" in text(again)
        looked = episode.invoke("inspect", {"refs": ["a1.f3", "a0.f2", "a2"]})
        assert not looked.isError and images(looked) == 3
        hist = episode.invoke("history", {"from_action": 1, "to_action": 2})
        assert "a1 [call" in text(hist) and "play 10.0-14.0s" in text(hist) and "wait" not in text(hist)
        flagged = episode.invoke("flag_bug", {"description": "test", "category": "collision", "status": "suspect", "evidence": ["a1.f3"]})
        assert not flagged.isError
        assert not episode.invoke("play", {"from_s": 56, "to_s": 59.5}).isError
        over = episode.invoke("play", {"from_s": 0, "to_s": 1})
        assert over.isError and "budget" in text(over)
        assert not episode.invoke("done", {"summary": "ok"}).isError
        meta = json.loads((tmp_path / "episode/meta.json").read_text())
        assert meta["status"] == "completed" and meta["actions_used"] == 3 and meta["backend"]["plays"] == 3
        assert meta["backend"]["engine"] == "ue" and meta["flags"][0]["evidence"] == ["a1.f3"]
        calls = [json.loads(l) for l in (tmp_path / "episode/mcp-calls.jsonl").read_text().splitlines()]
        plays = [c for c in calls if c["tool"] == "play" and not c["is_error"]]
        assert plays[0]["arguments"] == {"from_s": 10, "to_s": 14} and plays[0]["images"] == ["a1"]
        index = {json.loads(l)["ref"]: json.loads(l) for l in (tmp_path / "episode/frames/index.jsonl").read_text().splitlines()}
        assert index["a1.f3"]["t_sim"] == 2.0 and index["a1"]["t_sim"] == 4.0
    finally:
        episode.close()


@pytest.mark.requires_icl
def test_launcher_prepares_replay_run(tmp_path):
    rec = make_recording(tmp_path / "rec")
    scene = tmp_path / "scene.txt"
    scene.write_text("A test scene.\n")
    run = tmp_path / "run"
    cmd = [sys.executable, str(ROOT / "scripts/native-agents/launch.py"), "gemini", "--environment", "vla-replay",
           "--replay-dir", str(rec), "--task", "T1", "--legacy-task-files", "--subcategory", "C2", "--scene-description-file", str(scene),
           "--gemini-auth", "gemini-api-key", "--run-dir", str(run), "--dry-run", "--max-actions", "40"]
    subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=ROOT)
    launch = json.loads((run / "launch.json").read_text())
    assert launch["tools"] == ["read_example", "observe", "play", "inspect", "history", "write_notes", "flag_bug", "update_bug", "list_bugs", "done"]
    assert launch["evaluation_eligible"] is True
    episode = json.loads((run / "episode-config.json").read_text())
    assert episode["environment"] == "vla-replay" and episode["replay_dir"] == str(rec.resolve())
    assert episode["recording"]["frames"] == 120 and episode["recording"]["explorer"] == "open-p2p-1.2B"
    prompt = (run / "prompt.txt").read_text()
    assert "40 play actions" in prompt and "do not control the camera" in prompt and 'read_example(code="C2")' in prompt
    settings = json.loads((run / "gemini-settings.json").read_text())
    assert settings["mcpServers"]["world_audit"]["includeTools"] == launch["tools"]


def test_mcp_episode_all_frames_mode(tmp_path):
    import importlib.util
    from auditor.mcp_agent.server import Episode
    rec = make_recording(tmp_path / "rec")
    cfg = config(tmp_path, rec, replay_mode="all", max_actions=0, preview_every=0.5)
    episode = Episode(cfg)
    try:
        assert set(episode.schemas) == {"read_example", "observe", "inspect", "history", "flag_bug", "update_bug", "list_bugs", "write_notes", "done"}
        ins = episode.instructions()
        assert "FILM STRIP" in ins and "There are no environment actions" in ins and "play(" not in ins
        first = episode.invoke("observe", {})
        t = text(first)
        assert not first.isError and images(first) == 120
        assert "Explorer track" in t and "t=59.5s a0.f118:" in t
        assert "t=15.0s a0.f29: pos (34.00, 2.00) yaw 30 pitch 0 | moved 0.99 m | input fwd 0.5 s back 0.0 s" in t
        assert "t=15.5s a0.f30: pos (34.00, 2.00) yaw 30 pitch 0 | moved 0.00 m | input fwd 0.5 s back 0.0 s" in t   # held W, no motion
        assert "119 of them, every 0.5 s, are shown below" in t
        looked = episode.invoke("inspect", {"refs": ["a0.f28", "a0.f29"], "region": [0.2, 0.2, 0.8, 0.8]})
        assert not looked.isError and images(looked) == 2 and "t=+14.5s" in text(looked)
        assert not episode.invoke("flag_bug", {"description": "x", "category": "collision", "status": "confirmed", "evidence": ["a0.f29#c1", "a0.f30"]}).isError
        assert not episode.invoke("done", {"summary": "ok"}).isError
        meta = json.loads((tmp_path / "episode/meta.json").read_text())
        assert meta["status"] == "completed" and meta["actions_used"] == 0 and meta["backend"]["mode"] == "all" and meta["max_actions"] == 0
        spec = importlib.util.spec_from_file_location("after_agent", ROOT / "scripts/native-agents/after_agent.py")
        hook = importlib.util.module_from_spec(spec); spec.loader.exec_module(hook)
        result, _ = hook.decide(cfg, {"actions_used": 0, "tool_calls": 3}, {})
        assert result["decision"] == "block" and "done now" in result["reason"]
        assert hook.decide(cfg, {"status": "completed"}, {})[0] == {}
    finally:
        episode.close()


@pytest.mark.requires_icl
def test_launcher_all_mode_requires_zero_actions(tmp_path):
    rec = make_recording(tmp_path / "rec")
    scene = tmp_path / "scene.txt"; scene.write_text("A test scene.\n")
    base = [sys.executable, str(ROOT / "scripts/native-agents/launch.py"), "gemini", "--environment", "vla-replay", "--replay-dir", str(rec),
            "--task", "T1", "--legacy-task-files", "--subcategory", "C2", "--scene-description-file", str(scene), "--gemini-auth", "gemini-api-key", "--dry-run",
            "--replay-mode", "all"]
    bad = subprocess.run(base + ["--run-dir", str(tmp_path / "bad"), "--max-actions", "40"], capture_output=True, text=True, cwd=ROOT)
    assert bad.returncode and "max-actions 0" in bad.stdout + bad.stderr
    run = tmp_path / "run"
    subprocess.run(base + ["--run-dir", str(run), "--max-actions", "0"], check=True, capture_output=True, text=True, cwd=ROOT)
    launch = json.loads((run / "launch.json").read_text())
    assert "play" not in launch["tools"] and "inspect" in launch["tools"]
    prompt = (run / "prompt.txt").read_text()
    assert "There are no environment actions" in prompt and "40" not in prompt.split("Environment description")[1].split("subcategory")[0]


def test_all_mode_sparse_inline_keeps_every_frame_archived(tmp_path):
    from auditor.mcp_agent.server import Episode
    rec = make_recording(tmp_path / "rec")
    episode = Episode(config(tmp_path, rec, replay_mode="all", max_actions=0, preview_every=2.0))
    try:
        first = episode.invoke("observe", {})
        assert images(first) == 1 + 29 and "29 of them, every 2 s" in text(first)          # a0 + t = 2, 4, ..., 58
        assert "a0.f3 t=+2.0s" in text(first) and "a0.f2 t=+1.5s" not in text(first)
        looked = episode.invoke("inspect", {"refs": ["a0.f2", "a0.f118"]})                 # not inline, still archived
        assert not looked.isError and images(looked) == 2
    finally:
        episode.close()


def test_inspect_budget_and_no_inspect_tool(tmp_path):
    from auditor.mcp_agent.server import Episode
    rec = make_recording(tmp_path / "rec")
    episode = Episode(config(tmp_path, rec, replay_mode="all", max_actions=0, preview_every=1.0, inspect_budget=0))
    try:
        assert "inspect" not in episode.schemas and "no inspect tool" in episode.instructions() and "Use inspect" not in episode.instructions()
        first = episode.invoke("observe", {})
        assert images(first) == 1 + 59 and "There is no inspect tool" in text(first)
        assert episode.invoke("inspect", {"refs": ["a0.f1"]}).isError
        assert not episode.invoke("flag_bug", {"description": "x", "category": "visual", "status": "suspect", "evidence": ["a0.f3"]}).isError
        assert not episode.invoke("done", {"summary": "ok"}).isError
    finally:
        episode.close()
    episode = Episode({**config(tmp_path / "b", rec, replay_mode="all", max_actions=0, preview_every=2.0), "inspect_budget": 2})
    try:
        assert "At most 2 inspect calls" in episode.schemas["inspect"]["description"]
        episode.invoke("observe", {})
        assert not episode.invoke("inspect", {"refs": ["a0.f1"]}).isError
        assert not episode.invoke("inspect", {"refs": ["a0.f2"]}).isError
        over = episode.invoke("inspect", {"refs": ["a0.f3"]})
        assert over.isError and "budget" in text(over)
        assert not episode.invoke("done", {"summary": "ok"}).isError
    finally:
        episode.close()


def test_inline_size_fits_byte_budget(tmp_path):
    from auditor.mcp_agent.replay import ReplayEnv
    env = ReplayEnv(make_recording(tmp_path / "rec"), preview_every=0.5, mode="all")
    assert env.inline_size((960, 576), budget_bytes=10 ** 9) == (960, 576)
    assert env.inline_size((960, 576), budget_bytes=1) == (480, 288)
    sparse = ReplayEnv(tmp_path / "rec", preview_every=10.0, mode="all")
    assert sparse.inline_size((960, 576), budget_bytes=200_000) in {(960, 576), (800, 480), (640, 384), (480, 288)}


def test_vqa_mode_single_report(tmp_path):
    import importlib.util
    from auditor.mcp_agent.server import Episode
    rec = make_recording(tmp_path / "rec")
    cfg = config(tmp_path, rec, replay_mode="vqa", max_actions=0)
    episode = Episode(cfg)
    try:
        assert set(episode.schemas) == {"read_example", "observe", "report"}
        ins = episode.instructions()
        assert "ONE report call" in ins and "inspect(" not in ins and "Use inspect" not in ins and "End with report." in ins
        first = episode.invoke("observe", {})
        assert not first.isError and images(first) == 120 and "Answer with ONE report call" in text(first) and "Explorer track" in text(first)
        bad = episode.invoke("report", {"bugs": [{"description": "x", "category": "visual", "status": "suspect", "evidence": ["a9"]}], "summary": "s"})
        assert not bad.isError and "dropped unknown frame ref(s): a9" in text(bad)   # bad refs are dropped, the bug and the run still count
        assert episode.dispatch.done
        meta = json.loads((tmp_path / "episode/meta.json").read_text())
        assert meta["status"] == "completed" and meta["flags"][0]["evidence"] == [] and meta["done_summary"] == "s"
    finally:
        episode.close()
    episode = Episode(config(tmp_path / "b", rec, replay_mode="vqa", max_actions=0))
    try:
        episode.invoke("observe", {})
        assert episode.invoke("flag_bug", {"description": "x", "category": "visual", "status": "suspect"}).isError
        r = episode.invoke("report", {"bugs": [{"description": "chair floats", "category": "geometry", "status": "confirmed", "evidence": ["a0.f10", "a0.f11"]},
                                               {"description": "wall", "category": "collision", "status": "suspect", "evidence": []}], "summary": "two"})
        assert not r.isError and "Recorded b1" in text(r) and "Recorded b2" in text(r) and "Inspection finished" in text(r)
        meta = json.loads((tmp_path / "b/episode/meta.json").read_text())
        assert [f["evidence"] for f in meta["flags"]] == [["a0.f10", "a0.f11"], []] and meta["done_summary"] == "two"
        assert episode.invoke("report", {"bugs": [], "summary": "again"}).isError
        calls = [json.loads(l) for l in (tmp_path / "b/episode/mcp-calls.jsonl").read_text().splitlines()]
        assert [c["tool"] for c in calls] == ["observe", "flag_bug", "report", "report"]
        spec = importlib.util.spec_from_file_location("after_agent", ROOT / "scripts/native-agents/after_agent.py")
        hook = importlib.util.module_from_spec(spec); spec.loader.exec_module(hook)
        assert "report now" in hook.decide({**config(tmp_path, rec, replay_mode="vqa", max_actions=0)}, {"actions_used": 0, "tool_calls": 2}, {})[0]["reason"]
    finally:
        episode.close()
