"""Extract reported Codex usage without treating unavailable counters as zero."""
import json


def usage_from_events(text):
    turns = []
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            turns.append(event["usage"])
    fields = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
              "output_tokens", "reasoning_output_tokens")
    usage = {k: sum(t[k] for t in turns) if turns and all(type(t.get(k)) is int for t in turns) else None
             for k in fields}
    usage["total_tokens"] = (usage["input_tokens"] + usage["output_tokens"]
                             if usage["input_tokens"] is not None and usage["output_tokens"] is not None else None)
    return {"usage": usage, "completed_turns": len(turns),
            "usage_complete": bool(turns) and all(usage[k] is not None for k in ("input_tokens", "output_tokens")),
            "usage_source": "native Codex turn.completed events; cached tokens are included in input tokens"}
