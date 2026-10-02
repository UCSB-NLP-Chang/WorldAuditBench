#!/usr/bin/env python3
"""Assemble the single-file HTML: template.html + pack.json (assets, three.js) + app.js.

usage: build.py --pack <pack.json> --out <html>
"""
import argparse
import base64
import gzip
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pack = json.load(open(a.pack))
    app = (HERE / "app.js").read_text(encoding="utf-8")
    pack["js"]["app"] = base64.b64encode(gzip.compress(app.encode("utf-8"), 9)).decode("ascii")
    payload = "window.__HOUSE_PACK=" + json.dumps(pack, separators=(",", ":")) + ";"
    # guard against accidental </script> inside JSON strings (base64 cannot contain '<', but keep it safe)
    payload = payload.replace("</", "<\\/")
    html = (HERE / "template.html").read_text(encoding="utf-8").replace("/*__PACK__*/", payload)
    out = pathlib.Path(a.out)
    out.write_text(html, encoding="utf-8")
    sizes = {k: sum(len(v.get("glb", "")) for v in pack["models"].values()) if k == "models" else 0 for k in ["models"]}
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB; models {sizes['models']/1e6:.1f} MB b64, "
          f"textures {sum(sum(len(x) for x in t.values()) for t in pack['textures'].values())/1e6:.1f} MB, "
          f"hdri {len(pack['hdri'])/1e6:.1f} MB, js {sum(len(v) for v in pack['js'].values())/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
