from agent.tools import tool_schemas


def _names(schemas):
    return [s["function"]["name"] for s in schemas]


def test_schemas_follow_capabilities_and_enabled_groups():
    names = _names(tool_schemas(frozenset({"move", "turn"}), {"memory", "bugs", "notes"}))
    assert "move" in names and "turn" in names and "done" in names
    assert "look" not in names and "interact" not in names and "wait" not in names
    assert {"inspect", "history", "flag_bug", "update_bug", "list_bugs", "write_notes"} <= set(names)
    assert "read_notes" not in names


def test_disabling_groups_removes_their_tools():
    names = _names(tool_schemas(frozenset({"move"}), set()))
    assert names == ["move", "done"]
    names = _names(tool_schemas(frozenset({"move"}), {"bugs"}))
    assert "flag_bug" in names and "inspect" not in names and "write_notes" not in names


def test_every_schema_is_openai_shaped():
    for s in tool_schemas(frozenset({"move", "turn", "look", "interact", "wait"}), {"memory", "bugs", "notes"}):
        assert s["type"] == "function"
        f = s["function"]
        assert f["name"] and f["description"] and f["parameters"]["type"] == "object"


def test_limits_override_schema_bounds_for_tick_mode():
    schemas = {s["function"]["name"]: s for s in tool_schemas(
        frozenset({"move", "turn", "look", "wait"}), set(), limits={"move": 2.34, "turn": 60, "look": 60, "wait": 0.5})}
    assert schemas["move"]["function"]["parameters"]["properties"]["distance_m"]["maximum"] == 2.34
    assert schemas["turn"]["function"]["parameters"]["properties"]["degrees"]["maximum"] == 60
    assert schemas["turn"]["function"]["parameters"]["properties"]["degrees"]["minimum"] == -60
    w = schemas["wait"]["function"]["parameters"]["properties"]["seconds"]
    assert w["maximum"] == 0.5 and w["minimum"] == 0.5
