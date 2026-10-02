/**
 * Undergrowth — everything that grows below the canopy.
 *
 * Shrubs reuse the full tree grammar with bush-tuned profiles, grown as a few
 * leaning stems and merged into one bark+foliage pair. Ferns are rosettes of
 * arched frond cards. Flowers are bespoke little builders with real petal
 * geometry. All share the MeshForge / card pipeline, so nothing here needs an
 * external asset.
 */

import { Matrix4, Quaternion, Vector3 } from 'three';
import type { BufferGeometry } from 'three';
import type { SeedStream } from './SeedStream';
import { assembleTree } from './Assemble';
import { MeshForge } from './MeshForge';
import type { Tuft, TreeProfile } from './Botany';
import { scatterCards } from './CardAtlas';

// ---------------------------------------------------------------------------
// Shrub profiles (bush-tuned, same grammar as trees)
// ---------------------------------------------------------------------------

const bushTiers = (gnarl: number): TreeProfile['tiers'] => [
  {
    perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
    angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
    segments: 5, jitter: 0.18 * gnarl, upBias: 0.06, sag: 0, tipLift: 0, taperPow: 0.9,
  },
  {
    perMeter: 4.5, whorlCount: 0, spanStart: 0.2, spanEnd: 1.0,
    angleRoot: 1.0, angleEnd: 0.5, lenScale: 0.62, lenVar: 0.4, radScale: 0.55,
    segments: 4, jitter: 0.16 * gnarl, upBias: 0.1, sag: 0.2, tipLift: 0.1, taperPow: 0.85,
  },
  {
    perMeter: 7.0, whorlCount: 0, spanStart: 0.2, spanEnd: 1.0,
    angleRoot: 0.85, angleEnd: 0.5, lenScale: 0.45, lenVar: 0.4, radScale: 0.55,
    segments: 2, jitter: 0.2 * gnarl, upBias: 0.05, sag: 0.15, tipLift: 0.05, taperPow: 0.85,
    flatten: 0.5,
  },
];

export const BUSH_HAZEL: TreeProfile = {
  id: 'bushHazel',
  label: 'Hazel shrub',
  kind: 'broadleaf',
  height: [1.9, 2.9],
  girth: 0.02,
  crown: 'dome',
  crownLean: 0.35,
  tiers: bushTiers(1),
  canopy: {
    style: 'leafTuft',
    tier: 2,
    stride: 0.09,
    fromT: 0.15,
    sizeRange: [0.08, 0.13],
    tilt: 0.9,
    tuftRange: [2, 3],
    domeBlend: 0.6,
    twoRanked: true,
    plate: { mode: 'cross', scale: 2.3 },
    blade: { len: 1.0, width: 0.6, pointiness: 1.2, fold: 0.3, curl: 0.2, needles: 0, radial: 0 },
  },
  buttress: { amp: 0.2, rise: 0.3, lobes: 3 },
  barkTiling: 2,
  leafColor: { r: 0.055, g: 0.125, b: 0.03, hueVar: 0.24 },
  woodTint: { r: 0.4, g: 0.34, b: 0.27 },
  snapAt: 0,
  stubOdds: 0.02,
};

export const BUSH_PINKFLOWER: TreeProfile = {
  id: 'bushPink',
  label: 'Pink flowering shrub',
  kind: 'broadleaf',
  height: [1.5, 2.4],
  girth: 0.018,
  crown: 'dome',
  crownLean: 0.3,
  tiers: bushTiers(1.2),
  canopy: {
    style: 'leafTuft',
    tier: 2,
    stride: 0.055,
    fromT: 0.12,
    sizeRange: [0.09, 0.14],
    tilt: 0.95,
    tuftRange: [2, 3],
    domeBlend: 0.62,
    twoRanked: true,
    plate: { mode: 'cross', scale: 2.3 },
    blade: { len: 1.0, width: 0.5, pointiness: 1.25, fold: 0.28, curl: 0.18, needles: 0, radial: 0 },
  },
  buttress: { amp: 0.2, rise: 0.3, lobes: 3 },
  barkTiling: 2,
  leafColor: { r: 0.05, g: 0.115, b: 0.032, hueVar: 0.2 },
  bloom: { r: 0.58, g: 0.16, b: 0.24, frac: 0.56 },
  woodTint: { r: 0.38, g: 0.32, b: 0.26 },
  snapAt: 0,
  stubOdds: 0.02,
};

export const BUSH_JUNIPER: TreeProfile = {
  id: 'bushJuniper',
  label: 'Juniper mound',
  kind: 'conifer',
  height: [0.9, 1.5],
  girth: 0.03,
  crown: 'dome',
  crownLean: 0.4,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 4, jitter: 0.3, upBias: -0.12, sag: 0, tipLift: 0.05, taperPow: 0.8,
    },
    {
      perMeter: 7, whorlCount: 0, spanStart: 0.05, spanEnd: 1.0,
      angleRoot: 1.5, angleEnd: 0.7, lenScale: 0.85, lenVar: 0.4, radScale: 0.6,
      segments: 4, jitter: 0.22, upBias: 0.12, sag: 0.25, tipLift: 0.18, taperPow: 0.85,
    },
    {
      perMeter: 8, whorlCount: 0, spanStart: 0.2, spanEnd: 1.0,
      angleRoot: 0.9, angleEnd: 0.5, lenScale: 0.4, lenVar: 0.4, radScale: 0.55,
      segments: 2, jitter: 0.2, upBias: 0.08, sag: 0.1, tipLift: 0.1, taperPow: 0.85,
      flatten: 0.6,
    },
  ],
  canopy: {
    style: 'needleFan',
    tier: 2,
    stride: 0.07,
    fromT: 0.1,
    sizeRange: [0.12, 0.2],
    tilt: 0.55,
    tuftRange: [1, 1],
    domeBlend: 0.6,
    twoRanked: true,
    plate: { mode: 'flat', scale: 2.5 },
    blade: { len: 0.05, width: 0.012, pointiness: 1, fold: 0, curl: 0, needles: 26, radial: 0 },
  },
  buttress: { amp: 0.25, rise: 0.25, lobes: 3 },
  barkTiling: 2,
  leafColor: { r: 0.05, g: 0.095, b: 0.055, hueVar: 0.18 },
  woodTint: { r: 0.35, g: 0.3, b: 0.24 },
  snapAt: 0,
  stubOdds: 0.05,
};

export const SHRUB_CATALOG: readonly TreeProfile[] = [
  BUSH_HAZEL,
  BUSH_PINKFLOWER,
  BUSH_JUNIPER,
];

/** Multi-stem shrub: 3–5 leaning stems merged into one bark+foliage pair. */
export function assembleShrub(
  profile: TreeProfile,
  rng: SeedStream,
): { bark: BufferGeometry; foliage: BufferGeometry | null } {
  const stems = 3 + rng.index(3);
  const barkForge = new MeshForge();
  const folForge = new MeshForge();
  const m = new Matrix4();
  const q = new Quaternion();
  const p = new Vector3();
  let hasFoliage = false;
  for (let i = 0; i < stems; i++) {
    const a = (i / stems) * Math.PI * 2 + rng.unit();
    const lean = 0.12 + rng.unit() * 0.22;
    const stem = assembleTree(profile, rng.derive(`stem${i}`), {
      bias: {
        leanX: Math.cos(a) * lean,
        leanZ: Math.sin(a) * lean,
        maturity: 0.4 + rng.unit() * 0.5,
      },
    });
    p.set(Math.cos(a) * 0.09, 0, Math.sin(a) * 0.09);
    q.identity();
    m.compose(p, q, new Vector3(1, 1, 1));
    mergeInto(barkForge, stem.bark, m);
    if (stem.foliage) {
      mergeInto(folForge, stem.foliage, m);
      hasFoliage = true;
    }
    stem.bark.dispose();
    stem.foliage?.dispose();
  }
  return {
    bark: barkForge.finish(),
    foliage: hasFoliage ? folForge.finish() : null,
  };
}

/** Copy a built geometry (pos/normal/uv/vdata) into a forge under transform m. */
function mergeInto(forge: MeshForge, src: BufferGeometry, m: Matrix4): void {
  const pos = src.getAttribute('position');
  const nrm = src.getAttribute('normal');
  const uv = src.getAttribute('uv');
  const dat = src.getAttribute('vdata');
  const idx = src.getIndex();
  const p = new Vector3();
  const n = new Vector3();
  const base = forge.count;
  for (let i = 0; i < pos.count; i++) {
    p.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(m);
    n.set(nrm.getX(i), nrm.getY(i), nrm.getZ(i)).transformDirection(m);
    forge.emit(
      p.x, p.y, p.z, n.x, n.y, n.z,
      uv ? uv.getX(i) : 0, uv ? uv.getY(i) : 0,
      dat ? dat.getX(i) : 0, dat ? dat.getY(i) : 0,
      dat ? dat.getZ(i) : 0, dat ? dat.getW(i) : 1,
    );
  }
  if (idx) {
    for (let i = 0; i < idx.count; i += 3) {
      forge.face(base + idx.getX(i), base + idx.getX(i + 1), base + idx.getX(i + 2));
    }
  }
}

// ---------------------------------------------------------------------------
// Ferns
// ---------------------------------------------------------------------------

/** Capture profile for the fern frond atlas (one arching pinnate comb). */
export const FERN_PROTO: TreeProfile = {
  ...BUSH_HAZEL,
  id: 'fern',
  label: 'Fern',
  canopy: {
    style: 'needleFan',
    tier: 2,
    stride: 0.1,
    fromT: 0.1,
    sizeRange: [0.3, 0.45],
    tilt: 0.6,
    tuftRange: [1, 1],
    domeBlend: 0.55,
    twoRanked: true,
    bakeStyle: 'fern',
    plate: { mode: 'cross', scale: 2.2 },
    blade: { len: 0.1, width: 0.032, pointiness: 1, fold: 0, curl: 0, needles: 30, radial: 0 },
  },
  leafColor: { r: 0.045, g: 0.14, b: 0.028, hueVar: 0.22 },
};

/** Fern plant: a rosette of 6–10 frond cards springing from a centre point. */
export function assembleFern(rng: SeedStream): BufferGeometry {
  const forge = new MeshForge();
  const fronds = 6 + rng.index(5);
  const tufts: Tuft[] = [];
  const q = new Quaternion();
  const qt = new Quaternion();
  const Y = new Vector3(0, 1, 0);
  const X = new Vector3(1, 0, 0);
  for (let i = 0; i < fronds; i++) {
    const az = (i / fronds) * Math.PI * 2 + rng.unit() * 0.6;
    const pitch = 0.75 + rng.unit() * 0.4; // steep at the base, arches over
    q.setFromAxisAngle(Y, az);
    qt.setFromAxisAngle(X, -(Math.PI / 2 - pitch));
    q.multiply(qt);
    tufts.push({
      position: new Vector3(Math.cos(az) * 0.03, 0.02, Math.sin(az) * 0.03),
      orient: q.clone(),
      scale: 0.2 + rng.unit() * 0.14,
      tintJitter: rng.unit() * 2 - 1,
      dryness: rng.unit() * 0.4,
    });
  }
  scatterCards(forge, tufts, { mode: 'flat', scale: 2.4, bend: 1.0 }, rng);
  return forge.finish();
}

// ---------------------------------------------------------------------------
// Flowers
// ---------------------------------------------------------------------------

export type BloomKind = 'umbel' | 'bell' | 'daisy';

/**
 * Small flowering plant: a thin cross-strip stem, a few basal leaves, and real
 * petal geometry for the head(s).
 * vdata.x: 0 = stem/leaf (green), 0.5 = flower centre, 1 = petal.
 */
export function assembleFlower(kind: BloomKind, rng: SeedStream): BufferGeometry {
  const g = new MeshForge();
  const H = kind === 'umbel' ? 0.55 + rng.unit() * 0.3 : 0.28 + rng.unit() * 0.2;
  const sway = (rng.unit() - 0.5) * 0.25;
  const top = new Vector3(sway * H, H, sway * H * 0.6);
  const mid = new Vector3(sway * H * 0.4, H * 0.55, 0);
  // stem: two perpendicular thin strips (reads round from any angle)
  for (let pl = 0; pl < 2; pl++) {
    const w = 0.006;
    const ox = pl === 0 ? w : 0;
    const oz = pl === 0 ? 0 : w;
    const a0 = g.emit(-ox, 0, -oz, 0, 0, 1, 0, 0, 0, 0, 0, 0.8);
    const a1 = g.emit(ox, 0, oz, 0, 0, 1, 1, 0, 0, 0, 0, 0.8);
    const b0 = g.emit(mid.x - ox, mid.y, mid.z - oz, 0, 0, 1, 0, 0.5, 0, 0, 0, 0.9);
    const b1 = g.emit(mid.x + ox, mid.y, mid.z + oz, 0, 0, 1, 1, 0.5, 0, 0, 0, 0.9);
    const c0 = g.emit(top.x - ox * 0.6, top.y, top.z - oz * 0.6, 0, 0, 1, 0, 1, 0, 0, 0, 1);
    const c1 = g.emit(top.x + ox * 0.6, top.y, top.z + oz * 0.6, 0, 0, 1, 1, 1, 0, 0, 0, 1);
    g.face4(a0, a1, b1, b0);
    g.face4(b0, b1, c1, c0);
  }
  // basal leaves
  const leaves = 2 + rng.index(2);
  for (let i = 0; i < leaves; i++) {
    const az = rng.unit() * Math.PI * 2;
    const ll = 0.07 + rng.unit() * 0.06;
    const lx = Math.cos(az);
    const lz = Math.sin(az);
    const y0 = 0.02 + rng.unit() * H * 0.3;
    const a0 = g.emit(lx * 0.01, y0, lz * 0.01, 0, 1, 0, 0, 0, 0, 0, 0, 0.85);
    const a1 = g.emit(lx * 0.01 - lz * 0.012, y0 + 0.005, lz * 0.01 + lx * 0.012, 0, 1, 0, 1, 0, 0, 0, 0, 0.85);
    const b0 = g.emit(lx * ll, y0 + ll * 0.5, lz * ll, 0, 1, 0, 0, 1, 0, 0, 0, 1);
    const b1 = g.emit(lx * ll - lz * 0.01, y0 + ll * 0.5 + 0.005, lz * ll + lx * 0.01, 0, 1, 0, 1, 1, 0, 0, 0, 1);
    g.face4(a0, a1, b1, b0);
  }
  // head(s)
  const head = (cx: number, cy: number, cz: number, s: number): void => {
    if (kind === 'daisy') {
      const petals = 8 + rng.index(5);
      for (let i = 0; i < petals; i++) {
        const az = (i / petals) * Math.PI * 2;
        const dx = Math.cos(az);
        const dz = Math.sin(az);
        const pw = s * 0.3;
        const plen = s;
        const a0 = g.emit(cx + dx * s * 0.18 - dz * pw * 0.5, cy, cz + dz * s * 0.18 + dx * pw * 0.5, 0, 1, 0.2, 0, 0, 1, 0, 0, 1);
        const a1 = g.emit(cx + dx * s * 0.18 + dz * pw * 0.5, cy, cz + dz * s * 0.18 - dx * pw * 0.5, 0, 1, 0.2, 1, 0, 1, 0, 0, 1);
        const b0 = g.emit(cx + dx * plen - dz * pw * 0.25, cy + s * 0.16, cz + dz * plen + dx * pw * 0.25, 0, 1, 0.2, 0.4, 1, 1, 0, 0, 1);
        const b1 = g.emit(cx + dx * plen + dz * pw * 0.25, cy + s * 0.16, cz + dz * plen - dx * pw * 0.25, 0, 1, 0.2, 0.6, 1, 1, 0, 0, 1);
        g.face4(a0, a1, b1, b0);
      }
      const c = g.emit(cx, cy + s * 0.08, cz, 0, 1, 0, 0.5, 0.5, 0.5, 0, 0, 1);
      const ringN = 6;
      const ring: number[] = [];
      for (let i = 0; i <= ringN; i++) {
        const az = (i / ringN) * Math.PI * 2;
        ring.push(
          g.emit(cx + Math.cos(az) * s * 0.2, cy + s * 0.03, cz + Math.sin(az) * s * 0.2, 0, 1, 0, 0.5, 0.5, 0.5, 0, 0, 1),
        );
      }
      for (let i = 0; i < ringN; i++) g.face(c, ring[i + 1] as number, ring[i] as number);
    } else if (kind === 'bell') {
      const petals = 5;
      for (let i = 0; i < petals; i++) {
        const az = (i / petals) * Math.PI * 2;
        const dx = Math.cos(az);
        const dz = Math.sin(az);
        const a0 = g.emit(cx + dx * s * 0.12, cy, cz + dz * s * 0.12, dx, 0.3, dz, 0.4, 0, 1, 0, 0, 1);
        const a1 = g.emit(cx + Math.cos(az + 1.25) * s * 0.12, cy, cz + Math.sin(az + 1.25) * s * 0.12, dx, 0.3, dz, 0.6, 0, 1, 0, 0, 1);
        const b0 = g.emit(cx + dx * s * 0.3, cy - s * 0.5, cz + dz * s * 0.3, dx, 0, dz, 0.4, 1, 1, 0, 0, 1);
        const b1 = g.emit(cx + Math.cos(az + 1.25) * s * 0.3, cy - s * 0.5, cz + Math.sin(az + 1.25) * s * 0.3, dx, 0, dz, 0.6, 1, 1, 0, 0, 1);
        g.face4(a0, a1, b1, b0);
      }
    } else {
      const florets = 12 + rng.index(8);
      for (let i = 0; i < florets; i++) {
        const az = rng.unit() * Math.PI * 2;
        const rr = Math.sqrt(rng.unit()) * s;
        const fx = cx + Math.cos(az) * rr;
        const fz = cz + Math.sin(az) * rr;
        const fy = cy + (1 - (rr / s) * (rr / s)) * s * 0.35;
        const fs = s * 0.16;
        const a0 = g.emit(fx - fs, fy, fz - fs, 0, 1, 0, 0, 0, 1, 0, 0, 1);
        const a1 = g.emit(fx + fs, fy, fz - fs, 0, 1, 0, 1, 0, 1, 0, 0, 1);
        const b1 = g.emit(fx + fs, fy + fs * 0.2, fz + fs, 0, 1, 0, 1, 1, 1, 0, 0, 1);
        const b0 = g.emit(fx - fs, fy + fs * 0.2, fz + fs, 0, 1, 0, 0, 1, 1, 0, 0, 1);
        g.face4(a0, a1, b1, b0);
      }
    }
  };
  if (kind === 'bell') {
    const bells = 2 + rng.index(3);
    for (let i = 0; i < bells; i++) {
      const t = 0.6 + (i / bells) * 0.4;
      head(top.x * t + 0.02 * i, H * t, top.z * t, 0.05 + rng.unit() * 0.02);
    }
  } else {
    head(top.x, H + 0.02, top.z, kind === 'umbel' ? 0.09 + rng.unit() * 0.04 : 0.045 + rng.unit() * 0.02);
  }
  return g.finish();
}
