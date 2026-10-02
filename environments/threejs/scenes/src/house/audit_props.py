#!/usr/bin/env python3
"""Audit every placed prop in the house build (run after build.py): gap between the prop's bbox bottom and whatever is below it,
sampled at the footprint centre, corners and edge midpoints (rays cast from above the prop, first hit on another
object = the support surface). Flags floating (gap > 2 cm), sunk-in (> 3 cm) and overhanging (< 5/9 samples supported)
props. Single-corner hits on tall neighbours (chairs under a table, a wall skirting) are expected false positives -
check the flagged ones visually. Usage: .venv/bin/python environments/threejs/scenes/src/house/audit_props.py [html]"""
import sys, json, pathlib
REPO = pathlib.Path(__file__).resolve().parents[5]
from playwright.sync_api import sync_playwright
f = sys.argv[1] if len(sys.argv) > 1 else str(REPO / 'environments/threejs/scenes/09_sims_house_builder_constrained.html')
ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
JS = r"""
() => {
  const B = window.BenchmarkWorld, T = B.THREE;
  const out = [];
  const ray = new T.Raycaster();
  for (let level = 0; level < 2; level++) {
    B.setFloor(level, false);
    const floor = B.floors[level];
    const solids = [];
    B.root.traverse(o => { if (o.isMesh && o.visible) solids.push(o); });
    for (const obj of floor.children) {
      if (!obj.userData || !obj.userData.bbox) continue;      // only cloned Poly Haven props
      obj.updateWorldMatrix(true, true);
      const bb = new T.Box3().setFromObject(obj);
      if (!isFinite(bb.min.y)) continue;
      const own = new Set(); obj.traverse(o => own.add(o));
      const cands = solids.filter(o => !own.has(o));
      const sx = bb.max.x - bb.min.x, sz = bb.max.z - bb.min.z;
      const inset = Math.min(0.01, sx * 0.1, sz * 0.1);
      const pts = [[0.5, 0.5], [0, 0], [1, 0], [0, 1], [1, 1], [0.5, 0], [0.5, 1], [0, 0.5], [1, 0.5]].map(([u, v]) =>
        [bb.min.x + inset + u * (sx - 2 * inset), bb.min.z + inset + v * (sz - 2 * inset)]);
      // cast from above the prop's top: first hit on another object = the support surface under that point
      const gaps = pts.map(([x, z]) => {
        ray.set(new T.Vector3(x, bb.max.y + 0.05, z), new T.Vector3(0, -1, 0)); ray.far = 2.5;
        const h = ray.intersectObjects(cands, true).find(i => i.point.y <= bb.max.y + 0.001);
        return h ? +(bb.min.y - h.point.y).toFixed(3) : null;   // >0 gap (floating), <0 sunk into the support
      });
      const supported = gaps.filter(g => g !== null && g <= 0.02 && g >= -0.03).length;
      const minGap = Math.min(...gaps.filter(g => g !== null).concat([9]));
      out.push({ level, name: obj.name, pos: obj.position.toArray().map(v => +v.toFixed(2)), rotY: +obj.rotation.y.toFixed(2),
        bbox: [bb.min.x, bb.min.y, bb.min.z, bb.max.x, bb.max.y, bb.max.z].map(v => +v.toFixed(3)),
        gaps, supported, minGap });
    }
  }
  B.setFloor(0, false);
  return out;
}"""
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=ARGS); pg = b.new_page(viewport={'width': 960, 'height': 600})
    pg.goto('file://' + f, wait_until='load', timeout=300000)
    for _ in range(120):
        if pg.evaluate("() => window.BenchmarkWorld && window.BenchmarkWorld.ready"): break
        pg.wait_for_timeout(500)
    res = pg.evaluate(JS); b.close()
json.dump(res, open("house_prop_audit.json", "w"), indent=1)
MOUNTED = ('PICTURE', 'CLOCK', 'CEILING', 'MIRROR', 'PENDANT', 'CHANDELIER')
bad = [r for r in res if not any(m in r['name'] for m in MOUNTED) and (r['minGap'] > 0.02 or r['supported'] < 5 or min(g for g in r['gaps'] if g is not None) < -0.03)]
print(f"{len(res)} props audited (wall/ceiling-mounted skipped), {len(bad)} suspicious (floating: min gap > 2 cm, or fewer than 5/9 footprint samples supported)")
for r in sorted(bad, key=lambda r: (r['level'], -r['minGap'])):
    print(f"L{r['level']} {r['name']:<28} pos={r['pos']} rot={r['rotY']:+.2f} bottomY={r['bbox'][1]:.3f} minGap={r['minGap']:.3f} supported={r['supported']}/9 gaps={r['gaps']}")
