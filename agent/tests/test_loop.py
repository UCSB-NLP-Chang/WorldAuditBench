import base64
import json

from agent.env.fake import FakeEnv
from agent.loop import LoopConfig, run_episode
from agent.tests.fake_llm import FakeLLM
from agent.types import ObsConfig

TASK = "Patrol the hall and report bugs."


def _run(tmp_path, script, env=None, **cfg):
    kw = dict(max_actions=90, max_calls=50, obs=ObsConfig(mode="final"), context_limit=10 ** 6)
    kw.update(cfg)
    llm = FakeLLM(script)
    result = run_episode(env or FakeEnv(), llm, TASK, "fake-config", 0, tmp_path, LoopConfig(**kw))
    return result, llm


def _rows(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _images(msg):
    return [p for p in msg["content"] if isinstance(msg["content"], list) and p["type"] == "image_url"]


def test_move_flag_done_episode_writes_logs_and_ledger(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "I expect an open hall.", "tools": [("move", {"distance_m": 2.0, "direction": "forward"})]},
        {"content": "Chair floats.", "tools": [("flag_bug", {"description": "chair floating", "category": "geometry",
                                                              "status": "suspect", "evidence": ["a1"]})]},
        {"content": "", "tools": [("done", {"summary": "one bug"})]},
    ])
    assert result["outcome"] == "done" and result["n_actions"] == 1 and result["n_calls"] == 3
    assert result["flags"][0]["note"] == "chair floating" and result["flags"][0]["evidence"] == ["a1"]
    acts = _rows(tmp_path / "actions.jsonl")
    assert acts[0]["index"] == 1 and acts[0]["action"] == {"kind": "move", "params": {"distance_m": 2.0, "direction": "forward"}}
    assert abs(acts[0]["moved"] - 2.0) < 1e-6 and acts[0]["content"] == "I expect an open hall."
    traj = _rows(tmp_path / "trajectory.jsonl")
    assert traj[0]["step"] == 1 and traj[0]["action"] == {"action": "forward", "dist": 2.0}
    assert (tmp_path / "frames" / "a001.jpg").exists() and (tmp_path / "transcript.jsonl").exists()
    calls = _rows(tmp_path / "calls.jsonl")
    assert len(calls) == 3 and calls[0]["tools"] == ["move"] and "prompt_tokens" in calls[0]
    # the first request carries system, then the task text and the a0 image in one user message
    first = llm.calls[0]["messages"]
    assert first[0]["role"] == "system" and first[1]["role"] == "user"
    assert TASK in first[1]["content"][0]["text"] and len(_images(first[1])) == 1
    # observation after the move: tool text then a user message with the final frame
    second = llm.calls[1]["messages"]
    assert second[-2]["role"] == "tool" and "a1 move forward 2.0m -> moved 2.00m" in second[-2]["content"]
    assert second[-1]["role"] == "user" and len(_images(second[-1])) == 1


def test_multiple_env_actions_in_one_reply_run_in_order_with_own_observations(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("turn", {"degrees": 90}), ("move", {"distance_m": 1.0, "direction": "forward"})]},
        {"content": "", "tools": [("done", {"summary": ""})]},
    ])
    assert result["n_actions"] == 2
    msgs = llm.calls[1]["messages"]
    roles = [m["role"] for m in msgs[-4:]]
    assert roles == ["tool", "user", "tool", "user"]
    assert "a1 turn" in msgs[-4]["content"] and "a2 move" in msgs[-2]["content"]
    acts = _rows(tmp_path / "actions.jsonl")
    assert [a["index"] for a in acts] == [1, 2] and acts[1]["pose"]["yaw"] == 90


def test_film_mode_puts_strip_plus_final_in_context_and_archives_all(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("wait", {"seconds": 3.0})]},
        {"content": "", "tools": [("done", {"summary": ""})]},
    ], obs=ObsConfig(mode="film", film_dt=0.5, film_max=8))
    obs_msg = llm.calls[1]["messages"][-1]
    assert len(_images(obs_msg)) == 8                     # 7 film + final
    texts = [p["text"] for p in obs_msg["content"] if p["type"] == "text"]
    assert any("a1.f0" in t and "t=+0.0s" in t for t in texts) and any(t.startswith("a1 ") for t in texts)
    idx = _rows(tmp_path / "frames" / "index.jsonl")
    assert [r["ref"] for r in idx if r["action"] == 1] == [f"a1.f{i}" for i in range(7)] + ["a1"]
    tool_text = llm.calls[1]["messages"][-2]["content"]
    assert "a1.f0..a1.f6" in tool_text and "sim +3.0s" in tool_text


def test_inspect_reinjects_the_archived_frame_bytes(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]},
        {"content": "", "tools": [("inspect", {"refs": ["a0", "a1"]})]},
        {"content": "", "tools": [("done", {"summary": ""})]},
    ])
    msgs = llm.calls[2]["messages"]
    assert msgs[-2]["role"] == "tool" and "2 frame" in msgs[-2]["content"]
    imgs = _images(msgs[-1])
    assert len(imgs) == 2
    got = base64.b64decode(imgs[1]["image_url"]["url"].split(",", 1)[1])
    assert got == (tmp_path / "frames" / "a001.jpg").read_bytes()
    assert result["tool_counts"]["inspect"] == 1


def test_inspect_unknown_ref_and_too_many_refs_return_errors_not_exceptions(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("inspect", {"refs": ["a9"]}), ("inspect", {"refs": ["a0"] * 5})]},
        {"content": "", "tools": [("done", {"summary": ""})]},
    ])
    msgs = llm.calls[1]["messages"]
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert tool_msgs[0]["content"].startswith("ERROR") and "a9" in tool_msgs[0]["content"]
    assert tool_msgs[1]["content"].startswith("ERROR")
    assert result["outcome"] == "done"


def test_blocked_move_is_reported_only_with_hint_on(tmp_path):
    script = [{"content": "", "tools": [("move", {"distance_m": 3.0, "direction": "forward"})]},
              {"content": "", "tools": [("done", {"summary": ""})]}]
    _, llm = _run(tmp_path / "hint", list(script), env=FakeEnv(wall_x=1.0), blocked_hint=True)
    txt = llm.calls[1]["messages"][-2]["content"]
    assert "moved 1.00m" in txt and "BLOCKED" in txt
    _, llm = _run(tmp_path / "nohint", list(script), env=FakeEnv(wall_x=1.0), blocked_hint=False)
    txt = llm.calls[1]["messages"][-2]["content"]
    assert "moved 1.00m" in txt and "BLOCKED" not in txt
    assert _rows(tmp_path / "nohint" / "trajectory.jsonl")[0]["blocked"] is True


def test_proprio_off_gives_only_frame_refs_no_action_echo_or_numbers(tmp_path):
    _, llm = _run(tmp_path, [{"content": "", "tools": [("move", {"distance_m": 2.0, "direction": "forward"})]},
                             {"content": "", "tools": [("done", {"summary": ""})]}], proprio=False,
                  env=FakeEnv(wall_x=1.0), blocked_hint=True)
    txt = llm.calls[1]["messages"][-2]["content"]
    assert txt == "a1 | frames: a1 (final)"                  # no action echo, no moved/pos, no BLOCKED
    first = llm.calls[0]["messages"][1]["content"][0]["text"]
    assert "pos" not in first and "yaw" not in first


def test_proprio_off_keeps_numbers_out_of_compaction_index_and_inspect_captions(tmp_path):
    mv = {"content": "walking", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
    script = [mv] * 5 + [{"content": "", "tools": [("inspect", {"refs": ["a1"]})]},
                         {"content": "", "tools": [("done", {"summary": ""})]}]
    result, llm = _run(tmp_path, script, obs=ObsConfig(mode="film", film_dt=0.1, film_max=8),
                       context_limit=6000, keep_recent=2, proprio=False, env=FakeEnv(wall_x=3.5))
    assert result["compactions"] >= 1
    note_calls = [c for c in llm.calls if c["tools"] is None]
    header = llm.calls[llm.calls.index(note_calls[0]) + 1]["messages"][1]["content"]
    assert "a1 move forward 1.0m" in header                    # what it did is kept
    for word in ("moved", "pos", "yaw", "BLOCKED"):
        assert word not in header
    last = llm.calls[-1]["messages"]
    cap = [p["text"] for p in last[-1]["content"] if p["type"] == "text"]
    assert any("a1" in c for c in cap) and not any("pos" in c or "yaw" in c for c in cap)
    # blocked is still recorded for analysis
    assert any(_rows(tmp_path / "trajectory.jsonl")[i]["blocked"] for i in range(5))


def test_action_budget_ends_episode_and_refuses_extra_actions(tmp_path):
    mv = ("move", {"distance_m": 1.0, "direction": "forward"})
    result, llm = _run(tmp_path, [{"content": "", "tools": [mv]}, {"content": "", "tools": [mv, mv]},
                                  {"content": "", "tools": [("done", {"summary": "x"})]}], max_actions=2)
    assert result["outcome"] == "budget" and result["n_actions"] == 2 and result["n_calls"] == 2
    tool_msgs = [m for m in llm.calls[1]["messages"] + [] if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    # the refused third move is visible in the transcript as an error tool result
    rows = _rows(tmp_path / "transcript.jsonl")
    errs = [r for r in rows if r.get("role") == "tool" and str(r.get("content", "")).startswith("ERROR")]
    assert errs and "budget" in errs[0]["content"]


def test_no_tool_call_gets_a_nudge_then_required_then_stops(tmp_path):
    result, llm = _run(tmp_path, [{"content": "Just thinking."}, {"content": "Still thinking."},
                                  {"content": "Nothing."}])
    assert result["outcome"] == "no_action" and result["n_calls"] == 3
    assert llm.calls[1]["tool_choice"] == "auto" and llm.calls[1]["messages"][-1]["role"] == "user"
    assert "tool" in llm.calls[1]["messages"][-1]["content"].lower()
    assert llm.calls[2]["tool_choice"] == "required"


def test_max_calls_is_a_hard_stop(tmp_path):
    result, _ = _run(tmp_path, [{"content": "", "tools": [("list_bugs", {})]}] * 10, max_calls=4)
    assert result["outcome"] == "max_calls" and result["n_calls"] == 4


def test_bug_lifecycle_through_tools(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("flag_bug", {"description": "floating chair", "category": "geometry", "status": "suspect"})]},
        {"content": "", "tools": [("update_bug", {"id": "b1", "status": "confirmed", "evidence": ["a0"]})]},
        {"content": "", "tools": [("update_bug", {"id": "b7", "status": "confirmed"})]},
        {"content": "", "tools": [("update_bug", {"id": "b1", "status": "retracted"}), ("list_bugs", {})]},
        {"content": "", "tools": [("done", {"summary": ""})]},
    ])
    tool_texts = [m["content"] for m in llm.calls[-1]["messages"] if m["role"] == "tool"]
    assert tool_texts[0].startswith("Recorded b1") and "suspect" in tool_texts[0]
    assert "confirmed" in tool_texts[1] and "a0" in tool_texts[1]
    assert tool_texts[2].startswith("ERROR") and "b7" in tool_texts[2]
    assert "no bugs" in tool_texts[4]
    assert result["flags"] == [] and len(result["bugs_history"]) == 3


def test_flag_evidence_must_reference_archived_frames(tmp_path):
    _, llm = _run(tmp_path, [
        {"content": "", "tools": [("flag_bug", {"description": "x", "category": "other", "status": "suspect",
                                                "evidence": ["a42"]})]},
        {"content": "", "tools": [("done", {"summary": ""})]},
    ])
    txt = [m["content"] for m in llm.calls[1]["messages"] if m["role"] == "tool"][0]
    assert txt.startswith("ERROR") and "a42" in txt


def test_write_notes_appends_entries(tmp_path):
    result, llm = _run(tmp_path, [
        {"content": "", "tools": [("write_notes", {"text": "a0: hall checked"}),
                                  ("write_notes", {"text": "a0: sofa odd, recheck"})]},
        {"content": "", "tools": [("done", {"summary": ""})]},
    ])
    texts = [m["content"] for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert "1 entr" in texts[0] and "2 entr" in texts[1]
    assert (tmp_path / "notes.md").read_text() == "a0: hall checked\na0: sofa odd, recheck"
    assert result["notes"] == "a0: hall checked\na0: sofa odd, recheck"


def test_env_actions_after_done_in_same_reply_are_refused(tmp_path):
    result, llm = _run(tmp_path, [{"content": "", "tools": [("done", {"summary": "bye"}),
                                                            ("move", {"distance_m": 1.0, "direction": "forward"})]}])
    assert result["outcome"] == "done" and result["n_actions"] == 0 and result["done_summary"] == "bye"


def test_compaction_rewrites_notes_and_rebuilds_context_with_index_and_ledger(tmp_path):
    mv = {"content": "walking on", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
    note = {"content": "", "tools": [("write_notes", {"text": "a1: east pot looks big"})]}
    script = [mv, note] + [mv] * 5 + [{"content": "", "tools": [("done", {"summary": ""})]}]
    result, llm = _run(tmp_path, script, obs=ObsConfig(mode="film", film_dt=0.1, film_max=8),
                       context_limit=6000, keep_recent=2)
    assert result["compactions"] >= 1
    # the note request: no tools; its prompt quotes the notes appended so far and asks for a rewrite
    note_calls = [c for c in llm.calls if c["tools"] is None]
    assert note_calls
    prompt = note_calls[0]["messages"][-1]["content"]
    assert "a1: east pot looks big" in prompt and "rewrite" in prompt.lower()
    # the model's reply replaced notes.md and is what the rebuilt header carries
    assert (tmp_path / "notes.md").read_text() == "NOTE: continuation note from the fake model."
    i = llm.calls.index(note_calls[0])
    after = llm.calls[i + 1]["messages"]
    assert after[0]["role"] == "system" and after[1]["role"] == "user" and after[2]["role"] == "assistant"
    header = after[1]["content"]
    assert "NOTE: continuation note" in header and TASK in header and "a1 move" in header
    assert "Bug ledger" in header and "Action index" in header and "Your notes" in header
    assert "a1: east pot looks big" not in header                     # superseded by the rewrite
    assert (tmp_path / "context" / "epoch_1.json").exists() and (tmp_path / "context" / "note_1.md").exists()
    calls = _rows(tmp_path / "calls.jsonl")
    assert any(c.get("kind") == "compaction" for c in calls)
    assert result["outcome"] == "done" and result["n_actions"] == 6


def test_history_returns_dropped_actions_text(tmp_path):
    script = [{"content": f"reason {i}", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
              for i in range(1, 5)]
    script += [{"content": "", "tools": [("history", {"from_action": 1, "to_action": 2})]},
               {"content": "", "tools": [("done", {"summary": ""})]}]
    result, llm = _run(tmp_path, script, obs=ObsConfig(mode="film", film_dt=0.1, film_max=8),
                       context_limit=5000, keep_recent=1)
    assert result["compactions"] >= 1
    txt = [m["content"] for m in llm.calls[-1]["messages"] if m["role"] == "tool"][-1]
    assert "a1" in txt and "a2" in txt and "reason 1" in txt and "reason 2" in txt and "a3" not in txt


def test_system_prompt_is_constant_across_calls_and_mentions_film_only_in_film_mode(tmp_path):
    _, llm_final = _run(tmp_path / "f", [{"content": "", "tools": [("done", {"summary": ""})]}],
                        obs=ObsConfig(mode="final"))
    _, llm_film = _run(tmp_path / "m", [{"content": "", "tools": [("wait", {"seconds": 1.0})]},
                                        {"content": "", "tools": [("done", {"summary": ""})]}],
                       obs=ObsConfig(mode="film"))
    assert llm_film.calls[0]["messages"][0]["content"] == llm_film.calls[1]["messages"][0]["content"]
    assert "film" in llm_film.calls[0]["messages"][0]["content"].lower()
    assert "film" not in llm_final.calls[0]["messages"][0]["content"].lower()
    _, llm_noexp = _run(tmp_path / "e", [{"content": "", "tools": [("done", {"summary": ""})]}], expect=False)
    assert "expect" in llm_film.calls[0]["messages"][0]["content"].lower()
    assert "expect to see" not in llm_noexp.calls[0]["messages"][0]["content"].lower()


def test_transcript_is_linear_with_call_numbers_and_no_duplicated_tail(tmp_path):
    mv = {"content": "walking on", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
    script = [mv] * 6 + [{"content": "", "tools": [("done", {"summary": ""})]}]
    result, llm = _run(tmp_path, script, obs=ObsConfig(mode="film", film_dt=0.1, film_max=8),
                       context_limit=6000, keep_recent=2)
    assert result["compactions"] == 1
    rows = _rows(tmp_path / "transcript.jsonl")
    assistants = [r for r in rows if r.get("role") == "assistant"]
    assert [r["call"] for r in assistants] == sorted(r["call"] for r in assistants)
    assert len(assistants) == 7                                     # each step call appears exactly once
    assert len({r["call"] for r in assistants}) == 7
    marks = [i for i, r in enumerate(rows) if r.get("event") == "compaction"]
    assert len(marks) == 1
    header = rows[marks[0] + 1]
    assert header["role"] == "user" and "Continuation #1" in header["content"]
    assert rows[marks[0] + 2]["role"] == "assistant"                # next row is new work, not the old tail
    assert sum(1 for r in rows if r.get("role") == "system") == 1


def test_calls_log_records_the_provider_when_known(tmp_path):
    result, llm = _run(tmp_path, [{"content": "", "tools": [("done", {"summary": ""})]}])
    row = _rows(tmp_path / "calls.jsonl")[0]
    assert "provider" in row and row["provider"] is None       # FakeLLM reports none


def test_rerun_into_the_same_directory_starts_from_a_clean_archive(tmp_path):
    mv = {"content": "", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]}
    _run(tmp_path, [mv, mv, {"content": "", "tools": [("done", {"summary": ""})]}])
    _run(tmp_path, [mv, {"content": "", "tools": [("done", {"summary": ""})]}])
    idx = _rows(tmp_path / "frames" / "index.jsonl")
    assert [r["ref"] for r in idx] == ["a0", "a1"]                # no stale a2 from the first attempt
    assert not (tmp_path / "frames" / "a002.jpg").exists()
    assert len(_rows(tmp_path / "calls.jsonl")) == 2


def test_calls_log_has_timestamps_and_rate_limit_fields(tmp_path):
    _run(tmp_path, [{"content": "", "tools": [("done", {"summary": ""})]}])
    row = _rows(tmp_path / "calls.jsonl")[0]
    assert row["t"] > 1.7e9 and row["rate_limited"] == 0 and row["rate_limit_wait_s"] == 0


def test_reasoning_is_logged_per_call_and_in_the_transcript(tmp_path):
    _, llm = _run(tmp_path, [{"content": "go", "reasoning": "let me think about the corridor",
                              "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]},
                             {"content": "", "tools": [("done", {"summary": ""})]}])
    row = _rows(tmp_path / "calls.jsonl")[0]
    assert row["reasoning_chars"] == len("let me think about the corridor")
    a = [r for r in _rows(tmp_path / "transcript.jsonl") if r.get("role") == "assistant"][0]
    assert a["reasoning_content"] == "let me think about the corridor"
    # what was re-sent to the model carries it too (FakeLLM keeps reasoning like preserve_thinking=on)
    assert llm.calls[1]["messages"][-3]["reasoning_content"] == "let me think about the corridor"


def test_inspect_with_region_archives_the_crop_the_model_saw(tmp_path):
    _, llm = _run(tmp_path, [
        {"content": "", "tools": [("move", {"distance_m": 1.0, "direction": "forward"})]},
        {"content": "", "tools": [("inspect", {"refs": ["a1"], "region": [0.1, 0.55, 0.45, 1.0]})]},
        {"content": "", "tools": [("inspect", {"refs": ["a1"], "region": [0.1, 0.55, 0.45, 1.0]}), ("inspect", {"refs": ["a1"]})]},
        {"content": "", "tools": [("done", {"summary": ""})]},
    ])
    imgs = [p for r in _rows(tmp_path / "transcript.jsonl") if isinstance(r.get("content"), list)
            for p in r["content"] if p["type"] == "image_ref"]
    assert [p["ref"] for p in imgs] == ["a0", "a1", "a1#c1", "a1#c1", "a1"]
    idx = {r["ref"]: r for r in _rows(tmp_path / "frames" / "index.jsonl")}
    assert idx["a1#c1"]["kind"] == "crop" and idx["a1#c1"]["region"] == [0.1, 0.55, 0.45, 1.0]
    # the bytes sent to the model are the archived crop
    sent = base64.b64decode(_images(llm.calls[2]["messages"][-1])[0]["image_url"]["url"].split(",", 1)[1])
    assert sent == (tmp_path / "frames" / idx["a1#c1"]["file"]).read_bytes()
