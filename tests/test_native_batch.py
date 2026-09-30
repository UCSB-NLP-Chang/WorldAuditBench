"""The coordinator must not replay excluded or previously attempted episodes."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "scripts/native-agents/run_batch.py"


def invoke(tmp_path, tasks, excluded=(), extra=()):
    batch = tmp_path / "batch"
    batch.mkdir(exist_ok=True)
    (batch / "selection.json").write_text(json.dumps({
        "tasks": [{"id": t, "subcategory": "G1"} for t in tasks],
        "excluded_task_ids": list(excluded), "gpus": [2, 3]}))
    key = tmp_path / "synthetic-key"
    key.write_text("synthetic test credential, never sent anywhere")
    return subprocess.run([sys.executable, str(RUNNER), "--batch", str(batch),
                           "--key-file", str(key), *extra], capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("tasks,excluded", [(["S01"], ["S01"]), (["A01", "A01"], [])])
def test_rejects_excluded_or_duplicate_tasks_before_launch(tmp_path, tasks, excluded):
    result = invoke(tmp_path, tasks, excluded)
    assert result.returncode != 0
    assert "Duplicate or explicitly excluded" in result.stderr
    assert not (tmp_path / "batch/batch.started").exists()


def test_resume_preserves_attempts_and_does_not_run_held_tasks(tmp_path):
    batch = tmp_path / "batch"
    (batch / "A01").mkdir(parents=True)
    (batch / "A01/evidence.txt").write_text("previous interrupted evidence")
    (batch / "batch.started").write_text("previous coordinator")
    result = invoke(tmp_path, ["A01", "U014"], extra=["--resume", "--hold-task", "U014"])
    assert result.returncode == 0, result.stderr
    state = json.loads((batch / "progress.json").read_text())["tasks"]
    assert state["A01"]["status"] == "interrupted"
    assert state["U014"]["status"] == "held_backend"
    assert (batch / "A01/evidence.txt").read_text() == "previous interrupted evidence"
    assert not (batch / "A01/environment.log").exists()
    assert not (batch / "U014").exists()
