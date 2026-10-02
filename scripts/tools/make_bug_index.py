#!/usr/bin/env python3
"""bugs.html - one page that links every bug case of every environment (put it next to the built HTML files, e.g. in the
release bundle).  Each link opens the environment file with `?bug=<id>`; the review overlay inside the page lists the
other cases, describes the planted defect and jumps to it.  Thumbnails come from reports/<suite>/catalog when present.

usage: make_bug_index.py [--out environments/threejs/scenes/bugs.html]
"""
import argparse, base64, io, json, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
ENVS = [
    ("sp", "Sponza atrium", "00_sponza_constrained.html", None),
    ("hs", "Family house", "09_sims_house_builder_constrained.html", None),
    ("wt", "Reef dive", "10_beautiful_water_clean_constrained.html", "reports/water-suite/catalog"),
    ("af", "Sketchbook airfield", "03_sketchbook_airfield_constrained.html", "reports/airfield-suite/catalog"),
    ("wl", "Beyond Fable wilderness", "13_beyond_fable_wilderness_constrained.html", "reports/wilderness-suite/catalog"),
    ("ct", "Mistwood Cottage", "01_mistwood_cottage_constrained.html", "reports/cottage-suite/catalog"),
]


def thumb(png):
    try:
        from PIL import Image
        im = Image.open(png).convert("RGB"); im.thumbnail((240, 150)); buf = io.BytesIO(); im.save(buf, "JPEG", quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(REPO / "environments/threejs/scenes" / "bugs.html")); a = ap.parse_args()
    parts = ["""<!doctype html><html><head><meta charset="utf-8"><title>Bug catalogue - all environments</title>
<style>body{font:14px/1.45 system-ui,sans-serif;margin:0;padding:24px;background:#14161a;color:#e8e8e8}h1{margin:0 0 6px}h2{margin:28px 0 8px;color:#9ec5ff}
p.lead{color:#aaa;max-width:900px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
a.card{display:block;background:#1e2127;border:1px solid #2c3038;border-radius:10px;padding:8px;color:inherit;text-decoration:none}a.card:hover{border-color:#9ec5ff}
a.card img{width:100%;border-radius:6px;display:block;margin-bottom:6px;background:#000}a.card b{color:#ffd166}a.card small{color:#aaa;display:block;margin-top:2px}
.file{color:#888;font-size:12px}.clean{border-style:dashed}</style></head><body>
<h1>Bug catalogue</h1><p class="lead">Every card opens the environment with that case injected (<code>?bug=&lt;id&gt;</code>). Inside the page the
panel at the top right describes the defect, lists the other cases, jumps next to the answer and toggles a marker beam.
Walk with WASD, look with the mouse; there is no jump. Keep this file next to the environment files.</p>"""]
    for prefix, title, file, catalog in ENVS:
        cases = []
        for p in sorted((REPO / "environments/threejs/runtime" / "configs").glob(f"{prefix}[0-9][0-9]-*.json")):
            if p.name.endswith(".answers.json") or p.name.endswith("-near.json"): continue
            c = json.loads(p.read_text()); ans_p = p.with_name(p.name[:-5] + ".answers.json"); ans = json.loads(ans_p.read_text()) if ans_p.exists() else []
            cases.append((c["name"], ans[0]["name"] if ans else c.get("meta", {}).get("desc", ""), ans[0]["where"] if ans else c.get("meta", {}).get("desc", "")))
        parts.append(f'<h2>{title} <span class="file">{file} · {len(cases)} cases</span></h2><div class="grid">')
        for cid, name, where in cases:
            img = thumb(REPO / catalog / f"{cid}.png") if catalog else None
            cls = "card clean" if cid.endswith("00-clean") else "card"
            parts.append(f'<a class="{cls}" href="{file}?bug={cid}">{f"<img src={img!r} alt=>" if img else ""}<b>{cid}</b> {name}<small>{where}</small></a>')
        parts.append("</div>")
    parts.append("</body></html>")
    out = pathlib.Path(a.out); out.write_text("\n".join(parts), encoding="utf-8"); print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
