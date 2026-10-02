"""Accounting tests: cached prompts, generated tokens, helpers and unknown usage."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("report", Path(__file__).resolve().parents[1] /
                                            "scripts/experiments/summarize_batch.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_cached_input_and_reasoning_are_not_double_charged():
    stats = {"models": {"gemini-3.8-flash": {
        "input_tokens": 1_000_000, "cached": 800_000,
        "output_tokens": 10_000, "total_tokens": 1_040_000}}}
    result = report.estimate_cost(stats)
    assert result["estimated_usd"] == pytest.approx(.15 + .06 + .15)
    assert result["breakdown"][0]["reasoning_or_other_tokens_inferred"] == 30_000


def test_auxiliary_model_has_its_own_rate():
    usage = {"input_tokens": 1_000_000, "cached": 0, "output_tokens": 0, "total_tokens": 1_000_000}
    cost = report.estimate_cost({"models": {"gemini-3.8-flash": usage, "gemini-3-flash-preview": usage}})
    assert cost["estimated_usd"] == 1.25


@pytest.mark.parametrize("stats", [{}, {"models": {"unknown": {}}},
    {"models": {"gemini-3.8-flash": {"input_tokens": 10, "cached": 20, "output_tokens": 0, "total_tokens": 10}}}])
def test_missing_or_invalid_usage_is_unknown_not_free(stats):
    assert report.estimate_cost(stats)["estimated_usd"] is None


def test_runtime_failure_is_separate_from_rubric_recall(tmp_path):
    tasks = [{"id": t, "family": "test", "subcategory": "G1"} for t in ["found", "missed", "failed", "pending"]]
    (tmp_path / "selection.json").write_text(json.dumps({"tasks": tasks, "parallelism": 4,
        "gpus": [2, 3, 2, 3], "model": "gemini-3.8-flash", "thinking_level": "medium", "max_actions": 40}))
    (tmp_path / "progress.json").write_text(json.dumps({"tasks": {
        t["id"]: {"status": "failed" if t["id"] == "failed" else "completed"} for t in tasks}}))
    (tmp_path / "grades.json").write_text(json.dumps({
        "found": {"target_found": True, "reason": "Matching target"},
        "missed": {"target_found": False, "reason": "Wrong object"},
        "failed": {"target_found": None, "evaluation_status": "run_failed", "reason": "CLI interrupted"}}))
    report.build(tmp_path)
    result = json.loads((tmp_path / "results.json").read_text())
    assert result["graded"] == 2 and result["target_found"] == 1
    assert result["recall_graded"] == .5
    assert result["runtime_failures"] == 1 and result["pending_grading"] == 1
    assert 'Run failed' in (tmp_path / "index.html").read_text()
    assert 'target_found,evaluation_status,grading_reason' in (tmp_path / "results.csv").read_text()
