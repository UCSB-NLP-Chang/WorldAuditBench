"""Live smoke against a running vLLM server (skipped unless VLM_BASE_URL and VLM_MODEL are set):
the real model must drive the fake environment through tool calls, and the server must report
prefix-cache hits on the second call.

    VLM_BASE_URL=http://localhost:8010/v1 VLM_MODEL=Qwen/Qwen3-VL-8B-Instruct \
        .venv/bin/pytest -q agent/tests/test_live.py -m live -s
"""
import json
import os

import pytest

from agent.env.fake import FakeEnv
from agent.llm import LLMClient
from agent.loop import LoopConfig, run_episode
from agent.types import ObsConfig

pytestmark = pytest.mark.live
if not (os.environ.get("VLM_BASE_URL") and os.environ.get("VLM_MODEL")):
    pytest.skip("VLM_BASE_URL / VLM_MODEL not set", allow_module_level=True)


def test_model_drives_fake_env_with_tool_calls_and_cache_hits(tmp_path):
    llm = LLMClient(temperature=0.2)
    result = run_episode(FakeEnv(wall_x=3.0), llm,
                         "Walk forward a few metres, look around once, then finish with done.",
                         "fake", 0, tmp_path, LoopConfig(max_actions=4, max_calls=10, obs=ObsConfig(mode="film")))
    calls = [json.loads(l) for l in (tmp_path / "calls.jsonl").read_text().splitlines()]
    print(json.dumps({k: result[k] for k in ("outcome", "n_actions", "n_calls", "tool_counts", "usage")}, indent=1))
    for c in calls:
        print(f"call {c['call']:2d} {c['kind']:10s} tools={c['tools']} prompt={c['prompt_tokens']} "
              f"cached={c['cached_tokens']} predicted={c['predicted_prompt']} drift={c['drift']}")
    assert result["n_actions"] >= 1, "the model never called an environment action"
    assert result["outcome"] in ("done", "budget")
    if len(calls) >= 2:
        assert calls[1]["cached_tokens"] > 0, "no prefix-cache hit on the second call (check server flags)"
    drift = max(abs(c["drift"]) / max(c["prompt_tokens"], 1) for c in calls)
    assert drift < 0.1, f"token prediction drift {drift:.2%} - recalibrate image_tokens/text_tokens"
