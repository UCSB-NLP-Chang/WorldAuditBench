"""Contract tests with a real stdio MCP client and a clearly synthetic environment."""
import asyncio
import importlib.util
import json
import base64
import io
from pathlib import Path
import sys

import pytest
from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UPSTREAM))
from auditor.mcp_agent.server import Episode


def config(tmp_path, mode="on-demand"):
    return {"upstream": str(UPSTREAM), "run_dir": str(tmp_path / "episode"),
            "environment": "fake", "task": "synthetic-smoke", "instruction": "Synthetic smoke test.",
            "max_actions": 2, "max_tool_calls": 40, "observation": mode, "seed": 0}


def image_count(result):
    return sum(c.type == "image" for c in result.content)


def text(result):
    return "\n".join(c.text for c in result.content if c.type == "text")


def test_stdio_round_trip_archive_crop_budget_and_done(tmp_path):
    cfg = config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))

    async def check():
        params = StdioServerParameters(command=sys.executable,
                                        args=[str(ROOT / "auditor/mcp_agent/server.py"), "--config", str(path)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert names == {"read_example", "observe", "move", "turn", "look", "interact", "wait", "done",
                                 "inspect", "history", "flag_bug", "update_bug", "list_bugs", "write_notes"}
                assert not (tmp_path / "episode/episode.started").exists()  # Discovery never starts a game.
                first = await session.call_tool("observe", {})
                assert image_count(first) == 1 and not first.isError
                waited = await session.call_tool("wait", {"seconds": 2})
                assert image_count(waited) == 1 and "a1.f0" in text(waited)
                recalled = await session.call_tool("inspect", {"refs": ["a0", "a1.f0", "a1"]})
                assert image_count(recalled) == 3 and not recalled.isError
                crop = await session.call_tool("inspect", {"refs": ["a1.f0"], "region": [.1, .2, .8, .9]})
                assert image_count(crop) == 1 and "#c1" in text(crop)
                assert (await session.call_tool("inspect", {"refs": ["a0"] * 5})).isError
                assert (await session.call_tool("inspect", {"refs": ["a999"]})).isError
                assert (await session.call_tool("move", {"distance_m": 999, "direction": "forward"})).isError
                note = await session.call_tool("write_notes", {"text": "Recheck a1.f0."})
                assert not note.isError
                flag = await session.call_tool("flag_bug", {"description": "Synthetic hypothesis", "category": "visual",
                                                            "status": "suspect", "evidence": ["a1.f0"]})
                assert not flag.isError
                assert not (await session.call_tool("update_bug", {"id": "b1", "status": "retracted"})).isError
                assert not (await session.call_tool("turn", {"degrees": 30})).isError
                assert (await session.call_tool("move", {"distance_m": 1, "direction": "forward"})).isError
                history = await session.call_tool("history", {"from_action": 1, "to_action": 2})
                assert "wait" in text(history) and "turn" in text(history)
                assert not (await session.call_tool("done", {"summary": "Synthetic transport verified"})).isError
                assert (await session.call_tool("wait", {"seconds": 1})).isError
    asyncio.run(check())
    meta = json.loads((tmp_path / "episode/meta.json").read_text())
    assert meta["status"] == "completed" and meta["actions_used"] == 2
    assert meta["flags"] == []
    assert "Recheck" in (tmp_path / "episode/notes.md").read_text()


@pytest.mark.parametrize("mode,count", [("film", 6), ("final", 1), ("on-demand", 1)])
def test_delivery_modes(tmp_path, mode, count):
    e = Episode(config(tmp_path, mode))
    try:
        r = e.invoke("wait", {"seconds": 2})
        assert not r.isError, text(r)
        assert image_count(r) == count
        if mode != "final":
            assert e.archive.has("a1.f3")
    finally:
        e.close()


@pytest.mark.requires_icl
def test_schema_same_and_native_launchers_are_single_process(tmp_path):
    spec = importlib.util.spec_from_file_location("native_launch", ROOT / "scripts/native-agents/launch.py")
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    runs = []
    for client in ["codex", "gemini"]:
        args = launch.cli_parser().parse_args([client, "--environment", "fake", "--task", "smoke",
                                               "--subcategory", "C3", "--run-dir", str(tmp_path / client), "--dry-run"])
        run, cmd, env, _, manifest = launch.prepare(args)
        assert manifest["model_requested"] == launch.MODELS[client]
        assert manifest["icl"]["example_count"] == 1 and manifest["icl"]["image_count"] == 3
        assert (run / "icl/context.json").exists()
        runs.append((run, manifest))
        assert "resume" not in cmd
        cfg = json.loads((run / "episode-config.json").read_text())
        e = Episode(cfg)
        try:
            assert set(e.schemas) == set(launch.TOOLS)
        finally:
            e.close()
        if client == "codex":
            assert "--ignore-user-config" in cmd
            assert "forced_login_method=\"chatgpt\"" in cmd
            assert "OPENAI_API_KEY" not in env
        else:
            settings = json.loads((run / "gemini-settings.json").read_text())
            assert settings["tools"]["core"] == []
            assert settings["mcp"]["allowed"] == ["world_audit"]
            assert settings["modelConfigs"]["customOverrides"][0]["modelConfig"]["generateContentConfig"]["thinkingConfig"]["thinkingLevel"] == "MEDIUM"
    assert runs[0][1]["protocol_sha256"] == runs[1][1]["protocol_sha256"]


@pytest.mark.requires_icl
def test_icl_real_stdio_images_order_gating_recall_and_evidence_separation(tmp_path):
    from auditor.mcp_agent.examples import ExamplePack
    pack = ExamplePack(ROOT / "examples/icl", code="C3").snapshot(tmp_path / "icl")
    cfg = {**config(tmp_path), "subcategory": "C3", "icl": pack.manifest(), "icl_directory": str(pack.root)}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))

    async def check():
        params = StdioServerParameters(command=sys.executable,
                                        args=[str(ROOT / "auditor/mcp_agent/server.py"), "--config", str(path)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert (await session.call_tool("observe", {})).isError
                assert (await session.call_tool("wait", {"seconds": .5})).isError
                assert not (tmp_path / "episode/episode.started").exists()
                assert (await session.call_tool("read_example", {"code": "G1"})).isError
                count = 0
                for code, example in pack.examples.items():
                    result = await session.call_tool("read_example", {})
                    assert not result.isError, text(result)
                    assert f"ICL demonstration {code}:" in text(result)
                    assert "Reference answer" in text(result)
                    assert image_count(result) == example["image_count"]
                    first_image = next(i for i, c in enumerate(result.content) if c.type == "image")
                    answer = next(i for i, c in enumerate(result.content)
                                  if c.type == "text" and c.text.startswith("Reference answer"))
                    assert first_image > 0 and answer > first_image
                    expected = [b for m in example["messages"] for b in m["content"] if b["type"] == "image"]
                    delivered = [c for c in result.content if c.type == "image"]
                    for source, received in zip(expected, delivered):
                        assert base64.b64decode(received.data) == (pack.root / source["path"]).read_bytes()
                    meta = json.loads((tmp_path / "episode/meta.json").read_text())
                    assert meta["actions_used"] == 0 and meta["environment_started"] is False
                    count += image_count(result)
                assert count == 3
                assert not (await session.call_tool("observe", {})).isError
                recall = await session.call_tool("read_example", {"code": "C3"})
                assert image_count(recall) == 3 and not recall.isError
                assert (await session.call_tool("flag_bug", {
                    "description": "Do not let demonstration evidence leak into reports",
                    "category": "collision", "evidence": ["icl:C3:1"]})).isError
                assert not (await session.call_tool("wait", {"seconds": .5})).isError
                assert not (await session.call_tool("done", {"summary": "ICL transport verified"})).isError
    asyncio.run(check())
    meta = json.loads((tmp_path / "episode/meta.json").read_text())
    assert meta["icl_complete"] and meta["actions_used"] == 1 and meta["status"] == "completed"
    assert meta["icl_examples_delivered"] == ["C3"]
    assert sorted(p.name for p in (pack.root / "images").iterdir()) == ["C3_01.png", "C3_02.png", "C3_03.png"]


@pytest.mark.requires_icl
def test_icl_exclusion_aliases_snapshot_integrity_and_zero_shot(tmp_path):
    from auditor.mcp_agent.examples import ExamplePack
    pack = ExamplePack(ROOT / "examples/icl", code="G1")
    for task in ["S05", "s05", "U019", "A21", "JS_WL12"]:
        with pytest.raises(ValueError, match="ICL demonstration/alias"):
            pack.check_task(task)
        assert pack.check_task(task, allow_overlap=True)
    assert not pack.check_task("held-out-task")
    saved = pack.snapshot(tmp_path / "icl")
    assert saved.sha256 == pack.sha256
    assert not (saved.root / "examples.json").exists()  # No review/rubric metadata copied.
    path = saved.root / "images/G1_01.png"
    path.write_bytes(path.read_bytes() + b"modified")
    with pytest.raises(ValueError, match="changed"):
        saved.content("G1")
    cfg = {**config(tmp_path / "tamper"), "subcategory": "G1", "icl_directory": str(saved.root), "icl": pack.manifest()}
    with pytest.raises(ValueError, match="differs"):
        Episode(cfg)
    e = Episode(config(tmp_path / "zero"))
    try:
        assert e.invoke("read_example", {}).isError
        assert not e.started
        assert not e.invoke("observe", {}).isError
    finally:
        e.close()


@pytest.mark.requires_icl
def test_icl_launcher_overlap_and_disable(tmp_path):
    spec = importlib.util.spec_from_file_location("native_launch", ROOT / "scripts/native-agents/launch.py")
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    base = ["codex", "--environment", "unreal-http", "--env-url", "http://127.0.0.1:19100",
            "--task", "S05", "--legacy-task-files", "--dry-run"]
    with pytest.raises(ValueError, match="ICL demonstration/alias"):
        launch.prepare(launch.cli_parser().parse_args(base))
    _, _, _, _, manifest = launch.prepare(launch.cli_parser().parse_args(
        base + ["--allow-icl-overlap", "--run-dir", str(tmp_path / "overlap")]))
    assert manifest["evaluation_eligible"] is False and manifest["icl"]["enabled"]
    _, _, _, prompt, manifest = launch.prepare(launch.cli_parser().parse_args(
        base + ["--no-icl", "--run-dir", str(tmp_path / "zero")]))
    assert manifest["icl"] == {"enabled": False} and "zero-shot" in prompt


@pytest.mark.requires_icl
def test_task_specific_icl_selection_unknown_and_conflicting_labels(tmp_path):
    from auditor.mcp_agent.examples import ExamplePack
    spec = importlib.util.spec_from_file_location("native_launch", ROOT / "scripts/native-agents/launch.py")
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    def args(task, *extra):
        return launch.cli_parser().parse_args(["codex", "--environment", "fake", "--task", task, *extra])
    assert launch.task_subcategory(args("S05")) == "C3"
    assert launch.task_subcategory(args("S01")) == "G1"
    with pytest.raises(ValueError, match="is G1"):
        launch.task_subcategory(args("S01", "--subcategory", "C3"))
    with pytest.raises(ValueError, match="No subcategory metadata"):
        launch.prepare(args("unknown-task"))
    assert launch.task_subcategory(args("unknown-task", "--subcategory", "V2")) == "V2"
    with pytest.raises(ValueError, match="No ICL example for subcategory S1"):
        launch.prepare(args("unknown-task", "--subcategory", "S1"))
    library = ExamplePack(ROOT / "examples/icl")
    for code in library.examples:
        selected = ExamplePack(library.root, code=code)
        assert list(selected.examples) == [code]
        assert selected.manifest()["example_count"] == 1
        assert 1 <= selected.manifest()["image_count"] <= 3


@pytest.mark.requires_icl
def test_scene_description_in_prompt_and_recalled_observation(tmp_path):
    spec = importlib.util.spec_from_file_location("native_launch", ROOT / "scripts/native-agents/launch.py")
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    manifests = []
    for client in ["codex", "gemini"]:
        args = launch.cli_parser().parse_args([
            client, "--environment", "unreal-http", "--env-url", "http://127.0.0.1:19100",
            "--task", "A09", "--legacy-task-files", "--dry-run", "--run-dir", str(tmp_path / client)])
        run, _, _, prompt, manifest = launch.prepare(args)
        scene = launch.scene_description(args)
        assert "ancient Chinese city" in scene and "wicker basket" in scene
        assert "Environment description:\n" + scene in prompt
        assert manifest["scene_description"] == scene
        manifests.append(manifest)
        # Verify recall without connecting to a real environment.
        cfg = json.loads((run / "episode-config.json").read_text())
        cfg["environment"] = "fake"
        e = Episode(cfg)
        try:
            assert not e.invoke("read_example", {}).isError
            assert scene in text(e.invoke("observe", {}))
            e.invoke("wait", {"seconds": .5})
            assert scene in text(e.invoke("observe", {}))
        finally:
            e.close()
    assert manifests[0]["protocol_sha256"] == manifests[1]["protocol_sha256"]
    args.task = "unknown-scene"
    args.no_icl = True
    with pytest.raises(ValueError, match="Missing environment description"):
        launch.prepare(args)
    args.scene_description_file = tmp_path / "scene.txt"
    args.scene_description_file.write_text("Public scene background only.")
    assert launch.scene_description(args) == "Public scene background only."


@pytest.mark.requires_icl
def test_gemini_credential_stays_in_child_environment(tmp_path):
    spec = importlib.util.spec_from_file_location("native_launch", ROOT / "scripts/native-agents/launch.py")
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    credential = tmp_path / "key"
    credential.write_text("synthetic-secret-for-test")
    args = launch.cli_parser().parse_args([
        "gemini", "--environment", "fake", "--task", "smoke", "--subcategory", "C3",
        "--gemini-auth", "gemini-api-key", "--gemini-thinking", "high",
        "--gemini-api-key-file", str(credential), "--run-dir", str(tmp_path / "run"), "--dry-run"])
    run, command, env, prompt, manifest = launch.prepare(args)
    assert env["GEMINI_API_KEY"] == "synthetic-secret-for-test"
    assert manifest["reasoning_requested"] == "high"
    for name in ["launch.json", "gemini-settings.json", "episode-config.json", "prompt.txt"]:
        assert "synthetic-secret-for-test" not in (run / name).read_text()
    assert "synthetic-secret-for-test" not in json.dumps(command)


@pytest.mark.requires_icl
def test_icl_restart_before_scene_does_not_reset_progress(tmp_path):
    from auditor.mcp_agent.examples import ExamplePack
    pack = ExamplePack(ROOT / "examples/icl", code="C3").snapshot(tmp_path / "icl")
    cfg = {**config(tmp_path), "subcategory": "C3", "icl_directory": str(pack.root), "icl": pack.manifest()}
    e = Episode(cfg)
    try:
        assert not e.invoke("read_example", {"code": "C3"}).isError
        assert not e.started and e.dispatch.n_actions == 0
        with pytest.raises(ValueError, match="already started"):
            Episode(cfg)
    finally:
        e.close()


def test_restart_does_not_reset_existing_episode(tmp_path):
    e = Episode(config(tmp_path))
    e.invoke("observe", {})
    e.close()
    previous = (tmp_path / "episode/meta.json").read_bytes()
    with pytest.raises(ValueError, match="already started"):
        Episode(config(tmp_path))
    assert (tmp_path / "episode/meta.json").read_bytes() == previous


def test_invalid_crop_and_numbers_do_not_advance(tmp_path):
    e = Episode(config(tmp_path))
    try:
        assert e.invoke("move", {"distance_m": float("nan"), "direction": "forward"}).isError
        assert e.dispatch.n_actions == 0
    finally:
        e.close()


def test_unreal_adapter_units_timestamps_and_fail_closed():
    from auditor.mcp_agent.unreal_http import UnrealHTTP
    from agent.types import ObsConfig, Action
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "blue").save(buffer, "PNG")
    rgb = {"base64": base64.b64encode(buffer.getvalue()).decode()}
    initial = {"paused": True, "task_id": "S05", "episode_id": "owned", "simulation_time": 10.0,
               "position_cm": [100, 200, 300], "yaw_degree": 30, "look_degree": 15, "rgb": rgb}
    calls = []
    class Response:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data
    class Session:
        def get(self, url, **kwargs):
            return Response({"engine_alive": True, "episode_started": False,
                             "task_id": "S05", "build_sha256": "test-build"})
        def post(self, url, json, **kwargs):
            calls.append((url, json))
            if url.endswith("/reset"): return Response(initial)
            if json["action"]["name"] == "done": return Response({"done": True})
            return Response({**initial, "simulation_time": 11.0, "actual_distance_cm": 100,
                             "boundary_clearance_cm": 0,
                             "frames": [{"simulation_time": 10.5, "rgb": rgb}]})
        def close(self): pass
    env = UnrealHTTP("http://localhost:9100")
    env.session = Session()
    obs = env.reset("S05", 0, ObsConfig(mode="film"))
    assert (obs.pose.x, obs.pose.y, obs.pose.z) == (1, 2, 3)
    assert "Task boundary reached" not in obs.events["env_note"]
    later = env.step(Action("move", {"distance_m": 1.25, "direction": "back"}))
    assert calls[-1][1]["action"] == {"name": "move_down", "distance": 125}
    assert later.frames[0].t_sim == .5 and later.sim_elapsed == 1
    assert "Task boundary reached" in later.events["env_note"]
    assert env.meta()["build_sha256"] == "test-build"
    env.close()
    assert calls[-1][1]["episode_id"] == "owned" and calls[-1][1]["action"]["name"] == "done"
    with pytest.raises(RuntimeError): env.step(Action("wait", {"seconds": .5}))


def test_full_budget_done_guard_and_native_completion_hook(tmp_path):
    spec = importlib.util.spec_from_file_location("after_agent", ROOT / "scripts/native-agents/after_agent.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    cfg = {**config(tmp_path), "require_full_budget": True}
    episode = Episode(cfg)
    try:
        assert episode.invoke("done", {"summary": "premature"}).isError
        assert not episode.dispatch.done
        result, state = hook.decide(cfg, {"actions_used": 0, "tool_calls": 1}, {})
        assert result["decision"] == "block" and "0/2" in result["reason"]
        for _ in range(3):
            result, state = hook.decide(cfg, {"actions_used": 0, "tool_calls": 1}, state)
        assert result["continue"] is False
        assert hook.decide(cfg, {"status": "backend_error"}, {})[0] == {}
        assert hook.decide(cfg, {"status": "completed"}, {})[0] == {}
        assert not episode.invoke("wait", {"seconds": .5}).isError
        assert episode.invoke("done", {"summary": "still premature"}).isError
        assert not episode.invoke("wait", {"seconds": .5}).isError
        result, _ = hook.decide(cfg, {"actions_used": 2, "tool_calls": 4}, {})
        assert "done now" in result["reason"]
        assert not episode.invoke("done", {"summary": "complete"}).isError
    finally:
        episode.close()
