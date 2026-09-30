/**
 * Foliage — the actual leaf and needle geometry.
 *
 * A broadleaf is a short folded/curled strip with a parametric outline; a
 * needle fan is a thin twig carrying dozens of single-quad needles in either a
 * flat comb or a radial bottlebrush. Both append into a MeshForge through a
 * supplied transform (local +z runs outward, +y is leaf-up). These meshes are
 * only ever drawn once — into the canopy atlas — so a little extra detail here
 * is cheap and pays off across every card.
 *
 * vdata: x hue, y sway flex, z sway phase, w shade (crown depth applied later).
 */

import { Matrix4, Vector3 } from 'three';
import type { SeedStream } from './SeedStream';
import type { MeshForge } from './MeshForge';
import type { LeafForm } from './Botany';

const POS = new Vector3();
const NRM = new Vector3();
// scratch reused across every needle in a fan (no per-needle allocation)
const BASE = new Vector3();
const DIR = new Vector3();
const TIP = new Vector3();
const SPAN = new Vector3();
const NEEDLE_N = new Vector3();

function place(
  forge: MeshForge,
  m: Matrix4,
  px: number, py: number, pz: number,
  nx: number, ny: number, nz: number,
  u: number, v: number,
  d0: number, d1: number, d2: number, d3: number,
): number {
  POS.set(px, py, pz).applyMatrix4(m);
  NRM.set(nx, ny, nz).transformDirection(m);
  return forge.emit(POS.x, POS.y, POS.z, NRM.x, NRM.y, NRM.z, u, v, d0, d1, d2, d3);
}

/**
 * One broadleaf: a 4-row strip along +z, three verts per row (−w, mid, +w),
 * folded along the midrib and curled toward the tip — roughly 18 tris.
 */
export function appendLeaf(
  forge: MeshForge,
  m: Matrix4,
  form: LeafForm,
  hue: number,
  flex: number,
  phase: number,
  shade: number,
): void {
  const ROWS = 4;
  const L = form.len;
  const W = form.width;
  const stem = L * 0.14;
  const rows: number[][] = [];
  for (let i = 0; i <= ROWS; i++) {
    const s = i / ROWS;
    const w = W * Math.pow(Math.sin(Math.PI * Math.min(1, s * 0.86 + 0.07)), form.pointiness);
    const z = stem + s * (L - stem);
    const dropY = -form.curl * s * s * L;
    const foldY = form.fold * w;
    const row: number[] = [];
    row.push(place(forge, m, -w, dropY, z, -form.fold * 0.8, 1, 0, 0, s, hue, flex, phase, shade * 0.92));
    row.push(place(forge, m, 0, dropY + foldY * 0.35, z, 0, 1, form.curl * s, 0.5, s, hue, flex, phase, shade));
    row.push(place(forge, m, w, dropY - foldY, z, form.fold * 0.8, 1, 0, 1, s, hue, flex, phase, shade * 0.92));
    rows.push(row);
  }
  for (let i = 0; i < ROWS; i++) {
    const a = rows[i] as number[];
    const b = rows[i + 1] as number[];
    forge.face4(a[0] as number, b[0] as number, b[1] as number, a[1] as number);
    forge.face4(a[1] as number, b[1] as number, b[2] as number, a[2] as number);
  }
  // petiole
  const q0 = place(forge, m, -W * 0.06, 0, 0, 0, 1, 0, 0.45, 0, hue, flex * 0.7, phase, shade);
  const q1 = place(forge, m, W * 0.06, 0, 0, 0, 1, 0, 0.55, 0, hue, flex * 0.7, phase, shade);
  const r0 = rows[0] as number[];
  forge.face4(q0, r0[0] as number, r0[1] as number, q1);
  forge.face(q1, r0[1] as number, r0[2] as number);
}

/**
 * Needle fan: a sagging twig plus `needles` single-quad needles, laid out as a
 * flat ±comb or a radial bottlebrush. Local axis runs along +z.
 */
export function appendNeedleFan(
  forge: MeshForge,
  m: Matrix4,
  form: LeafForm,
  reach: number,
  rng: SeedStream,
  hue: number,
  flex: number,
  phase: number,
  shade: number,
): void {
  const SEGS = 4;
  const L = reach;
  // sagging stem polyline
  const stem: Vector3[] = [];
  let dy = 0;
  let z = 0;
  let y = 0;
  for (let i = 0; i <= SEGS; i++) {
    stem.push(new Vector3(0, y, z));
    const seg = L / SEGS;
    dy -= 0.16 * (i / SEGS);
    const len = Math.hypot(dy, 1);
    z += (1 / len) * seg;
    y += (dy / len) * seg;
  }
  // stem as a thin two-sided strip (reads as a twig, cheaper than a tube)
  const half = L * 0.012 + 0.002;
  const strip: number[][] = [];
  for (let i = 0; i <= SEGS; i++) {
    const p = stem[i] as Vector3;
    const w = half * (1 - (i / SEGS) * 0.7);
    strip.push([
      place(forge, m, p.x - w, p.y, p.z, 0, 1, 0, 0.48, i / SEGS, hue, flex, phase, shade * 0.85),
      place(forge, m, p.x + w, p.y, p.z, 0, 1, 0, 0.52, i / SEGS, hue, flex, phase, shade * 0.85),
    ]);
  }
  for (let i = 0; i < SEGS; i++) {
    const a = strip[i] as number[];
    const b = strip[i + 1] as number[];
    forge.face4(a[0] as number, b[0] as number, b[1] as number, a[1] as number);
  }

  const count = form.needles;
  const nl = form.len;
  const nw = form.width;
  const bottlebrush = form.radial > 0.5;
  for (let i = 0; i < count; i++) {
    const s = (i + 0.5) / count;
    const fi = s * SEGS;
    const i0 = Math.min(SEGS - 1, Math.floor(fi));
    const f = fi - i0;
    BASE.copy(stem[i0] as Vector3).lerp(stem[i0 + 1] as Vector3, f);
    const side = i % 2 === 0 ? 1 : -1;
    const layer = i % 4 < 2 ? 1 : 0;
    const az = bottlebrush
      ? rng.unit() * Math.PI * 2
      : side * (1.05 + (rng.unit() - 0.5) * 0.85);
    const elev = bottlebrush
      ? (rng.unit() - 0.2) * 1.1
      : (layer === 1 ? 0.42 : 0.02) + (rng.unit() - 0.5) * 0.3;
    const sweep = (rng.unit() - 0.5) * 0.3 + s * 0.55;
    DIR.set(
      Math.sin(az) * Math.cos(elev),
      Math.sin(elev),
      Math.cos(az) * Math.cos(elev) * 0.35 + sweep,
    ).normalize();
    const len = nl * (0.75 + rng.unit() * 0.5) * (0.65 + 0.35 * Math.sin(Math.PI * Math.min(1, s * 1.18)));
    TIP.copy(BASE).addScaledVector(DIR, len);
    SPAN.set(-DIR.z, 0, DIR.x).normalize().multiplyScalar(nw * 0.5);
    NEEDLE_N.set(0, 1, 0).addScaledVector(DIR, -0.25).normalize();
    const hn = hue + (rng.unit() - 0.5) * 0.5;
    const a0 = place(forge, m, BASE.x - SPAN.x, BASE.y, BASE.z - SPAN.z, NEEDLE_N.x, NEEDLE_N.y, NEEDLE_N.z, 0, 0, hn, flex, phase, shade * 0.9);
    const a1 = place(forge, m, BASE.x + SPAN.x, BASE.y, BASE.z + SPAN.z, NEEDLE_N.x, NEEDLE_N.y, NEEDLE_N.z, 1, 0, hn, flex, phase, shade * 0.9);
    const b0 = place(forge, m, TIP.x - SPAN.x * 0.25, TIP.y, TIP.z - SPAN.z * 0.25, NEEDLE_N.x, NEEDLE_N.y, NEEDLE_N.z, 0.4, 1, hn, flex * 1.15, phase, shade);
    const b1 = place(forge, m, TIP.x + SPAN.x * 0.25, TIP.y, TIP.z + SPAN.z * 0.25, NEEDLE_N.x, NEEDLE_N.y, NEEDLE_N.z, 0.6, 1, hn, flex * 1.15, phase, shade);
    forge.face4(a0, b0, b1, a1);
  }
}
