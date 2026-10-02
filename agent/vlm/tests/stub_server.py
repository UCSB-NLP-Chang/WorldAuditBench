"""Minimal OpenAI-compatible stub: serves canned chat completions, records requests."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class StubServer:
    def __init__(self, responses):
        """responses: list of (status, body_dict); consumed in order, last one repeats."""
        self.responses = list(responses)
        self.requests = []
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                stub.requests.append(dict(path=self.path, headers=dict(self.headers),
                                          body=json.loads(self.rfile.read(n) or b"{}")))
                status, body = stub.responses[0] if len(stub.responses) == 1 else stub.responses.pop(0)
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


def completion(content=None, tool_calls=None, prompt=100, completion_tokens=20, cached=None,
               finish="stop"):
    msg = {"role": "assistant", "content": content, "refusal": None, "annotations": None}
    if tool_calls:
        msg["tool_calls"] = [dict(id=f"call_{i}", type="function",
                                  function=dict(name=n, arguments=json.dumps(a)))
                             for i, (n, a) in enumerate(tool_calls)]
        finish = "tool_calls"
    usage = {"prompt_tokens": prompt, "completion_tokens": completion_tokens,
             "total_tokens": prompt + completion_tokens}
    if cached is not None:
        usage["prompt_tokens_details"] = {"cached_tokens": cached}
    return {"id": "x", "object": "chat.completion", "model": "stub",
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}], "usage": usage}
