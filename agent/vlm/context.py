"""Append-only conversation with token accounting and epoch compaction.

Within an epoch every request is a strict extension of the previous one (the server's prefix
cache serves everything but the new tail). When the predicted prompt size crosses the limit,
the model writes a continuation note, and the conversation is rebuilt as
    [system (byte-identical)] [user: header = task + note + action index + ledger + notes]
    [the last `keep_recent` environment actions' messages, verbatim]
The note request itself is produced by the loop (this module never calls the model).
"""
from __future__ import annotations

import base64
import copy
import io
import json
from typing import Dict, List, Optional, Tuple

from PIL import Image

MSG_OVERHEAD = 4          # role markers etc. per message


def text_tokens(s: str) -> int:
    return len(s) // 4 + 1


def image_tokens(w: int, h: int) -> int:
    """Qwen3-VL: 32x32 pixels per token (patch 16, merge 2) after rounding to multiples of 32,
    plus the two vision boundary tokens."""
    return max(1, round(w / 32)) * max(1, round(h / 32)) + 2


_url_size_cache: Dict[str, Tuple[int, int]] = {}


def _dataurl_size(url: str) -> Tuple[int, int]:
    size = _url_size_cache.get(url)
    if size is None:
        raw = base64.b64decode(url.split(",", 1)[1])
        size = Image.open(io.BytesIO(raw)).size
        _url_size_cache[url] = size
    return size


def message_tokens(msg: dict) -> int:
    n = MSG_OVERHEAD
    content = msg.get("content")
    if isinstance(content, str):
        n += text_tokens(content)
    elif isinstance(content, list):
        for part in content:
            if part.get("type") == "text":
                n += text_tokens(part["text"])
            elif part.get("type") == "image_url":
                n += image_tokens(*_dataurl_size(part["image_url"]["url"]))
    if msg.get("tool_calls"):
        n += text_tokens(json.dumps(msg["tool_calls"]))
    if msg.get("reasoning_content"):
        n += text_tokens(msg["reasoning_content"])
    return n


def estimate_tokens(messages: List[dict]) -> int:
    return sum(message_tokens(m) for m in messages)


class Conversation:
    def __init__(self, system: str, context_limit: int = 64000, keep_recent: int = 3, extra_tokens: int = 0):
        self.system = system
        self.context_limit = context_limit
        self.keep_recent = keep_recent
        self.extra_tokens = extra_tokens                 # request-level tokens outside messages (tool schemas)
        self.messages: List[dict] = [{"role": "system", "content": system}]
        self.compactions = 0
        self._action_starts: Dict[int, int] = {}     # action index -> index of the assistant msg that issued it
        self._last_assistant: Optional[int] = None
        self._usage_base: Optional[int] = None       # prompt+completion tokens of the last measured call
        self._base_len = 0                           # messages covered by _usage_base
        self._compaction_mark: Optional[int] = None

    # ------------------------------------------------------------- appending
    def append_user_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_assistant(self, msg: dict, call: Optional[int] = None) -> None:
        if call is not None:
            msg["_call"] = call                          # private: stripped from requests, kept in the transcript
        self.messages.append(msg)
        self._last_assistant = len(self.messages) - 1

    def append_tool(self, call_id: str, text: str) -> None:
        self.messages.append({"role": "tool", "tool_call_id": call_id, "content": text})

    def append_user_images(self, label: str, items: List[Tuple[str, str, str]]) -> None:
        """items: (caption, data_url, ref). Images travel in a user message (tool messages are
        text-only in the OpenAI spec and in most open-model chat templates)."""
        content = [{"type": "text", "text": label}]
        for caption, url, ref in items:
            content.append({"type": "text", "text": caption})
            content.append({"type": "image_url", "image_url": {"url": url}})
        # refs ride along under a private key (stripped from requests) so identical frames
        # (e.g. a static scene during wait) still map back to their own refs in the transcript
        self.messages.append({"role": "user", "content": content, "_refs": [ref for _, _, ref in items]})

    def mark_action(self, action_index: int) -> None:
        """Record that the most recent assistant message issued environment action `action_index`."""
        if self._last_assistant is None:
            raise RuntimeError("mark_action before any assistant message")
        self._action_starts.setdefault(action_index, self._last_assistant)

    def snapshot(self) -> List[dict]:
        """Request body: a deep copy without private keys."""
        return [copy.deepcopy({k: v for k, v in m.items() if not k.startswith("_")}) for m in self.messages]

    # ------------------------------------------------------------ accounting
    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Anchor the prediction on the measured prompt. The reply that just came back is
        estimated from its visible text rather than `completion_tokens`: thinking models spend
        most of the completion on reasoning that is never sent back."""
        self._usage_base = prompt_tokens
        n = len(self.messages)
        self._base_len = n - 1 if n and self.messages[-1].get("role") == "assistant" else n

    def predicted_next(self) -> int:
        if self._usage_base is None:                     # no measurement yet (or just rebuilt): pure estimate
            return estimate_tokens(self.messages) + self.extra_tokens
        return self._usage_base + estimate_tokens(self.messages[self._base_len:])

    def needs_compaction(self) -> bool:
        return self.predicted_next() > self.context_limit

    # ------------------------------------------------------------ compaction
    def begin_compaction(self, prompt: str) -> None:
        self.append_user_text(prompt)
        self._compaction_mark = len(self.messages) - 1

    def finish_compaction(self, header: str) -> List[dict]:
        """Rebuild around `header`; returns the full old message list for archiving."""
        old = self.messages
        body = old[:self._compaction_mark] if self._compaction_mark is not None else old
        tail: List[dict] = []
        kept: Dict[int, int] = {}
        if self._action_starts:
            first_kept = max(self._action_starts) - self.keep_recent + 1
            candidates = [a for a in self._action_starts if a >= first_kept]
            if candidates:
                start = self._action_starts[min(candidates)]
                tail = body[start:]
                kept = {a: i - start + 2 for a, i in self._action_starts.items() if a >= first_kept}
        self.messages = [{"role": "system", "content": self.system},
                         {"role": "user", "content": header}] + tail
        self._action_starts = kept
        self._last_assistant = max(kept.values()) if kept else None
        self._usage_base, self._base_len = None, 0
        self._compaction_mark = None
        self.compactions += 1
        return old

    # ------------------------------------------------------------ transcript
    def transcript_row(self, msg: dict) -> dict:
        row = {k: v for k, v in msg.items() if not k.startswith("_")}
        if "_call" in msg:
            row["call"] = msg["_call"]
        if msg.get("_reasoning"):                      # thinking not re-sent to the model, kept for the record
            row["reasoning_content"] = msg["_reasoning"]
        if isinstance(msg.get("content"), list):
            refs = iter(msg.get("_refs") or [])
            parts = []
            for p in msg["content"]:
                if p.get("type") == "image_url":
                    parts.append({"type": "image_ref", "ref": next(refs, "?")})
                else:
                    parts.append(p)
            row["content"] = parts
        return row
