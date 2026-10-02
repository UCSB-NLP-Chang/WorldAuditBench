"""OpenAI-compatible VLM client (works with vLLM / OpenRouter / OpenAI), with retries and usage accounting."""
import os
import time
import requests


class VLMClient:
    def __init__(self, base_url=None, api_key=None, model=None,
                 temperature=0.4, max_tokens=500, timeout=None, retries=3):
        timeout = timeout or int(os.environ.get("VLM_TIMEOUT", 180))
        self.base_url = (base_url or os.environ.get("VLM_BASE_URL", "http://localhost:8000/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("VLM_API_KEY", "none")
        self.model = model or os.environ.get("VLM_MODEL", "")
        self.temperature, self.max_tokens = temperature, max_tokens
        self.timeout, self.retries = timeout, retries
        self.total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    def chat(self, messages, **kw):
        payload = dict(model=self.model, messages=messages,
                       temperature=kw.get("temperature", self.temperature),
                       max_tokens=kw.get("max_tokens", self.max_tokens))
        last_err = None
        for attempt in range(self.retries + 1):
            t0 = time.time()
            try:
                r = requests.post(f"{self.base_url}/chat/completions",
                                  headers={"Authorization": f"Bearer {self.api_key}"},
                                  json=payload, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                usage = data.get("usage") or {}
                self.total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                self.total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                self.total_usage["calls"] += 1
                return {
                    "text": data["choices"][0]["message"]["content"],
                    "usage": usage,
                    "latency_s": round(time.time() - t0, 2),
                }
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                last_err = e
                if isinstance(e, requests.HTTPError) and e.response is not None \
                        and e.response.status_code < 500 and e.response.status_code != 429:
                    break                      # 4xx (non-rate-limit): retrying is pointless
                time.sleep(min(2 ** attempt * 2, 20))
        raise RuntimeError(f"VLM call failed after {self.retries + 1} attempts: {last_err}")
