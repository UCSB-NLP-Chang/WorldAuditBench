"""End to end: the runner drives the real three.js page (env0-corridor) with a scripted model,
and the outputs feed the old evaluation tools (metrics, video)."""
import json
import os
from pathlib import Path

import pytest

from agent.tests.fake_llm import FakeLLM

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.chromium
if not (REPO / "assets" / "vendor" / "three" / "three.module.js").exists():
    pytest.skip("three.js vendor assets missing", allow_module_level=True)

SCRIPT = [
    {"content": "I expect a stone corridor ahead.", "tools": [("move", {"distance_m": 2.0, "direction": "forward"})]},
    {"content": "Let me look around.", "tools": [("turn", {"degrees": 90}), ("wait", {"seconds": 1.0})]},
    {"content": "Compare with the start.", "tools": [("inspect", {"refs": ["a0", "a2"]})]},
    {"content": "", "tools": [("flag_bug", {"description": "test flag", "category": "other", "status": "suspect",
                                            "evidence": ["a1"]})]},
    {"content": "", "tools": [("done", {"summary": "smoke"})]},
]


def test_runner_end_to_end_on_env0(tmp_path):
    from agent.env.threejs import ThreeJSEnv
    from agent.runner import EpisodeSpec, run_one
    from harness.tasks import TASKS
    TASKS["audit_e2e_env0"] = dict(config="env0-corridor", kind="audit", zone="zone_tc", steps=10,
                                   instr="Inspect the corridor.")
    try:
        spec = EpisodeSpec(task="audit_e2e_env0", seed=1, run_dir=tmp_path / "ep", obs="film", film_dt=0.5,
                           film_max=8, env="threejs", gpu=os.environ.get("AGENT_TEST_GPU", "swiftshader"),
                           video=True)
        meta = run_one(spec, env_factory=lambda s: ThreeJSEnv(gpu=s.gpu), llm_factory=lambda s: FakeLLM(list(SCRIPT)))
    finally:
        TASKS.pop("audit_e2e_env0", None)
    assert meta["outcome"] == "done" and meta["steps_used"] == 3 and meta["renderer"]
    assert meta["flags"][0]["note"] == "test flag" and meta["flags"][0]["evidence"] == ["a1"]
    assert meta["page_errors"] == []
    idx = [json.loads(l) for l in (tmp_path / "ep" / "frames" / "index.jsonl").read_text().splitlines()]
    assert [r["ref"] for r in idx if r["action"] == 3][-1] == "a3"
    assert any(r["kind"] == "film" and r["w"] == 960 for r in idx)        # film archived at capture resolution
    assert (tmp_path / "ep" / "video.mp4").exists()
    from eval.metrics import episode_metrics, load_episode
    steps, m = load_episode(tmp_path / "ep")
    assert episode_metrics(steps, m)["steps"] == 3
