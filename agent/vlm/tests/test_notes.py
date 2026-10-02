from agent.vlm.notes import Notes


def test_notes_empty_by_default_and_persist(tmp_path):
    n = Notes(tmp_path)
    assert n.read() == ""
    n.append("kitchen checked; sofa suspicious (a12)")
    assert n.read() == "kitchen checked; sofa suspicious (a12)"
    assert (tmp_path / "notes.md").read_text() == "kitchen checked; sofa suspicious (a12)"
    assert Notes(tmp_path).read() == "kitchen checked; sofa suspicious (a12)"


def test_append_adds_lines_and_write_replaces(tmp_path):
    n = Notes(tmp_path)
    n.append("a3: pot looks large")
    n.append("a7: recheck sofa")
    assert n.read() == "a3: pot looks large\na7: recheck sofa"
    assert n.count() == 2
    n.write("consolidated")
    assert n.read() == "consolidated"
    n.append("more")
    assert n.read() == "consolidated\nmore"


def test_append_ignores_blank_text(tmp_path):
    n = Notes(tmp_path)
    n.append("  ")
    assert n.read() == "" and n.count() == 0
