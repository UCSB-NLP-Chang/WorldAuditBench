#!/usr/bin/env python3
"""Preview conversion of the Intel 'NewSponza' mirror (rGovers/IcarianSponza: 161 Blender-exported OBJ parts +
26 4K BaseColor PNGs, material defs without object defs) into one GLB with 2K WebP textures, so it can be
rendered in the harness' three.js next to the Khronos Sponza.  Material per part is inferred from the OBJ
file name suffix (…_<Tag>.obj) -> texture (the object->material defs are not in the mirror).
Usage: intel_sponza_to_glb.py --src <IcarianSponza/Project> --out intel_sponza.glb [--tex 2048]
"""
import argparse, io, json, re, struct, sys
from pathlib import Path
import numpy as np
from PIL import Image

TAG2TEX = {  # OBJ name suffix -> BaseColor texture
    "Arch": "arch_stone_wall_01", "BrickWall": "brickwall_01", "BrickWall2": "brickwall_02",
    "CeilingPlaster": "ceiling_plaster_01", "CeilingPlaster2": "ceiling_plaster_02",
    "ColumnBase": "col_1stfloor", "ColumnBrickWall": "col_brickwall_01", "ColumnHead": "col_head_1stfloor",
    "ColumnHead2": "col_head_2ndfloor_02", "ColumnHead3": "col_head_2ndfloor_03",
    "StoneFrame": "door_stoneframe_01", "StoneFrame2": "door_stoneframe_02", "Floor": "floor_tiles_01",
    "LionHead": "lionhead_01", "Metal": "metal_door_01", "Ornament": "ornament_01", "Roof": "roof_tiles_01",
    "StoneTile": "stone_01_tile", "StoneTiles": "stone_01_tile", "Tile": "stone_01_tile", "StoneTrims": "stone_trims_01",
    "StoneTrims2": "stone_trims_02", "Stones": "stones_2ndfloor_01", "StoneWall": "stones_2ndfloor_01",
    "Window": "window_frame_01", "WoodDoor": "wood_door_01", "Wood": "wood_tile_01", "Glass": None,
}


def parse_obj(path):
    v, vt, vn, faces = [], [], [], []
    for line in open(path, "r", errors="ignore"):
        if line.startswith("v "):
            v.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "):
            t = line.split()[1:3]; vt.append([float(t[0]), float(t[1])])
        elif line.startswith("vn "):
            vn.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            idx = []
            for tok in line.split()[1:]:
                p = tok.split("/")
                idx.append((int(p[0]) - 1, int(p[1]) - 1 if len(p) > 1 and p[1] else -1, int(p[2]) - 1 if len(p) > 2 and p[2] else -1))
            for k in range(1, len(idx) - 1):   # fan triangulation
                faces.append((idx[0], idx[k], idx[k + 1]))
    return np.array(v, np.float32), np.array(vt, np.float32) if vt else None, np.array(vn, np.float32) if vn else None, faces


def build_mesh(v, vt, vn, faces):
    key = {}
    pos, uv, nor, ind = [], [], [], []
    for tri in faces:
        for (a, b, c) in tri:
            k = (a, b, c)
            i = key.get(k)
            if i is None:
                i = len(pos); key[k] = i
                pos.append(v[a]); uv.append(vt[b] if vt is not None and b >= 0 else (0, 0)); nor.append(vn[c] if vn is not None and c >= 0 else (0, 1, 0))
            ind.append(i)
    P = np.array(pos, np.float32); U = np.array(uv, np.float32); N = np.array(nor, np.float32)
    U[:, 1] = 1.0 - U[:, 1]
    # the mirror's OBJs come out upside down in a Y-up viewer: rotate 180 deg about X (y -> -y, z -> -z)
    P[:, 1] *= -1; P[:, 2] *= -1; N[:, 1] *= -1; N[:, 2] *= -1
    return P, U, N, np.array(ind, np.uint32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--out", required=True); ap.add_argument("--tex", type=int, default=2048); ap.add_argument("--q", type=int, default=80)
    a = ap.parse_args()
    src = Path(a.src)
    objs = sorted((src / "Models").glob("*.obj"))
    texdir = src / "Textures"
    # textures -> webp
    images, tex_index = [], {}
    bufs = []  # (bytes, target)
    def add_buf(data, target=None, stride=None):
        bufs.append((data, target, stride)); return len(bufs) - 1
    def texture_for(tag):
        name = TAG2TEX.get(tag)
        if name is None:
            return None
        if name in tex_index:
            return tex_index[name]
        p = texdir / f"{name}_BaseColor.png"
        if not p.exists():
            print("missing texture", p, file=sys.stderr); return None
        im = Image.open(p).convert("RGB")
        if max(im.size) > a.tex:
            im = im.resize((a.tex, a.tex), Image.LANCZOS)
        b = io.BytesIO(); im.save(b, "WEBP", quality=a.q, method=6)
        images.append({"bufferView": add_buf(b.getvalue()), "mimeType": "image/webp", "name": name})
        tex_index[name] = len(images) - 1
        print(f"texture {name}: {im.size} {len(b.getvalue())/1e6:.2f} MB", file=sys.stderr)
        return tex_index[name]
    materials, mat_index = [], {}
    meshes, nodes, accessors, views_meta = [], [], [], []
    def tag_of(stem):
        toks = stem.split("_")
        last = toks[-1]
        floor2 = any(t == "2ndFloor" for t in toks)
        if last == "Head": return "ColumnHead2" if floor2 else "ColumnHead"
        if last == "Base": return "ColumnBase"
        if last == "Plaster": return "CeilingPlaster2" if floor2 else "CeilingPlaster"
        if last in ("Tiles", "Tile", "StoneTiles"): return "StoneTile"
        if last == "Stone": return "Floor"
        if last in ("Stones", "StoneWall"): return "Stones"
        if last in ("1stFloor", "2ndFloor"): return "Ornament"     # Sponza_OrnamentStones_1stFloor
        base = re.sub(r"\d+$", "", last)
        return last if last in TAG2TEX else (base if base in TAG2TEX else last)
    for obj in objs:
        tag = tag_of(obj.stem)
        v, vt, vn, faces = parse_obj(obj)
        if len(faces) == 0:
            continue
        P, U, N, I = build_mesh(v, vt, vn, faces)
        if tag not in mat_index:
            ti = texture_for(tag)
            m = {"name": tag, "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.9}, "doubleSided": tag in ("Glass",)}
            if ti is not None:
                m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": ti}
            elif tag == "Glass":
                m["pbrMetallicRoughness"]["baseColorFactor"] = [0.6, 0.75, 0.85, 0.35]; m["alphaMode"] = "BLEND"
            else:
                m["pbrMetallicRoughness"]["baseColorFactor"] = [0.6, 0.6, 0.6, 1.0]
            materials.append(m); mat_index[tag] = len(materials) - 1
        attrs = {}
        for name, arr, ncomp, ctype in (("POSITION", P, 3, 5126), ("NORMAL", N, 3, 5126), ("TEXCOORD_0", U, 2, 5126)):
            bv = add_buf(arr.astype(np.float32).tobytes(), 34962)
            acc = {"bufferView": bv, "componentType": ctype, "count": int(len(arr)), "type": {3: "VEC3", 2: "VEC2"}[ncomp]}
            if name == "POSITION":
                acc["min"] = [float(x) for x in arr.min(0)]; acc["max"] = [float(x) for x in arr.max(0)]
            accessors.append(acc); attrs[name] = len(accessors) - 1
        bv = add_buf(I.astype(np.uint32).tobytes(), 34963)
        accessors.append({"bufferView": bv, "componentType": 5125, "count": int(len(I)), "type": "SCALAR"})
        meshes.append({"name": obj.stem, "primitives": [{"attributes": attrs, "indices": len(accessors) - 1, "material": mat_index[tag]}]})
        nodes.append({"name": obj.stem, "mesh": len(meshes) - 1})
        print(f"{obj.stem:45s} tag={tag:16s} tris={len(I)//3}", file=sys.stderr)
    # assemble binary
    blob = bytearray(); bufferViews = []
    for data, target, stride in bufs:
        off = len(blob); blob += data; blob += b"\0" * ((-len(data)) % 4)
        bv = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target: bv["target"] = target
        bufferViews.append(bv)
    gltf = {"asset": {"version": "2.0", "generator": "intel_sponza_to_glb"}, "extensionsUsed": ["EXT_texture_webp"], "extensionsRequired": ["EXT_texture_webp"],
            "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "materials": materials,
            "textures": [{"sampler": 0, "extensions": {"EXT_texture_webp": {"source": i}}} for i in range(len(images))], "images": images,
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
            "accessors": accessors, "bufferViews": bufferViews, "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(gltf, separators=(",", ":")).encode(); js += b" " * ((-len(js)) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)) + struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    Path(a.out).write_bytes(out)
    print(f"wrote {a.out}: {len(out)/1e6:.1f} MB, {len(meshes)} parts, {len(materials)} materials, {len(images)} textures", file=sys.stderr)


if __name__ == "__main__":
    main()
