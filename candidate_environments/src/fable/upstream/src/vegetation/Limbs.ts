/**
 * Limbs — skins the branch skeleton in bark.
 *
 * Each limb polyline becomes a generalized cylinder built with a
 * parallel-transport frame (no per-ring twist, so the bark texture never
 * spirals). The trunk gets a flared, lobed buttress at the base; snapped limbs
 * get a ragged splinter cap instead of a smooth point.
 */

import { Vector3 } from 'three';
import type { SeedStream } from './SeedStream';
import type { MeshForge } from './MeshForge';
import type { BranchTree, Limb } from './Botany';

export interface LimbSkin {
  /** ring vertex count at the base (tapers toward the tip) */
  ringSegs: number;
  /** around-tube texture repeats at the base */
  uTiling: number;
  /** lengthwise texture scale */
  vTiling: number;
  /** trunk-only buttress */
  buttress?: { amp: number; rise: number; lobes: number; phase: number };
  swayPhase: number;
  flexBase: number;
  flexTip: number;
  hue: number;
}

const NRM = new Vector3();
const BIN = new Vector3();
const TAN = new Vector3();
const TMP = new Vector3();

/** Extrude one limb's bark into the forge. */
export function extrudeLimb(
  forge: MeshForge,
  limb: Limb,
  skin: LimbSkin,
  rng: SeedStream,
): void {
  const count = limb.points.length;
  if (count < 2) return;

  // seed the transport frame perpendicular to the first tangent
  TAN.copy(limb.tangents[0] as Vector3);
  const seed = Math.abs(TAN.y) < 0.94 ? new Vector3(0, 1, 0) : new Vector3(1, 0, 0);
  NRM.crossVectors(seed, TAN).normalize();
  BIN.crossVectors(TAN, NRM).normalize();

  const around = Math.max(4, skin.ringSegs);
  const baseR = Math.max(limb.radii[0] as number, 1e-4);
  const rings: number[][] = [];
  let lastRing: number[] = [];
  let vRun = 0;

  for (let i = 0; i < count; i++) {
    const p = limb.points[i] as Vector3;
    const r = limb.radii[i] as number;
    if (i > 0) {
      vRun += TMP.subVectors(p, limb.points[i - 1] as Vector3).length();
      // rotate the frame to follow the bend (parallel transport)
      const prevT = limb.tangents[i - 1] as Vector3;
      const curT = limb.tangents[i] as Vector3;
      const axis = TMP.crossVectors(prevT, curT);
      const sin = axis.length();
      if (sin > 1e-6) {
        axis.multiplyScalar(1 / sin);
        const ang = Math.asin(Math.min(1, sin));
        NRM.applyAxisAngle(axis, ang).normalize();
        BIN.applyAxisAngle(axis, ang).normalize();
      }
    }
    const tFrac = i / (count - 1);
    const rAhead = limb.radii[Math.min(count - 1, i + 1)] as number;
    const rBehind = limb.radii[Math.max(0, i - 1)] as number;
    const slope = ((rBehind - rAhead) * (count - 1)) / Math.max(0.05, limb.length) * 0.5;
    const flex = skin.flexBase + (skin.flexTip - skin.flexBase) * tFrac;
    const ring: number[] = [];
    const ringPos: number[] = [];
    const tan = limb.tangents[i] as Vector3;
    for (let k = 0; k <= around; k++) {
      const a = (k / around) * Math.PI * 2;
      const ca = Math.cos(a);
      const sa = Math.sin(a);
      let rr = r;
      if (skin.buttress && limb.level === 0) {
        const h = (limb.points[i] as Vector3).y - (limb.points[0] as Vector3).y;
        const lobe = Math.pow(
          Math.max(0, Math.cos(skin.buttress.lobes * a + skin.buttress.phase)),
          1.6,
        );
        rr *= 1 + skin.buttress.amp * Math.exp(-h / skin.buttress.rise) * (0.45 + 0.9 * lobe);
      }
      const dx = NRM.x * ca + BIN.x * sa;
      const dy = NRM.y * ca + BIN.y * sa;
      const dz = NRM.z * ca + BIN.z * sa;
      let nx = dx + tan.x * slope;
      let ny = dy + tan.y * slope;
      let nz = dz + tan.z * slope;
      const nl = Math.hypot(nx, ny, nz) || 1;
      nx /= nl; ny /= nl; nz /= nl;
      const vx = p.x + dx * rr;
      const vy = p.y + dy * rr;
      const vz = p.z + dz * rr;
      ringPos.push(vx, vy, vz);
      ring.push(
        forge.emit(
          vx, vy, vz,
          nx, ny, nz,
          (k / around) * skin.uTiling,
          (vRun / (Math.PI * 2 * baseR)) * skin.uTiling * skin.vTiling,
          skin.hue, flex, skin.swayPhase, 1,
        ),
      );
    }
    rings.push(ring);
    lastRing = ringPos;
  }

  // stitch consecutive rings; base-ring-first winding keeps faces outward
  for (let i = 0; i < rings.length - 1; i++) {
    const lo = rings[i] as number[];
    const hi = rings[i + 1] as number[];
    for (let k = 0; k < around; k++) {
      forge.face4(lo[k] as number, lo[k + 1] as number, hi[k + 1] as number, hi[k] as number);
    }
  }

  const top = rings[rings.length - 1] as number[];
  const tipP = limb.points[count - 1] as Vector3;
  const tipT = limb.tangents[count - 1] as Vector3;
  const tipR = limb.radii[count - 1] as number;
  if (limb.broken && tipR > 0.015) {
    // splintered break: a crown of inward spikes at random heights
    const hub = forge.emit(
      tipP.x + tipT.x * tipR * 0.4, tipP.y + tipT.y * tipR * 0.4, tipP.z + tipT.z * tipR * 0.4,
      tipT.x, tipT.y, tipT.z,
      0.5, 0.5, skin.hue, skin.flexTip, skin.swayPhase, 0.55,
    );
    const spikes: number[] = [];
    for (let k = 0; k <= around; k++) {
      const px = tipP.x + ((lastRing[k * 3] as number) - tipP.x) * 0.45;
      const py = tipP.y + ((lastRing[k * 3 + 1] as number) - tipP.y) * 0.45;
      const pz = tipP.z + ((lastRing[k * 3 + 2] as number) - tipP.z) * 0.45;
      const jut = (rng.unit() * 0.9 + 0.25) * tipR * 1.4;
      spikes.push(
        forge.emit(
          px + tipT.x * jut, py + tipT.y * jut, pz + tipT.z * jut,
          tipT.x, tipT.y, tipT.z,
          0.5, 0.5, skin.hue, skin.flexTip, skin.swayPhase, 0.5,
        ),
      );
    }
    for (let k = 0; k < around; k++) {
      forge.face4(top[k] as number, top[k + 1] as number, spikes[k + 1] as number, spikes[k] as number);
      forge.face(spikes[k + 1] as number, hub, spikes[k] as number);
    }
  } else {
    // taper smoothly to a point
    const tip = forge.emit(
      tipP.x + tipT.x * tipR * 2.0, tipP.y + tipT.y * tipR * 2.0, tipP.z + tipT.z * tipR * 2.0,
      tipT.x, tipT.y, tipT.z,
      0.5, vRun / (Math.PI * 2 * baseR) + 0.2,
      skin.hue, skin.flexTip, skin.swayPhase, 1,
    );
    for (let k = 0; k < around; k++) {
      forge.face(top[k + 1] as number, tip, top[k] as number);
    }
  }
}

/** Ring resolution by branch level; the LOD factor scales it down. */
export function ringCount(level: number, lodK: number): number {
  const base = level === 0 ? 14 : level === 1 ? 8 : level === 2 ? 6 : 5;
  return Math.max(4, Math.round(base * lodK));
}

/** Skin every limb of a tree into the forge. */
export function extrudeSkeleton(
  forge: MeshForge,
  tree: BranchTree,
  rng: SeedStream,
  opts: {
    lodK: number;
    uTiling: number;
    buttress?: { amp: number; rise: number; lobes: number; phase: number };
    /** skip limbs above this level (LOD cut) */
    maxLevel?: number;
    /** keep only every Nth level-≥1 limb (far-LOD bark diet) */
    stride?: number;
  },
): void {
  const maxLevel = opts.maxLevel ?? 99;
  const stride = opts.stride ?? 1;
  let seen = 0;
  for (const limb of tree.limbs) {
    if (limb.level > maxLevel) continue;
    if (limb.level >= 1 && stride > 1 && seen++ % stride !== 0) continue;
    const flexBase = limb.level === 0 ? 0 : limb.level === 1 ? 0.12 : 0.3;
    const flexTip = limb.level === 0 ? 0.05 : limb.level === 1 ? 0.35 : 0.7;
    extrudeLimb(
      forge,
      limb,
      {
        ringSegs: ringCount(limb.level, opts.lodK),
        uTiling: limb.level === 0 ? opts.uTiling : Math.max(1, Math.round(opts.uTiling * 0.4)),
        vTiling: 1,
        ...(limb.level === 0 && opts.buttress ? { buttress: opts.buttress } : {}),
        swayPhase: rng.unit() * Math.PI * 2,
        flexBase,
        flexTip,
        hue: rng.unit() * 2 - 1,
      },
      rng,
    );
  }
}
