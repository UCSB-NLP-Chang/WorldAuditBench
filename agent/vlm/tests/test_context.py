import json

from agent.vlm.context import Conversation, estimate_tokens, image_tokens, message_tokens, text_tokens

SYSTEM = "You are a QA tester."


def _img(w, h, tag="x"):
    """A small real data URL of the requested size (the estimator reads the JPEG header)."""
    import base64
    from agent.vlm.tests.helpers import jpeg_bytes
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes(w, h, text=tag)).decode()


def _dump(msgs):
    return [json.dumps(m, sort_keys=True) for m in msgs]


def test_image_and_text_token_estimates():
    assert image_tokens(960, 576) == 30 * 18 + 2
    assert image_tokens(480, 288) == 15 * 9 + 2
    assert image_tokens(960, 600) == 30 * 19 + 2          # 600 rounds to 608
    assert text_tokens("") == 1 and text_tokens("a" * 400) == 101


def test_estimate_counts_text_and_images_in_parts():
    msgs = [{"role": "system", "content": "a" * 40},
            {"role": "user", "content": [{"type": "text", "text": "b" * 40},
                                         {"type": "image_url", "image_url": {"url": _img(480, 288)}}]}]
    est = estimate_tokens(msgs)
    assert est == text_tokens("a" * 40) + text_tokens("b" * 40) + image_tokens(480, 288) + 2 * 4


def test_snapshots_are_strict_prefixes_within_an_epoch():
    c = Conversation(SYSTEM, context_limit=10 ** 6, keep_recent=2)
    c.append_user_text("TASK: patrol")
    snaps = [_dump(c.snapshot())]
    c.append_assistant({"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "move", "arguments": "{}"}}]})
    c.mark_action(1)
    c.append_tool("c1", "a1 move -> moved 1.5m")
    c.append_user_images("[observation a1]", [("final", _img(64, 64), "a1")])
    snaps.append(_dump(c.snapshot()))
    c.append_assistant({"role": "assistant", "content": "done thinking"})
    snaps.append(_dump(c.snapshot()))
    for a, b in zip(snaps, snaps[1:]):
        assert b[:len(a)] == a and len(b) > len(a)
    assert c.snapshot() is not c.messages                # a copy, safe to hand out


def test_predicted_next_uses_recorded_usage_plus_appended_delta():
    c = Conversation(SYSTEM, context_limit=1000, keep_recent=2)
    c.append_user_text("x" * 400)
    assert c.predicted_next() == estimate_tokens(c.messages)
    a = {"role": "assistant", "content": "y" * 40}
    c.append_assistant(a)
    c.record_usage(prompt_tokens=700, completion_tokens=900)     # 900 = mostly hidden reasoning, never re-sent
    assert c.predicted_next() == 700 + message_tokens(a)         # the visible reply is estimated, not the completion
    c.append_tool("c1", "z" * 40)
    assert c.predicted_next() == 700 + message_tokens(a) + text_tokens("z" * 40) + 4
    assert not c.needs_compaction()
    c.append_user_images("[observation a1]", [("final", _img(960, 576), "a1")])
    assert c.needs_compaction()


def _episode(c, n_actions, start=1):
    """Append env actions start..start+n-1, each = assistant(tool call) + tool text + image user msg."""
    for a in range(start, start + n_actions):
        c.append_assistant({"role": "assistant", "content": f"step {a}", "tool_calls": [
            {"id": f"c{a}", "type": "function", "function": {"name": "move", "arguments": "{}"}}]})
        c.mark_action(a)
        c.append_tool(f"c{a}", f"a{a} move -> moved 1.0m")
        c.append_user_images(f"[observation a{a}]", [("final", _img(64, 64, f"a{a}"), f"a{a}")])


def test_compaction_rebuilds_header_plus_verbatim_tail():
    c = Conversation(SYSTEM, context_limit=10 ** 6, keep_recent=2)
    c.append_user_text("TASK: patrol")
    _episode(c, 5)
    tail_expected = c.messages[c.messages.index(next(m for m in c.messages if m.get("content") == "step 4")):]
    c.begin_compaction("Write a continuation note.")
    assert c.messages[-1]["content"] == "Write a continuation note."
    old = c.finish_compaction("HEADER with note")
    assert old[-1]["content"] == "Write a continuation note."     # archived epoch includes the prompt
    assert c.messages[0] == {"role": "system", "content": SYSTEM}
    assert c.messages[1] == {"role": "user", "content": "HEADER with note"}
    assert c.messages[2:] == tail_expected                          # actions 4 and 5 verbatim
    assert c.messages[2]["role"] == "assistant"
    assert c.compactions == 1
    assert c.predicted_next() == estimate_tokens(c.messages)        # accounting re-based


def test_second_compaction_slices_by_remapped_action_indices():
    c = Conversation(SYSTEM, context_limit=10 ** 6, keep_recent=1)
    c.append_user_text("TASK")
    _episode(c, 3)
    c.begin_compaction("note?")
    c.finish_compaction("H1")
    _episode(c, 2, start=4)                                         # actions 4, 5 appended after rebuild
    c.begin_compaction("note?")
    c.finish_compaction("H2")
    assert c.messages[2]["content"] == "step 5"                     # only the last action kept
    assert c.messages[2]["tool_calls"][0]["id"] == "c5"


def test_compaction_before_any_action_keeps_nothing_but_header():
    c = Conversation(SYSTEM, context_limit=10 ** 6, keep_recent=3)
    c.append_user_text("TASK")
    c.append_assistant({"role": "assistant", "content": "thinking only"})
    c.begin_compaction("note?")
    c.finish_compaction("H")
    assert [m["role"] for m in c.messages] == ["system", "user"]


def test_transcript_rows_replace_image_urls_with_refs():
    c = Conversation(SYSTEM, context_limit=10 ** 6, keep_recent=2)
    c.append_user_images("[observation a1]", [("t=+0.0s", _img(64, 64), "a1.f0"), ("final", _img(64, 64), "a1")])
    row = c.transcript_row(c.messages[-1])
    imgs = [p for p in row["content"] if p["type"] == "image_ref"]
    assert [p["ref"] for p in imgs] == ["a1.f0", "a1"]
    assert "base64" not in json.dumps(row)


def test_extra_tokens_are_part_of_the_prediction_until_usage_is_measured():
    c = Conversation(SYSTEM, context_limit=10 ** 6, keep_recent=2, extra_tokens=1200)
    c.append_user_text("TASK")
    assert c.predicted_next() == estimate_tokens(c.messages) + 1200
    a = {"role": "assistant", "content": "ok"}
    c.append_assistant(a)
    c.record_usage(prompt_tokens=3000, completion_tokens=5)
    assert c.predicted_next() == 3000 + message_tokens(a)            # measured usage already includes the tools
    c.begin_compaction("note?")
    c.finish_compaction("H")
    assert c.predicted_next() == estimate_tokens(c.messages) + 1200  # re-based estimate counts them again


def test_reasoning_content_counts_toward_the_prompt_and_private_reasoning_reaches_the_transcript():
    kept = {"role": "assistant", "content": "ok", "reasoning_content": "x" * 400}
    assert message_tokens(kept) == message_tokens({"role": "assistant", "content": "ok"}) + text_tokens("x" * 400)
    c = Conversation(SYSTEM, context_limit=10 ** 6)
    c.append_assistant({"role": "assistant", "content": "ok", "_reasoning": "hidden thought"}, call=3)
    assert "_reasoning" not in c.snapshot()[-1] and "reasoning_content" not in c.snapshot()[-1]
    row = c.transcript_row(c.messages[-1])
    assert row["reasoning_content"] == "hidden thought" and row["call"] == 3
