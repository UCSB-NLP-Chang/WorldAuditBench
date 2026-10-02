"""Scripted stand-in for LLMClient: replays a list of replies, records every request."""
import json

from agent.vlm.context import estimate_tokens, text_tokens


class FakeLLM:
    model = "fake-vlm"

    def __init__(self, script, reject_required=False):
        """script items: {"content": str, "tools": [(name, args), ...], "finish": str?} or a callable
        (messages, tools) -> item. A compaction request (tools=None) that meets a tool-call
        item returns a generic note without consuming the script. reject_required=True mimics a
        provider that answers tool_choice="required" with an HTTP 400."""
        self.script = list(script)
        self.reject_required = reject_required
        self.calls = []
        self.total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "calls": 0}
        self._n = 0

    def chat(self, messages, tools=None, tool_choice="auto", max_tokens=None, temperature=None):
        self.calls.append(dict(messages=messages, tools=tools, tool_choice=tool_choice, max_tokens=max_tokens))
        if tools is not None and tool_choice == "required" and self.reject_required:
            raise RuntimeError("LLM call failed after 1 attempts: 400 Client Error :: tool_choice required unsupported")
        if not self.script:
            raise RuntimeError("FakeLLM script exhausted")
        item = self.script[0]
        if callable(item):
            item = item(messages, tools)
            self.script.pop(0)
        elif tools is None and item.get("tools"):
            item = {"content": "NOTE: continuation note from the fake model."}
        else:
            self.script.pop(0)
        msg = {"role": "assistant", "content": item.get("content") or ""}
        if item.get("reasoning"):
            msg["reasoning_content"] = item["reasoning"]
        calls = item.get("tools") or []
        if calls:
            msg["tool_calls"] = []
            for name, args in calls:
                self._n += 1
                msg["tool_calls"].append({"id": f"call_{self._n}", "type": "function",
                                          "function": {"name": name, "arguments": json.dumps(args)}})
        prompt = estimate_tokens(messages)
        completion = text_tokens(msg["content"]) + 20 * len(calls)
        usage = {"prompt_tokens": prompt, "completion_tokens": completion, "cached_tokens": 0}
        for k in ("prompt_tokens", "completion_tokens"):
            self.total_usage[k] += usage[k]
        self.total_usage["calls"] += 1
        return {"message": msg, "usage": usage, "reasoning": item.get("reasoning") or "",
                "finish_reason": item.get("finish") or ("tool_calls" if calls else "stop"), "latency_s": 0.0}
