"""OpenAI-compatible chat client with tool calling (vLLM / any open-model server).

Non-streaming only (hermes-style tool parsers are unreliable when streamed). Returns the
assistant message normalized to the keys chat templates consume, so it can be appended to the
conversation verbatim and re-sent byte-identically for prefix-cache reuse.
"""
from __future__ import annotations

import json
import os
import random
import time
from typing import List, Optional

import requests


def reasoning_text(msg: dict) -> str:
    """The model's chain of thought, whichever field the server used (DashScope/vLLM: reasoning_content;
    OpenRouter: reasoning)."""
    return msg.get("reasoning_content") or (msg.get("reasoning") if isinstance(msg.get("reasoning"), str) else "") or ""


def normalize_assistant(msg: dict, keep_reasoning: bool = False) -> dict:
    """Keep role / content / tool_calls (id, type, function.name, function.arguments); with
    keep_reasoning the chain of thought stays in the message as `reasoning_content` so it is
    re-sent verbatim on later turns (Qwen3.8's default: preserve thinking across the history)."""
    out = {"role": "assistant", "content": msg.get("content") or ""}
    if keep_reasoning and reasoning_text(msg):
        out["reasoning_content"] = reasoning_text(msg)
    calls = msg.get("tool_calls") or []
    if calls:
        out["tool_calls"] = [
            {"id": c.get("id"), "type": c.get("type", "function"),
             "function": {"name": c["function"]["name"],
                          "arguments": c["function"].get("arguments") or "{}"}}
            for c in calls]
    return out


class LLMClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, temperature: float = 1.0, max_tokens: int = 4096,
                 top_p: Optional[float] = 0.95, top_k: Optional[int] = 20, min_p: Optional[float] = 0.0,
                 presence_penalty: Optional[float] = 0.0, repetition_penalty: Optional[float] = 1.0,
                 reasoning_effort: Optional[str] = "low", extra_body: Optional[dict] = None,
                 preserve_thinking: bool = True,
                 timeout: Optional[float] = None, retries: int = 3, backoff: float = 2.0,
                 rate_limit_wait: float = 3600.0, network_wait: float = 1800.0):
        """Defaults follow Qwen's recommended sampling for thinking models (temperature 1.0, top_p 0.95,
        top_k 20, min_p 0, presence 0, repetition 1.0). top_k / min_p / repetition_penalty are vLLM and
        OpenRouter extensions; pass None to omit a field. `reasoning_effort` is sent as the OpenAI
        top-level field (DashScope and OpenRouter honour it; the nested OpenRouter form is ignored by
        DashScope) and dropped for the session if the server rejects it with a 4xx.
        `preserve_thinking` keeps the chain of thought in the appended assistant message so it is
        re-sent on later turns. `extra_body` is merged into every request as-is (e.g. OpenRouter's
        {"provider": {"sort": "latency"}} or a fixed "seed"). HTTP 429 (rate limit) is retried with
        growing backoff (Retry-After honoured) for up to `rate_limit_wait` seconds, independently of
        `retries`, which covers 5xx. Connection errors / timeouts (a network outage) are likewise retried
        with backoff for up to `network_wait` seconds without consuming `retries`."""
        self.base_url = (base_url or os.environ.get("VLM_BASE_URL", "http://localhost:8010/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("VLM_API_KEY", "none")
        self.model = model or os.environ.get("VLM_MODEL", "")
        self.temperature, self.max_tokens = temperature, max_tokens
        self.sampling = {k: v for k, v in dict(top_p=top_p, top_k=top_k, min_p=min_p, presence_penalty=presence_penalty,
                                               repetition_penalty=repetition_penalty).items() if v is not None}
        self.reasoning_effort = reasoning_effort
        self.preserve_thinking = preserve_thinking
        self.extra_body = dict(extra_body or {})
        self.timeout = timeout or float(os.environ.get("VLM_TIMEOUT", 300))
        self.retries, self.backoff, self.rate_limit_wait = retries, backoff, rate_limit_wait
        self.network_wait = network_wait
        self.total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0,
                            "reasoning_tokens": 0, "calls": 0, "rate_limited": 0, "rate_limit_wait_s": 0.0}

    def chat(self, messages: List[dict], tools: Optional[List[dict]] = None, tool_choice: str = "auto",
             max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> dict:
        payload = dict(model=self.model, messages=messages, stream=False,
                       temperature=self.temperature if temperature is None else temperature,
                       max_tokens=max_tokens or self.max_tokens, **self.sampling)
        payload.update(self.extra_body)
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
            payload["parallel_tool_calls"] = True      # DashScope emits one call per reply without it; vLLM ignores it
        last_err = None
        attempt = 0
        rl_started = None                                  # when the current run of 429s began
        rl_tries, rl_waited = 0, 0.0
        net_started, net_tries = None, 0                   # same for connection errors / timeouts
        while attempt <= self.retries:
            t0 = time.time()
            try:
                r = requests.post(f"{self.base_url}/chat/completions",
                                  headers={"Authorization": f"Bearer {self.api_key}"},
                                  json=payload, timeout=self.timeout)
                if 400 <= r.status_code < 500 and r.status_code != 429 and "reasoning_effort" in payload:
                    payload.pop("reasoning_effort")        # server does not know the field: drop it for good
                    self.reasoning_effort = None
                    continue                               # does not count as an attempt
                if r.status_code == 429:
                    rl_started = rl_started or time.time()
                    if time.time() - rl_started > self.rate_limit_wait:
                        raise RuntimeError(f"rate limited for over {self.rate_limit_wait:.0f}s: 429 :: {r.text[:300]}")
                    wait = min(self.backoff * (2 ** rl_tries), 60.0) * (1 + 0.25 * random.random())
                    try:
                        wait = max(wait, float(r.headers.get("Retry-After", 0)))
                    except ValueError:
                        pass
                    rl_tries += 1
                    rl_waited += wait
                    time.sleep(wait)
                    continue                               # rate limits do not consume `retries`
                r.raise_for_status()
                data = r.json()
                if not data.get("choices"):                # e.g. OpenRouter: HTTP 200 carrying a provider error
                    raise requests.HTTPError(f"200 without choices :: {json.dumps(data)[:500]}", response=None)
                choice = data["choices"][0]
                usage = _usage(data.get("usage") or {})
                for k in ("prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens"):
                    self.total_usage[k] += usage[k]
                self.total_usage["calls"] += 1
                self.total_usage["rate_limited"] += rl_tries
                self.total_usage["rate_limit_wait_s"] = round(self.total_usage["rate_limit_wait_s"] + rl_waited, 1)
                return {"message": normalize_assistant(choice["message"], self.preserve_thinking),
                        "reasoning": reasoning_text(choice["message"]),
                        "usage": usage,
                        "finish_reason": choice.get("finish_reason"),
                        "provider": data.get("provider"),          # OpenRouter: which upstream served the call
                        "rate_limited": rl_tries, "rate_limit_wait_s": round(rl_waited, 3),
                        "latency_s": round(time.time() - t0, 2)}
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                last_err = e
                if not isinstance(e, requests.HTTPError):    # network outage: keep trying, do not burn retries
                    net_started = net_started or time.time()
                    if time.time() - net_started > self.network_wait:
                        raise RuntimeError(f"network unavailable for over {self.network_wait:.0f}s: {e}")
                    time.sleep(min(self.backoff * (2 ** net_tries), 60.0) * (1 + 0.25 * random.random()))
                    net_tries += 1
                    continue
                if isinstance(e, requests.HTTPError) and e.response is not None:
                    last_err = RuntimeError(f"{e} :: {e.response.text[:500]}")   # keep the server's reason
                    transient = "timed out" in e.response.text.lower() or "timeout" in e.response.text.lower()
                    if e.response.status_code < 500 and e.response.status_code != 429 and not transient:
                        break                              # a 4xx will not get better on retry
                    # (DashScope answers a slow multimodal fetch with a 400 "Download multimodal file timed out";
                    #  that one is worth retrying like a 5xx)
                time.sleep(min(self.backoff * (2 ** attempt), 20))
                attempt += 1
        raise RuntimeError(f"LLM call failed after {self.retries + 1} attempts: {last_err}")


def _usage(u: dict) -> dict:
    details = u.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens") if isinstance(details, dict) else getattr(details, "cached_tokens", 0)
    cdetails = u.get("completion_tokens_details") or {}
    reasoning = cdetails.get("reasoning_tokens") if isinstance(cdetails, dict) else 0
    return {"prompt_tokens": int(u.get("prompt_tokens") or 0),
            "completion_tokens": int(u.get("completion_tokens") or 0),
            "cached_tokens": int(cached or 0),
            "reasoning_tokens": int(reasoning or 0)}
