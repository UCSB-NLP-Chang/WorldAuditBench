#!/usr/bin/env python3
"""Transparent relay between Muse Code and OpenRouter's Responses API that restores tool namespaces.

Muse Code declares tools as Responses-API `namespace` tools ({"type": "namespace", "name": "mcp__world_audit", "tools": [...]})
and expects the model's function calls back as "<namespace>.<tool>".  OpenRouter returns the bare tool name, which Muse
resolves against its default namespace ("muse") and rejects as unknown.  This relay forwards every request unchanged and
rewrites the function_call `name` fields in the streamed response (and in non-streamed bodies) to "<namespace>.<name>"
using the namespaces declared in that request.  Nothing else is touched; the Authorization header passes through.

usage: python3 agent/vlm/native/muse_openrouter_proxy.py --port 18090 [--upstream https://openrouter.ai] [--log FILE]
Point Muse's endpoint_transport.base_url at http://127.0.0.1:<port>/api/v1 (agent/vlm/native/launch.py --muse-base-url).
"""
import argparse, http.client, http.server, json, pathlib, ssl, sys, threading, time, urllib.parse

UPSTREAM = "https://openrouter.ai"
LOG = None
DUMP = None
LOCK = threading.Lock()


def log(rec):
    if LOG:
        with LOCK, open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")


def namespace_map(body):
    m = {}
    try:
        for t in json.loads(body).get("tools", []) or []:
            if t.get("type") == "namespace":
                for f in t.get("tools", []) or []:
                    if f.get("name"):
                        m[f["name"]] = t["name"]
    except (ValueError, AttributeError):
        pass
    return m


def rewrite_obj(o, nsmap, stats):
    """Rewrite function_call names in any nested structure in place."""
    if isinstance(o, dict):
        t = o.get("type")
        # function_call items (output_item.added/done, response.output[]) and the response.function_call_arguments.* events,
        # which repeat the name at the event's top level
        if (t == "function_call" or (isinstance(t, str) and t.startswith("response.function_call"))) \
                and isinstance(o.get("name"), str) and "." not in o["name"] and o["name"] in nsmap:
            o["name"] = f"{nsmap[o['name']]}.{o['name']}"; stats["rewritten"] += 1
        for v in o.values():
            rewrite_obj(v, nsmap, stats)
    elif isinstance(o, list):
        for v in o:
            rewrite_obj(v, nsmap, stats)


def rewrite_sse_line(line, nsmap, stats):
    if not nsmap or not line.startswith(b"data: "):
        return line
    payload = line[6:].strip()
    if payload in (b"", b"[DONE]"):
        return line
    try:
        d = json.loads(payload)
    except ValueError:
        return line
    rewrite_obj(d, nsmap, stats)
    return b"data: " + json.dumps(d, separators=(",", ":")).encode() + b"\n"


class Relay(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.relay()

    def do_POST(self):
        self.relay()

    def relay(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        nsmap = namespace_map(body) if body else {}
        u = urllib.parse.urlsplit(UPSTREAM)
        conn = (http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection)(u.netloc, timeout=900)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
        headers["Host"] = u.netloc; headers["Accept-Encoding"] = "identity"
        if body:
            headers["Content-Length"] = str(len(body))
        t0 = time.time(); stats = {"rewritten": 0}
        if DUMP and body:
            (pathlib.Path(DUMP) / f"{t0:.3f}-{threading.get_ident()}.json").write_bytes(body)
        try:
            conn.request(self.command, self.path, body=body if body else None, headers=headers)
            resp = conn.getresponse()
        except Exception as e:  # upstream unreachable: tell the client, keep the relay alive
            self.send_response(502); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", "0"); self.end_headers()
            log({"t": t0, "path": self.path, "error": repr(e)}); return
        ctype = resp.getheader("Content-Type", "")
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() in ("transfer-encoding", "content-length", "connection", "content-encoding"):
                continue
            self.send_header(k, v)
        if "text/event-stream" in ctype:
            self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
            buf = b""
            while True:
                chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    out = rewrite_sse_line(line + b"\n", nsmap, stats)
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(out), out))
                self.wfile.flush()
            if buf:
                out = rewrite_sse_line(buf, nsmap, stats)
                self.wfile.write(b"%x\r\n%s\r\n" % (len(out), out))
            self.wfile.write(b"0\r\n\r\n"); self.wfile.flush()
        else:
            data = resp.read()
            if nsmap and "application/json" in ctype:
                try:
                    d = json.loads(data); rewrite_obj(d, nsmap, stats); data = json.dumps(d).encode()
                except ValueError:
                    pass
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); self.wfile.flush()
        log({"t": t0, "path": self.path, "status": resp.status, "namespaces": sorted(set(nsmap.values())), "rewritten": stats["rewritten"],
             "request_bytes": len(body), "input_images": body.count(b'"input_image"'), "seconds": round(time.time() - t0, 1)})

    def log_message(self, *a):
        pass


def main():
    global UPSTREAM, LOG, DUMP
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18090); ap.add_argument("--upstream", default=UPSTREAM); ap.add_argument("--log", default=None)
    ap.add_argument("--dump-dir", default=None, help="debug: save every request body here")
    a = ap.parse_args(); UPSTREAM = a.upstream.rstrip("/"); LOG = a.log; DUMP = a.dump_dir
    if DUMP:
        pathlib.Path(DUMP).mkdir(parents=True, exist_ok=True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Relay); srv.daemon_threads = True
    print(f"relay 127.0.0.1:{a.port} -> {UPSTREAM}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
