"""Fixed-tick decision mode: every decision that acts advances exactly `tick` simulated seconds."""
import json

import pytest

from agent.vlm.env.fake import FakeEnv
from agent.vlm.loop import LoopConfig, run_episode
from agent.vlm.tests.fake_llm import FakeLLM
from agent.vlm.types import ObsConfig

DONE = {"content": "", "tools": [("done", {"summary": ""})]}


def _run(tmp_path, script, **kw):
    cfg = dict(decision="tick", tick=0.5, obs=ObsConfig(mode="final"), context_limit=10 ** 6,
               max_actions=100, max_calls=40)
    cfg.update(kw)
    llm = FakeLLM(script)
    return run_episode(FakeEnv(), llm, "task", "fake", 0, tmp_path, LoopConfig(**cfg)), llm


def _rows(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _tool_texts(llm, i):
    return [m["content"] for m in llm.calls[i]["messages"] if m["role"] == "tool"]


def test_single_move_is_clamped_to_the_tick_and_held_to_its_end(tmp_path):
    result, llm = _run(tmp_path, [{"content": "", "tools": [("move", {"distance_m": 4.0, "direction": "forward"})]}, DONE])
    txt = _tool_texts(llm, 1)[0]
    assert "move forward 2.3m" in txt and "moved 2.34m" in txt and "sim +0.5s" in txt
    acts = _rows(tmp_path / "actions.jsonl")
    assert acts[0]["sim_elapsed"] == 0.5 and acts[0]["action"]["params"]["hold_sec"] == 0.5
    assert result["sim_t"] == 0.5


def test_actions_share_one_tick_and_the_overflow_is_refused(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("turn", {"degrees": 90}), ("move", {"distance_m": 4.0, "direction": "forward"})]},
        DONE])
    t = _tool_texts(llm, 1)
    assert "turn 60 deg" in t[0] and "sim +0.5s" in t[0]                # clamped to 120 deg/s x 0.5 s
    assert t[1].startswith("ERROR") and "tick" in t[1]                    # nothing left in this tick
    assert result["n_actions"] == 1 and result["sim_t"] == 0.5


def test_short_actions_split_the_tick_and_the_last_one_holds(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("turn", {"degrees": 30}), ("move", {"distance_m": 4.0, "direction": "forward"})]},
        DONE])
    t = _tool_texts(llm, 1)
    assert "sim +0.2s" in t[0] or "sim +0.3s" in t[0]                     # 30 deg = 0.25 s
    assert "moved 1.17m" in t[1] and "sim +0.2s" in t[1] or "sim +0.3s" in t[1]
    acts = _rows(tmp_path / "actions.jsonl")
    assert abs(sum(a["sim_elapsed"] for a in acts) - 0.5) < 1e-6
    assert result["sim_t"] == 0.5


def test_wait_and_interact_last_one_tick_and_memory_tools_take_no_time(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("wait", {"seconds": 5.0})]},
        {"content": "", "tools": [("inspect", {"refs": ["a0"]}), ("list_bugs", {})]},
        {"content": "", "tools": [("interact", {})]},
        DONE])
    assert "sim +0.5s" in _tool_texts(llm, 1)[0]
    acts = _rows(tmp_path / "actions.jsonl")
    assert [a["sim_elapsed"] for a in acts] == [0.5, 0.5] and result["sim_t"] == 1.0


def test_sim_time_budget_ends_the_episode(tmp_path):
    mv = {"content": "", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
    result, llm = _run(tmp_path, [mv] * 5 + [DONE], max_sim_seconds=1.0)
    assert result["outcome"] == "budget" and result["n_actions"] == 2 and result["sim_t"] == 1.0
    assert "Time budget: 1 simulated second" in llm.calls[0]["messages"][1]["content"][0]["text"]


def test_sim_time_budget_also_applies_in_macro_mode(tmp_path):
    w = {"content": "", "tools": [("wait", {"seconds": 5.0})]}
    result, _ = _run(tmp_path, [w] * 3 + [DONE], decision="macro", max_sim_seconds=8.0)
    assert result["outcome"] == "budget" and result["n_actions"] == 2


def test_tick_mode_prompt_and_schema_describe_the_tick(tmp_path):
    _, llm = _run(tmp_path, [DONE])
    system = llm.calls[0]["messages"][0]["content"]
    assert "0.5" in system and "tick" in system.lower()
    tools = {t["function"]["name"]: t for t in llm.calls[0]["tools"]}
    assert tools["move"]["function"]["parameters"]["properties"]["distance_m"]["maximum"] == 2.34
    assert tools["turn"]["function"]["parameters"]["properties"]["degrees"]["maximum"] == 60


def test_tick_with_film_is_rejected():
    with pytest.raises(ValueError):
        LoopConfig(decision="tick", obs=ObsConfig(mode="film"))
    with pytest.raises(ValueError):
        LoopConfig(decision="stepwise")


def test_clamped_action_tells_the_model_it_was_partial_and_it_may_continue(tmp_path):
    _, llm = _run(tmp_path, [{"content": "", "tools": [("move", {"distance_m": 4.0, "direction": "forward"})]},
                             {"content": "", "tools": [("turn", {"degrees": 180})]},
                             {"content": "", "tools": [("wait", {"seconds": 5.0})]},
                             {"content": "", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]},
                             DONE])
    t1, t2, t3, t4 = (_tool_texts(llm, i)[-1] for i in (1, 2, 3, 4))      # latest tool result per request
    assert "[tick limit" in t1 and "4.0 m" in t1 and "2.34 m" in t1 and "continue" in t1
    assert "[tick limit" in t2 and "180" in t2 and "60" in t2
    assert "[tick limit" in t3 and "5.0 s" in t3 and "0.5 s" in t3
    assert "[tick limit" not in t4                                        # fits: no note


def test_clamp_note_is_given_without_proprio_but_without_displacement(tmp_path):
    _, llm = _run(tmp_path, [{"content": "", "tools": [("move", {"distance_m": 4.0, "direction": "forward"})]}, DONE],
                  proprio=False)
    t = _tool_texts(llm, 1)[0]
    assert t.startswith("a1 | frames:") and "[tick limit" in t and "4.0 m" in t and "2.34 m" in t
    assert "moved" not in t and "pos" not in t
