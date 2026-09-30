"""Provider quirks: thinking models that exhaust max_tokens before emitting a tool call, and
providers that reject tool_choice="required"."""
import json

from agent.env.fake import FakeEnv
from agent.loop import LoopConfig, run_episode
from agent.tests.fake_llm import FakeLLM
from agent.types import ObsConfig

MV = {"content": "walk", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
DONE = {"content": "", "tools": [("done", {"summary": ""})]}
TRUNC = {"content": "", "finish": "length"}          # reasoning ate the whole output budget


def _run(tmp_path, llm, **kw):
    cfg = dict(max_actions=20, max_calls=30, obs=ObsConfig(mode="final"), context_limit=10 ** 6, max_tokens=600)
    cfg.update(kw)
    return run_episode(FakeEnv(), llm, "task", "fake", 0, tmp_path, LoopConfig(**cfg))


def test_truncated_empty_reply_is_retried_with_more_tokens_not_appended(tmp_path):
    llm = FakeLLM([TRUNC, MV, DONE])
    result = _run(tmp_path, llm)
    assert result["outcome"] == "done" and result["n_actions"] == 1
    assert llm.calls[0]["max_tokens"] == 600 and llm.calls[1]["max_tokens"] > 600
    assert len(llm.calls[1]["messages"]) == len(llm.calls[0]["messages"])   # nothing appended in between
    assert llm.calls[1]["tool_choice"] == "auto"
    kinds = [json.loads(l) for l in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert kinds[0]["finish_reason"] == "length" and kinds[0]["kind"] == "step"


def test_repeated_truncation_eventually_counts_as_no_action(tmp_path):
    llm = FakeLLM([TRUNC] * 10)
    result = _run(tmp_path, llm, max_calls=12)
    assert result["outcome"] in ("no_action", "max_calls")
    assert max(c["max_tokens"] for c in llm.calls) <= 600 * 4                  # growth is capped


def test_required_rejection_falls_back_to_auto_and_disables_required(tmp_path):
    llm = FakeLLM([{"content": "hmm"}, {"content": "hmm again"}, MV, {"content": "x"}, {"content": "y"}, DONE],
                  reject_required=True)
    result = _run(tmp_path, llm)
    assert result["outcome"] == "done" and result["n_actions"] == 1
    choices = [c["tool_choice"] for c in llm.calls]
    assert choices.count("required") == 1                 # tried once, then never again this episode
    assert choices[-1] == "auto"
