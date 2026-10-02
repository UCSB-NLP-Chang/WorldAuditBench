#!/usr/bin/env python3
"""Generic asset packer for the single-file candidate environments.

Reads a manifest.json next to the calling build and produces a JSON "pack":
  models   : glTF (.gltf + .bin + images) or .glb  -> quantized, WebP-textured GLB, gzip, base64
  textures : Poly Haven texture sets (Diffuse/nor_gl/arm 1k jpg) -> WebP base64
  hdri     : optional .hdr -> gzip base64
  js       : {specifier: file path} -> gzip base64 (relative imports are left for the bootstrap)

Model re-encoding:
  POSITION -> int16 (KHR_mesh_quantization, per-mesh scale/translation on a child node)
  NORMAL   -> int8 normalized;  TEXCOORD_0 -> uint16 normalized when inside [0,1]
  indices  -> uint16 when possible;  TANGENT/COLOR/extra UV sets are dropped
  images   -> WebP (EXT_texture_webp), resized per manifest; ARM reused as occlusion when missing
  `height` (metres, from the Poly Haven catalogue) rescales models exported in the wrong unit.

Usage:
  pack.py --manifest <manifest.json> --assets <dir with models/ textures/ hdri/> \
          --js-root <dir> [--js-root <dir> ...] --out pack.json
Per-asset results are cached in <out>.cache/.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import pathlib
import struct
import sys

import numpy as np
from PIL import Image

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def gz(data: bytes) -> bytes:
    return gzip.compress(data, 9)


def webp_bytes(src, size, quality):
    im = Image.open(src) if not isinstance(src, bytes) else Image.open(io.BytesIO(src))
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if has_alpha else "RGB")
    if max(im.size) > size:
        w, h = im.size
        scale = size / max(w, h)
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()


def classic_bytes(src, size, quality):
    """JPEG (RGB) or PNG (alpha) for loaders without EXT_texture_webp support (three r113 GLTFLoader)."""
    im = Image.open(src) if not isinstance(src, bytes) else Image.open(io.BytesIO(src))
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if has_alpha else "RGB")
    if max(im.size) > size:
        w, h = im.size
        scale = size / max(w, h)
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    if has_alpha:
        im.save(buf, "PNG", optimize=True)
        return buf.getvalue(), "image/png"
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=False)
    return buf.getvalue(), "image/jpeg"


class BinWriter:
    def __init__(self):
        self.chunks, self.views, self.offset = [], [], 0

    def add(self, data: bytes, stride=None, target=None):
        pad = (-len(data)) % 4
        self.chunks.append(data + b"\0" * pad)
        view = {"buffer": 0, "byteOffset": self.offset, "byteLength": len(data)}
        if stride:
            view["byteStride"] = stride
        if target:
            view["target"] = target
        self.views.append(view)
        self.offset += len(data) + pad
        return len(self.views) - 1

    def blob(self):
        return b"".join(self.chunks)


def node_matrix(n):
    m = np.identity(4)
    if "matrix" in n:
        return np.array(n["matrix"]).reshape(4, 4).T
    t = n.get("translation", [0, 0, 0])
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = n.get("scale", [1, 1, 1])
    R = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    m[:3, :3] = R * np.array(s)[None, :]
    m[:3, 3] = t
    return m


def load_gltf(model_dir: pathlib.Path):
    """Return (json, buffers[list of bytes], image_bytes_getter)."""
    glbs = list(model_dir.glob("*.glb"))
    if glbs:
        data = glbs[0].read_bytes()
        magic, version, length = struct.unpack("<III", data[:12])
        assert magic == 0x46546C67, "not a GLB"
        off = 12
        js, bins = None, []
        while off < length:
            clen, ctype = struct.unpack("<II", data[off:off + 8])
            chunk = data[off + 8:off + 8 + clen]
            if ctype == 0x4E4F534A:
                js = json.loads(chunk.decode("utf-8"))
            elif ctype == 0x004E4942:
                bins.append(bytes(chunk))
            off += 8 + clen
        return js, bins, lambda img: buffer_view_bytes(js, bins, img["bufferView"]) if "bufferView" in img else (model_dir / img["uri"]).read_bytes()
    gltf_path = next(model_dir.glob("*.gltf"))
    js = json.load(open(gltf_path))
    bins = [(model_dir / b["uri"]).read_bytes() for b in js["buffers"]]
    return js, bins, lambda img: (model_dir / img["uri"]).read_bytes()


def buffer_view_bytes(js, bins, bv_index):
    bv = js["bufferViews"][bv_index]
    buf = bins[bv.get("buffer", 0)]
    off = bv.get("byteOffset", 0)
    return buf[off:off + bv["byteLength"]]


def pack_model(model_dir: pathlib.Path, tex_size: int, q_diff: int, q_nor: int, height=None, webp=True):
    src, bins, image_bytes = load_gltf(model_dir)

    def accessor(i):
        a = src["accessors"][i]
        bv = src["bufferViews"][a["bufferView"]]
        buf = bins[bv.get("buffer", 0)]
        n = NC[a["type"]]
        dt = CT[a["componentType"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride")
        item = n * np.dtype(dt).itemsize
        if stride and stride != item:
            raw = np.frombuffer(buf, dtype=np.uint8, count=stride * (a["count"] - 1) + item, offset=off)
            rows = np.lib.stride_tricks.as_strided(raw, shape=(a["count"], item), strides=(stride, 1)).copy()
            return rows.view(dt).reshape(a["count"], n)
        return np.frombuffer(buf, dtype=dt, count=a["count"] * n, offset=off).reshape(a["count"], n)

    out = {
        "asset": {"version": "2.0", "generator": "game-auditing pack (quantized, WebP)"},
        "extensionsUsed": sorted(set(src.get("extensionsUsed", [])) | ({"KHR_mesh_quantization", "EXT_texture_webp"} if webp else {"KHR_mesh_quantization"})),
        "extensionsRequired": ["KHR_mesh_quantization"],
        "scene": src.get("scene", 0),
        "scenes": json.loads(json.dumps(src["scenes"])),
        "nodes": [], "meshes": [], "accessors": [], "bufferViews": [], "buffers": [],
        "materials": [], "textures": [], "images": [],
        "samplers": src.get("samplers", [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]),
    }
    bw = BinWriter()

    for img in src.get("images", []):
        name = (img.get("name") or img.get("uri") or "").lower()
        q = q_nor if ("nor" in name) else q_diff
        if webp:
            data, mime = webp_bytes(image_bytes(img), tex_size, q), "image/webp"
        else:
            data, mime = classic_bytes(image_bytes(img), tex_size, q)
        out["images"].append({"bufferView": bw.add(data), "mimeType": mime, "name": img.get("name", name)})
    for t in src.get("textures", []):
        if webp:
            out["textures"].append({"sampler": t.get("sampler", 0), "extensions": {"EXT_texture_webp": {"source": t["source"]}}})
        else:
            out["textures"].append({"sampler": t.get("sampler", 0), "source": t["source"]})
    for m in src.get("materials", []):
        nm = json.loads(json.dumps(m))
        pbr = nm.get("pbrMetallicRoughness", {})
        if "occlusionTexture" not in nm and "metallicRoughnessTexture" in pbr:
            nm["occlusionTexture"] = {"index": pbr["metallicRoughnessTexture"]["index"], "strength": 1.0}
        out["materials"].append(nm)

    mesh_quant, mesh_bounds = [], []
    world_min, world_max = np.full(3, np.inf), np.full(3, -np.inf)
    for mesh in src["meshes"]:
        prims = []
        pos_all = [accessor(p["attributes"]["POSITION"]).astype(np.float32) for p in mesh["primitives"]]
        mn = np.min([p.min(0) for p in pos_all], 0)
        mx = np.max([p.max(0) for p in pos_all], 0)
        mesh_bounds.append((mn, mx))
        c = (mn + mx) / 2
        h = float(max((mx - mn).max() / 2, 1e-6))
        s = h / 32767.0
        mesh_quant.append((c, s))
        for p, pos in zip(mesh["primitives"], pos_all):
            attrs = {}
            q = np.clip(np.round((pos - c) / s), -32767, 32767).astype(np.int16)
            padded = np.zeros((len(q), 4), np.int16)
            padded[:, :3] = q
            vi = bw.add(padded.tobytes(), stride=8, target=34962)
            out["accessors"].append({"bufferView": vi, "componentType": 5122, "count": len(q), "type": "VEC3",
                                     "min": [int(v) for v in q.min(0)], "max": [int(v) for v in q.max(0)]})
            attrs["POSITION"] = len(out["accessors"]) - 1
            if "NORMAL" in p["attributes"]:
                nor = accessor(p["attributes"]["NORMAL"]).astype(np.float32)
                nl = np.linalg.norm(nor, axis=1, keepdims=True)
                nor = nor / np.where(nl > 0, nl, 1)
                qn = np.clip(np.round(nor * 127), -127, 127).astype(np.int8)
                pn = np.zeros((len(qn), 4), np.int8)
                pn[:, :3] = qn
                vi = bw.add(pn.tobytes(), stride=4, target=34962)
                out["accessors"].append({"bufferView": vi, "componentType": 5120, "normalized": True, "count": len(qn), "type": "VEC3"})
                attrs["NORMAL"] = len(out["accessors"]) - 1
            if "TEXCOORD_0" in p["attributes"]:
                uv = accessor(p["attributes"]["TEXCOORD_0"]).astype(np.float32)
                if uv.min() >= -1e-4 and uv.max() <= 1 + 1e-4:
                    qu = np.clip(np.round(uv * 65535), 0, 65535).astype(np.uint16)
                    vi = bw.add(qu.tobytes(), stride=4, target=34962)
                    out["accessors"].append({"bufferView": vi, "componentType": 5123, "normalized": True, "count": len(qu), "type": "VEC2"})
                else:
                    vi = bw.add(uv.astype(np.float32).tobytes(), stride=8, target=34962)
                    out["accessors"].append({"bufferView": vi, "componentType": 5126, "count": len(uv), "type": "VEC2"})
                attrs["TEXCOORD_0"] = len(out["accessors"]) - 1
            np_ = {"attributes": attrs, "mode": p.get("mode", 4)}
            if "material" in p:
                np_["material"] = p["material"]
            if "indices" in p:
                idx = accessor(p["indices"]).reshape(-1).astype(np.uint32)
                if idx.max() < 65535:
                    vi = bw.add(idx.astype(np.uint16).tobytes(), target=34963)
                    out["accessors"].append({"bufferView": vi, "componentType": 5123, "count": len(idx), "type": "SCALAR"})
                else:
                    vi = bw.add(idx.tobytes(), target=34963)
                    out["accessors"].append({"bufferView": vi, "componentType": 5125, "count": len(idx), "type": "SCALAR"})
                np_["indices"] = len(out["accessors"]) - 1
            prims.append(np_)
        out["meshes"].append({"name": mesh.get("name", ""), "primitives": prims})

    for n in src["nodes"]:
        out["nodes"].append({k: v for k, v in n.items() if k in ("name", "translation", "rotation", "scale", "matrix", "children")})
    # world matrices for bounds (parents first)
    parent_of = {}
    for i, n in enumerate(src["nodes"]):
        for ch in n.get("children", []):
            parent_of[ch] = i

    def world(i):
        m = node_matrix(src["nodes"][i])
        return (world(parent_of[i]) @ m) if i in parent_of else m

    for ni, n in enumerate(src["nodes"]):
        if "mesh" in n:
            c, s = mesh_quant[n["mesh"]]
            out["nodes"].append({"name": (n.get("name", "") + "_q"), "mesh": n["mesh"], "translation": [float(v) for v in c], "scale": [s, s, s]})
            out["nodes"][ni].setdefault("children", []).append(len(out["nodes"]) - 1)
            m = world(ni)
            mn, mx = mesh_bounds[n["mesh"]]
            corners = np.array([[x, y, z, 1] for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])])
            wc = (m @ corners.T).T[:, :3]
            world_min = np.minimum(world_min, wc.min(0))
            world_max = np.maximum(world_max, wc.max(0))

    if height:
        cur = float(world_max[1] - world_min[1])
        s = height / cur if cur > 0 else 1.0
        if abs(s - 1) > 0.15:
            out["nodes"].append({"name": "unit_fix", "scale": [s, s, s], "children": list(out["scenes"][out["scene"]]["nodes"])})
            out["scenes"][out["scene"]] = {"name": "Scene", "nodes": [len(out["nodes"]) - 1]}
            world_min, world_max = world_min * s, world_max * s
            print(f"  unit fix x{s:.3f} applied to {model_dir.name}", file=sys.stderr)

    blob = bw.blob()
    out["bufferViews"] = bw.views
    out["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(out, separators=(",", ":")).encode("utf-8")
    js += b" " * ((-len(js)) % 4)
    glb = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob))
    glb += struct.pack("<II", len(js), 0x4E4F534A) + js
    glb += struct.pack("<II", len(blob), 0x004E4942) + blob
    return glb, [float(v) for v in world_min] + [float(v) for v in world_max]


def file_hash(*paths):
    h = hashlib.sha1()
    for p in paths:
        h.update(str(p).encode())
        h.update(str(pathlib.Path(p).stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--js-root", action="append", default=[], help="directories searched for manifest js paths")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    manifest = json.load(open(a.manifest))
    assets = pathlib.Path(a.assets)
    cache = pathlib.Path(a.out + ".cache")
    cache.mkdir(parents=True, exist_ok=True)
    pack = {"models": {}, "textures": {}, "hdri": None, "js": {}}

    for mid, spec in manifest.get("models", {}).items():
        d = assets / "models" / mid
        webp = manifest.get("webp", True)
        key = file_hash(*sorted(p for p in d.rglob("*") if p.is_file())) + f"-{spec['size']}-{spec.get('q', 78)}-h{spec.get('height', 0)}-v2" + ("" if webp else "-jpg")
        cf = cache / f"model-{mid}-{key}.json"
        if cf.exists():
            pack["models"][mid] = json.load(open(cf))
        else:
            glb, bbox = pack_model(d, spec["size"], spec.get("q", 78), spec.get("qn", 85), spec.get("height"), webp)
            entry = {"glb": b64(gz(glb)), "bbox": bbox, "raw": len(glb)}
            json.dump(entry, open(cf, "w"))
            pack["models"][mid] = entry
        e = pack["models"][mid]
        print(f"model {mid:28s} glb={e['raw']/1e6:.2f}MB gz+b64={len(e['glb'])/1e6:.2f}MB bbox={[round(v,2) for v in e['bbox']]}", file=sys.stderr)

    for tid, spec in manifest.get("textures", {}).items():
        d = assets / "textures" / tid
        files = sorted(d.glob("*.jpg"))
        key = file_hash(*files) + f"-{spec['size']}" + ("" if manifest.get("webp", True) else "-jpg")
        cf = cache / f"tex-{tid}-{key}.json"
        if cf.exists():
            pack["textures"][tid] = json.load(open(cf))
        else:
            entry = {}
            for f in files:
                kind = {"Diffuse": "diff", "nor_gl": "nor", "arm": "arm"}.get(f.stem)
                if kind:
                    if manifest.get("webp", True):
                        entry[kind] = b64(webp_bytes(f, spec["size"], 86 if kind == "nor" else 80))
                    else:
                        entry[kind] = b64(classic_bytes(f, spec["size"], 88 if kind == "nor" else 82)[0])
            json.dump(entry, open(cf, "w"))
            pack["textures"][tid] = entry
        print(f"texture {tid:26s} {sum(len(v) for v in pack['textures'][tid].values())/1e6:.2f}MB", file=sys.stderr)

    if manifest.get("hdri"):
        pack["hdri"] = b64(gz((assets / "hdri" / manifest["hdri"]).read_bytes()))
        print(f"hdri {len(pack['hdri'])/1e6:.2f}MB", file=sys.stderr)

    roots = [pathlib.Path(r) for r in a.js_root]
    for spec, rel in manifest.get("js", {}).items():
        path = next((r / rel for r in roots if (r / rel).exists()), None)
        if path is None:
            raise SystemExit(f"js module not found: {rel} (roots {roots})")
        txt = path.read_text(encoding="utf-8")
        pack["js"][spec] = b64(gz(txt.encode("utf-8")))
        print(f"js {spec:52s} {len(pack['js'][spec])/1e6:.2f}MB", file=sys.stderr)

    json.dump(pack, open(a.out, "w"))
    print(f"wrote {a.out}: {pathlib.Path(a.out).stat().st_size/1e6:.1f}MB", file=sys.stderr)


if __name__ == "__main__":
    main()
