"""Cache-oriented loop properties: requests are strict prefixes within an epoch, and a tiny
limit cannot trap the loop in back-to-back compactions."""
import json

from agent.vlm.env.fake import FakeEnv
from agent.vlm.loop import LoopConfig, run_episode
from agent.vlm.tests.fake_llm import FakeLLM
from agent.vlm.types import ObsConfig

MV = {"content": "walk", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
DONE = {"content": "", "tools": [("done", {"summary": ""})]}


def _dump(msgs):
    return [json.dumps(m, sort_keys=True) for m in msgs]


def test_requests_are_strict_prefixes_within_each_epoch(tmp_path):
    llm = FakeLLM([MV] * 8 + [DONE])
    run_episode(FakeEnv(), llm, "task", "fake", 0, tmp_path,
                LoopConfig(obs=ObsConfig(mode="film", film_dt=0.1), context_limit=7000, keep_recent=2))
    epochs, cur = [], []
    for c in llm.calls:
        msgs = _dump(c["messages"])
        if cur and msgs[:len(cur[-1])] != cur[-1]:        # prefix broke: a compaction rebuilt the context
            epochs.append(cur)
            cur = []
        cur.append(msgs)
    epochs.append(cur)
    assert len(epochs) >= 2                                # at least one compaction happened
    for ep in epochs:
        for a, b in zip(ep, ep[1:]):
            assert b[:len(a)] == a and len(b) > len(a)
    # the system prompt is byte-identical in every request
    assert len({c["messages"][0]["content"] for c in llm.calls}) == 1


def test_tiny_limit_does_not_loop_on_compaction(tmp_path):
    llm = FakeLLM([MV] * 4 + [DONE])
    result = run_episode(FakeEnv(), llm, "task", "fake", 0, tmp_path,
                         LoopConfig(obs=ObsConfig(mode="final"), context_limit=300, keep_recent=3, max_calls=40))
    assert result["outcome"] == "done" and result["n_actions"] == 4
    kinds = [json.loads(l)["kind"] for l in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert not any(a == b == "compaction" for a, b in zip(kinds, kinds[1:]))   # never twice in a row
