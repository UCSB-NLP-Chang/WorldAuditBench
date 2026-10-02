#!/usr/bin/env python3
"""Write the packed house assets (pack.json from pack.py) as plain files for the harness build
(environments/threejs/runtime/house/house.js loads them over HTTP instead of the embedded base64 pack).

usage: export_pack.py --pack <pack.json> --out assets/house/pack
Layout: models/<id>.glb, tex/<id>.<diff|nor|arm>.webp, hdri/sky.hdr, manifest.json (bboxes).
"""
import argparse
import base64
import gzip
import json
import pathlib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pack = json.load(open(a.pack))
    out = pathlib.Path(a.out)
    (out / "models").mkdir(parents=True, exist_ok=True)
    (out / "tex").mkdir(exist_ok=True)
    (out / "hdri").mkdir(exist_ok=True)
    manifest = {"models": {}, "textures": {}}
    total = 0
    for mid, e in pack["models"].items():
        glb = gzip.decompress(base64.b64decode(e["glb"]))
        (out / "models" / f"{mid}.glb").write_bytes(glb)
        manifest["models"][mid] = {"bbox": e["bbox"], "bytes": len(glb)}
        total += len(glb)
    for tid, e in pack["textures"].items():
        manifest["textures"][tid] = []
        for kind, b64 in e.items():
            data = base64.b64decode(b64)
            (out / "tex" / f"{tid}.{kind}.webp").write_bytes(data)
            manifest["textures"][tid].append(kind)
            total += len(data)
    hdr = gzip.decompress(base64.b64decode(pack["hdri"]))
    (out / "hdri" / "sky.hdr").write_bytes(hdr)
    total += len(hdr)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {out}: {len(manifest['models'])} models, {len(manifest['textures'])} texture sets, hdri; {total/1e6:.1f} MB")


if __name__ == "__main__":
    main()
