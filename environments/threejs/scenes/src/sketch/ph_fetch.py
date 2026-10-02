#!/usr/bin/env python3
"""Download Poly Haven texture sets (1k jpg: Diffuse / nor_gl / arm) and glTF models (with their
.bin and texture includes) into an assets directory laid out for common/pack.py:
  <assets>/textures/<id>/{Diffuse,nor_gl,arm}.jpg
  <assets>/models/<id>/<id>.gltf (+ includes)
Usage: ph_fetch.py --assets <dir> [--tex id ...] [--model id ...] [--res 1k]
"""
import argparse, json, pathlib, urllib.request, sys, concurrent.futures as cf

UA = {"User-Agent": "Mozilla/5.0 (asset fetch for an offline benchmark scene)"}


def get_json(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())


def fetch(url, dest: pathlib.Path):
    if dest.exists() and dest.stat().st_size > 0:
        return dest.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()
    dest.write_bytes(data)
    return len(data)


def fetch_texture(tid, assets, res):
    files = get_json(f"https://api.polyhaven.com/files/{tid}")
    out = assets / "textures" / tid
    n = 0
    for key in ("Diffuse", "nor_gl", "arm", "Rough", "AO"):
        ent = files.get(key, {}).get(res, {}).get("jpg")
        if ent:
            n += fetch(ent["url"], out / f"{key}.jpg")
    return tid, n


def fetch_model(mid, assets, res):
    files = get_json(f"https://api.polyhaven.com/files/{mid}")
    g = files["gltf"]
    r = res if res in g else sorted(g.keys())[0]
    ent = g[r]["gltf"]
    out = assets / "models" / mid
    n = fetch(ent["url"], out / f"{mid}.gltf")
    for rel, inc in ent.get("include", {}).items():
        n += fetch(inc["url"], out / rel)
    info = get_json(f"https://api.polyhaven.com/info/{mid}")
    (out / "info.json").write_text(json.dumps({"dimensions": info.get("dimensions"), "res": r}))
    return mid, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True)
    ap.add_argument("--tex", nargs="*", default=[])
    ap.add_argument("--model", nargs="*", default=[])
    ap.add_argument("--res", default="1k")
    a = ap.parse_args()
    assets = pathlib.Path(a.assets)
    with cf.ThreadPoolExecutor(6) as ex:
        futs = [ex.submit(fetch_texture, t, assets, a.res) for t in a.tex] + [ex.submit(fetch_model, m, assets, a.res) for m in a.model]
        for f in cf.as_completed(futs):
            try:
                name, n = f.result()
                print(f"{name:32s} {n/1e6:6.2f} MB", file=sys.stderr)
            except Exception as e:
                print("ERROR", e, file=sys.stderr)


if __name__ == "__main__":
    main()
