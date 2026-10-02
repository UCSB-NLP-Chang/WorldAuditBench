import json
import subprocess
from pathlib import Path

from judge.codex_metrics import usage_from_events
from judge import judge


def test_sum_turns_preserves_missing_and_does_not_double_count_cache():
    raw = "noise\n" + "\n".join(json.dumps({"type": "turn.completed", "usage": u}) for u in [
        {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10},
        {"input_tokens": 200, "cached_input_tokens": 160, "output_tokens": 20}])
    m = usage_from_events(raw)
    assert m["usage_complete"] and m["completed_turns"] == 2
    assert m["usage"]["total_tokens"] == 330
    assert m["usage"]["cached_input_tokens"] == 240
    assert m["usage"]["reasoning_output_tokens"] is None
    assert usage_from_events("")["usage"]["input_tokens"] is None
    assert not usage_from_events("")["usage_complete"]


def test_judge_persists_raw_usage_and_keeps_score_contract(tmp_path, monkeypatch):
    raw = json.dumps({"type": "turn.completed", "usage": {"input_tokens": 99, "output_tokens": 7}}) + "\n"
    monkeypatch.setattr(judge.shutil, "which", lambda _: "/experiment/bin/codex")

    def run(command, **kwargs):
        Path(command[command.index("--output-last-message") + 1]).write_text('{"score":1,"reason":"matches"}')
        return subprocess.CompletedProcess(command, 0, raw, "diagnostic")

    monkeypatch.setattr(judge.subprocess, "run", run)
    result = judge.judge("rubric", "report", metrics_dir=tmp_path)
    assert result == {"score": 1, "reason": "matches"}
    assert (tmp_path / "judge-native-events.jsonl").read_text() == raw
    m = json.loads((tmp_path / "judge-metrics.json").read_text())
    assert m["usage"]["total_tokens"] == 106 and m["usage_complete"]
    assert m["model"] == "gpt-6-astra" and m["reasoning_effort"] == "medium"
    assert m["codex_binary"] == "/experiment/bin/codex" and m["wall_s"] >= 0
    assert m["cost_usd"] is None
