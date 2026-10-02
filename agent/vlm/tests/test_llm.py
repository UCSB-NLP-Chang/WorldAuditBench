import json

import pytest

from agent.vlm.llm import LLMClient, normalize_assistant
from agent.vlm.tests.stub_server import StubServer, completion

TOOLS = [{"type": "function", "function": {"name": "move", "parameters": {"type": "object"}}}]


@pytest.fixture
def stub():
    servers = []

    def make(responses):
        s = StubServer(responses)
        servers.append(s)
        return s
    yield make
    for s in servers:
        s.close()


def test_chat_sends_tools_and_returns_tool_calls_and_usage(stub):
    s = stub([(200, completion(content="I will walk.", tool_calls=[("move", {"distance_m": 2})],
                                prompt=1234, completion_tokens=17, cached=1000))])
    c = LLMClient(base_url=s.url, model="m", temperature=0.4)
    r = c.chat([{"role": "user", "content": "hi"}], tools=TOOLS)
    body = s.requests[0]["body"]
    assert body["tools"] == TOOLS and body["tool_choice"] == "auto" and body["model"] == "m"
    assert body["stream"] is False
    assert r["message"]["content"] == "I will walk."
    assert r["message"]["tool_calls"][0]["function"]["name"] == "move"
    assert json.loads(r["message"]["tool_calls"][0]["function"]["arguments"]) == {"distance_m": 2}
    assert r["usage"] == {"prompt_tokens": 1234, "completion_tokens": 17, "cached_tokens": 1000, "reasoning_tokens": 0}
    assert r["finish_reason"] == "tool_calls" and r["latency_s"] >= 0
    assert c.total_usage["prompt_tokens"] == 1234 and c.total_usage["calls"] == 1


def test_missing_cached_tokens_counts_as_zero(stub):
    s = stub([(200, completion(content="x"))])
    r = LLMClient(base_url=s.url, model="m").chat([{"role": "user", "content": "hi"}])
    assert r["usage"]["cached_tokens"] == 0
    assert "tools" not in s.requests[0]["body"]


def test_retries_on_5xx_then_succeeds(stub):
    s = stub([(500, {"error": "boom"}), (200, completion(content="ok"))])
    c = LLMClient(base_url=s.url, model="m", retries=2, backoff=0.01)
    assert c.chat([{"role": "user", "content": "hi"}])["message"]["content"] == "ok"
    assert len(s.requests) == 2


def test_4xx_is_not_retried(stub):
    s = stub([(400, {"error": "bad"})])
    c = LLMClient(base_url=s.url, model="m", retries=2, backoff=0.01, reasoning_effort=None)
    with pytest.raises(RuntimeError, match="bad"):          # the server's error body is in the message
        c.chat([{"role": "user", "content": "hi"}])
    assert len(s.requests) == 1


def test_normalize_assistant_keeps_only_template_relevant_keys():
    raw = {"role": "assistant", "content": None, "refusal": None, "annotations": None,
           "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "wait", "arguments": "{}"},
                           "extra": 1}]}
    m = normalize_assistant(raw)
    assert m == {"role": "assistant", "content": "",
                 "tool_calls": [{"id": "c1", "type": "function",
                                 "function": {"name": "wait", "arguments": "{}"}}]}
    assert normalize_assistant({"role": "assistant", "content": "hi"}) == {"role": "assistant", "content": "hi"}


def test_default_sampling_and_reasoning_fields_are_sent(stub):
    s = stub([(200, completion(content="x"))])
    c = LLMClient(base_url=s.url, model="m")
    c.chat([{"role": "user", "content": "hi"}])
    body = s.requests[0]["body"]
    assert body["max_tokens"] == 4096 and body["temperature"] == 1.0
    assert body["top_p"] == 0.95 and body["top_k"] == 20 and body["min_p"] == 0.0
    assert body["presence_penalty"] == 0.0 and body["repetition_penalty"] == 1.0
    assert body["reasoning_effort"] == "low" and "reasoning" not in body


def test_reasoning_can_be_disabled_and_sampling_overridden(stub):
    s = stub([(200, completion(content="x"))])
    c = LLMClient(base_url=s.url, model="m", reasoning_effort=None, top_k=None, temperature=0.4)
    c.chat([{"role": "user", "content": "hi"}])
    body = s.requests[0]["body"]
    assert "reasoning_effort" not in body and "top_k" not in body and body["temperature"] == 0.4


def test_reasoning_field_rejected_by_server_is_dropped_for_the_session(stub):
    s = stub([(400, {"error": "unknown parameter reasoning_effort"}), (200, completion(content="ok")),
              (200, completion(content="ok2"))])
    c = LLMClient(base_url=s.url, model="m", retries=0, backoff=0.01)
    assert c.chat([{"role": "user", "content": "hi"}])["message"]["content"] == "ok"
    assert "reasoning_effort" in s.requests[0]["body"] and "reasoning_effort" not in s.requests[1]["body"]
    c.chat([{"role": "user", "content": "again"}])
    assert "reasoning_effort" not in s.requests[2]["body"]         # not retried every call


def test_extra_body_is_merged_into_every_request(stub):
    s = stub([(200, completion(content="x"))])
    c = LLMClient(base_url=s.url, model="m", extra_body={"provider": {"sort": "latency"}, "seed": 7})
    c.chat([{"role": "user", "content": "hi"}])
    body = s.requests[0]["body"]
    assert body["provider"] == {"sort": "latency"} and body["seed"] == 7 and body["model"] == "m"


def test_response_provider_field_is_surfaced(stub):
    body = completion(content="x"); body["provider"] = "Makora"
    s = stub([(200, body)])
    r = LLMClient(base_url=s.url, model="m").chat([{"role": "user", "content": "hi"}])
    assert r["provider"] == "Makora"
    s2 = stub([(200, completion(content="y"))])
    assert LLMClient(base_url=s2.url, model="m").chat([{"role": "user", "content": "hi"}])["provider"] is None


def test_rate_limit_is_retried_patiently_and_honours_retry_after(stub):
    s = stub([(429, {"error": "slow down"}), (429, {"error": "slow down"}), (200, completion(content="ok"))])
    c = LLMClient(base_url=s.url, model="m", retries=0, backoff=0.01, rate_limit_wait=30)
    assert c.chat([{"role": "user", "content": "hi"}])["message"]["content"] == "ok"
    assert len(s.requests) == 3                                  # 429s do not count against `retries`


def test_rate_limit_gives_up_after_the_wait_budget(stub):
    s = stub([(429, {"error": "slow down"})])
    c = LLMClient(base_url=s.url, model="m", retries=0, backoff=0.01, rate_limit_wait=0.05)
    with pytest.raises(RuntimeError, match="429"):
        c.chat([{"role": "user", "content": "hi"}])


def test_rate_limit_waits_are_reported_in_the_response(stub):
    s = stub([(429, {"error": "slow down"}), (200, completion(content="ok"))])
    c = LLMClient(base_url=s.url, model="m", backoff=0.01, rate_limit_wait=30)
    r = c.chat([{"role": "user", "content": "hi"}])
    assert r["rate_limited"] == 1 and r["rate_limit_wait_s"] >= 0.01
    assert c.total_usage["rate_limited"] == 1


def test_200_without_choices_is_retried_as_a_server_error(stub):
    s = stub([(200, {"error": {"message": "Provider returned error", "code": 502}}), (200, completion(content="ok"))])
    c = LLMClient(base_url=s.url, model="m", retries=2, backoff=0.01)
    assert c.chat([{"role": "user", "content": "hi"}])["message"]["content"] == "ok"
    assert len(s.requests) == 2
    s2 = stub([(200, {"error": {"message": "Provider returned error", "code": 502}})])
    c = LLMClient(base_url=s2.url, model="m", retries=1, backoff=0.01)
    with pytest.raises(RuntimeError, match="Provider returned error"):
        c.chat([{"role": "user", "content": "hi"}])


def test_rate_limit_wait_default_is_an_hour():
    assert LLMClient(base_url="http://x", model="m").rate_limit_wait == 3600


def test_parallel_tool_calls_is_requested_with_tools(stub):
    s = stub([(200, completion(content="x"))])
    LLMClient(base_url=s.url, model="m").chat([{"role": "user", "content": "hi"}], tools=TOOLS)
    assert s.requests[0]["body"]["parallel_tool_calls"] is True       # DashScope returns one call per reply otherwise
    s2 = stub([(200, completion(content="x"))])
    LLMClient(base_url=s2.url, model="m").chat([{"role": "user", "content": "hi"}])
    assert "parallel_tool_calls" not in s2.requests[0]["body"]


def test_transient_4xx_such_as_multimodal_download_timeout_is_retried(stub):
    body = {"error": {"message": "Provider returned error", "code": 400,
                      "metadata": {"raw": '{"error":{"code":"invalid_parameter_error","message":"Download multimodal file timed out"}}'}}}
    s = stub([(400, body), (200, completion(content="ok"))])
    c = LLMClient(base_url=s.url, model="m", retries=2, backoff=0.01, reasoning_effort=None)
    assert c.chat([{"role": "user", "content": "hi"}])["message"]["content"] == "ok"
    assert len(s.requests) == 2


def test_reasoning_is_kept_in_the_message_when_preserve_thinking_is_on(stub):
    body = completion(content="", tool_calls=[("move", {"distance_m": 1})]); body["choices"][0]["message"]["reasoning_content"] = "I should walk."
    s = stub([(200, body)])
    r = LLMClient(base_url=s.url, model="m", preserve_thinking=True).chat([{"role": "user", "content": "hi"}])
    assert r["message"]["reasoning_content"] == "I should walk."        # re-sent verbatim next turn (Qwen3.8 default)
    assert r["reasoning"] == "I should walk."


def test_reasoning_is_stripped_but_returned_when_preserve_thinking_is_off(stub):
    body = completion(content="x"); body["choices"][0]["message"]["reasoning"] = "OpenRouter style"
    s = stub([(200, body)])
    r = LLMClient(base_url=s.url, model="m", preserve_thinking=False).chat([{"role": "user", "content": "hi"}])
    assert "reasoning_content" not in r["message"] and "reasoning" not in r["message"]
    assert r["reasoning"] == "OpenRouter style"
    assert normalize_assistant({"role": "assistant", "content": "a", "reasoning_content": "t"}, keep_reasoning=True) == \
        {"role": "assistant", "content": "a", "reasoning_content": "t"}


def test_connection_errors_are_retried_for_the_network_wait_budget(monkeypatch):
    import requests as rq
    from agent.vlm import llm as llm_mod
    calls = {"n": 0}
    good = completion(content="back")

    class R:
        status_code = 200; text = "{}"; headers = {}
        def raise_for_status(self): pass
        def json(self): return good

    def fake_post(*a, **k):
        calls["n"] += 1
        if calls["n"] < 4:
            raise rq.ConnectionError("network down")
        return R()
    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    c = LLMClient(base_url="http://x", model="m", retries=1, backoff=0.01, network_wait=30)
    assert c.chat([{"role": "user", "content": "hi"}])["message"]["content"] == "back"
    assert calls["n"] == 4                                    # 3 outages did not exhaust `retries`
    calls["n"] = -100
    c = LLMClient(base_url="http://x", model="m", retries=1, backoff=0.01, network_wait=0.05)
    with pytest.raises(RuntimeError, match="network down"):
        c.chat([{"role": "user", "content": "hi"}])
