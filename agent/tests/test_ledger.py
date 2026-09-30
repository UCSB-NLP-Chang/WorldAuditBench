import json

import pytest

from agent.ledger import BugLedger
from agent.tests.helpers import pose


def test_flag_returns_sequential_ids_and_records_position(tmp_path):
    lg = BugLedger(tmp_path)
    b1 = lg.flag("chair floating above floor", "geometry", "suspect", ["a3"], pose(x=1.2, y=-0.3), 3, 4.5)
    b2 = lg.flag("invisible wall in hall", "collision", "confirmed", [], pose(x=2.0), 7, 9.0)
    assert (b1, b2) == ("b1", "b2")
    e = lg.get("b1")
    assert e["status"] == "suspect" and e["category"] == "geometry" and e["evidence"] == ["a3"]
    assert e["pos"] == [1.2, 1.7, -0.3]            # env-native position from pose.raw
    assert e["action"] == 3 and e["simT"] == 4.5


def test_update_changes_fields_and_retract_removes_from_active(tmp_path):
    lg = BugLedger(tmp_path)
    lg.flag("maybe floating", "geometry", "suspect", [], pose(), 1, 1.0)
    lg.update("b1", status="confirmed", description="chair floating 30cm", evidence=["a1", "a4"])
    assert lg.get("b1")["status"] == "confirmed"
    assert lg.get("b1")["description"] == "chair floating 30cm"
    assert [e["id"] for e in lg.active()] == ["b1"]
    lg.update("b1", status="retracted")
    assert lg.active() == []


def test_update_after_retract_is_rejected(tmp_path):
    lg = BugLedger(tmp_path)
    lg.flag("x", "other", "suspect", [], pose(), 1, 1.0)
    lg.update("b1", status="retracted")
    with pytest.raises(ValueError):
        lg.update("b1", status="confirmed")


def test_invalid_category_status_and_id_are_rejected(tmp_path):
    lg = BugLedger(tmp_path)
    with pytest.raises(ValueError):
        lg.flag("x", "weird", "suspect", [], pose(), 1, 1.0)
    with pytest.raises(ValueError):
        lg.flag("x", "other", "maybe", [], pose(), 1, 1.0)
    with pytest.raises(KeyError):
        lg.update("b9", status="confirmed")


def test_events_are_logged_to_bugs_jsonl(tmp_path):
    lg = BugLedger(tmp_path)
    lg.flag("x", "other", "suspect", [], pose(), 1, 1.0)
    lg.update("b1", status="confirmed")
    lg.update("b1", status="retracted")
    rows = [json.loads(l) for l in (tmp_path / "bugs.jsonl").read_text().splitlines()]
    assert [r["event"] for r in rows] == ["flag", "update", "update"]
    assert rows[-1]["status"] == "retracted"
    assert len(lg.history()) == 3


def test_export_matches_scoring_shape_and_skips_retracted(tmp_path):
    lg = BugLedger(tmp_path)
    lg.flag("floating chair", "geometry", "suspect", ["a2"], pose(x=1.0, y=2.0), 2, 3.0)
    lg.flag("wrong", "other", "suspect", [], pose(), 4, 5.0)
    lg.update("b2", status="retracted")
    out = lg.export()
    assert len(out) == 1
    f = out[0]
    assert f["note"] == "floating chair" and f["pos"] == [1.0, 1.7, 2.0] and f["simT"] == 3.0
    assert f["id"] == "b1" and f["status"] == "suspect" and f["evidence"] == ["a2"]


def test_render_lists_active_bugs_with_status(tmp_path):
    lg = BugLedger(tmp_path)
    assert "no bugs" in lg.render()
    lg.flag("floating chair", "geometry", "suspect", ["a2"], pose(), 2, 3.0)
    txt = lg.render()
    assert "b1" in txt and "suspect" in txt and "floating chair" in txt and "a2" in txt
