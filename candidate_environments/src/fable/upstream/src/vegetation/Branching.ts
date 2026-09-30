/**
 * Branching — the recursive growth simulator.
 *
 * Each branch is walked one segment at a time, its heading nudged by gravity
 * and light tropisms, a little noise, and an accumulating cantilever sag.
 * Children are budded along the parent with either whorled or golden-angle
 * spacing, and their length is shaped by a crown envelope plus a sun-seeking
 * asymmetry. Foliage anchors are dropped on the chosen tier as it grows. The
 * whole walk is driven by one SeedStream, so it replays exactly per seed.
 */

import { Quaternion, Vector3 } from 'three';
import type { SeedStream } from './SeedStream';
import type {
  BranchTree,
  CrownProfile,
  GrowthBias,
  Limb,
  TierParams,
  Tuft,
  TreeProfile,
} from './Botany';

const UP = new Vector3(0, 1, 0);
const PHI = 2.39996323; // golden angle (rad)

/** Length multiplier for a child at fraction `t` of its crown band. */
function crownEnvelope(shape: CrownProfile, t: number, rng: SeedStream): number {
  switch (shape) {
    case 'cone':
      return 0.18 + 0.82 * Math.pow(1 - t, 0.9);
    case 'ellipsoid':
      return Math.max(0.12, Math.sin(Math.PI * (0.08 + 0.88 * t)));
    case 'dome':
      return Math.max(0.15, Math.sqrt(Math.max(0, 1 - t * t * 0.92)));
    case 'column':
      return 0.55 + 0.45 * Math.sin(Math.PI * Math.min(1, t * 1.15));
    case 'irregular':
      return 0.3 + 0.7 * Math.abs(Math.sin(t * 9.7 + rng.unit() * 6.28)) * (1 - t * 0.4);
  }
}

/** orthonormal pair perpendicular to `dir` */
function sideFrame(dir: Vector3, outN: Vector3, outB: Vector3): void {
  const ref = Math.abs(dir.y) < 0.94 ? UP : new Vector3(1, 0, 0);
  outN.crossVectors(ref, dir).normalize();
  outB.crossVectors(dir, outN).normalize();
}

interface GrowState {
  profile: TreeProfile;
  rng: SeedStream;
  bias: GrowthBias;
  limbs: Limb[];
  tufts: Tuft[];
  budget: number;
}

interface Bud {
  level: number;
  origin: Vector3;
  heading: Vector3;
  length: number;
  baseR: number;
  atParent: number;
  stub: boolean;
}

function extend(state: GrowState, bud: Bud): Limb | null {
  if (state.budget <= 0) return null;
  state.budget--;

  const { profile, rng, bias } = state;
  const tier = profile.tiers[bud.level] as TierParams;
  const segs = Math.max(2, tier.segments);
  const isTrunk = bud.level === 0;
  const rawLen = bud.stub ? bud.length * (0.12 + rng.unit() * 0.18) : bud.length;
  const broken = bud.stub || (isTrunk && profile.snapAt > 0 && profile.snapAt < 1);
  const liveLen = isTrunk && profile.snapAt > 0 ? rawLen * profile.snapAt : rawLen;

  const points: Vector3[] = [];
  const radii: number[] = [];
  const tangents: Vector3[] = [];
  const dir = bud.heading.clone().normalize();
  const cursor = bud.origin.clone();
  const step = liveLen / segs;

  // each branch gets a private wobble so siblings decorrelate
  const wobblePhase = rng.unit() * Math.PI * 2;
  const wobbleFreq = 1.5 + rng.unit() * 2.5;
  const sagTotal = tier.sag * (0.7 + rng.unit() * 0.6);

  const fn = new Vector3();
  const fb = new Vector3();
  for (let i = 0; i <= segs; i++) {
    const t = i / segs;
    const tTaper = isTrunk && profile.snapAt > 0 ? t * profile.snapAt : t;
    let r = bud.baseR * Math.pow(Math.max(0, 1 - tTaper), tier.taperPow);
    r = isTrunk ? Math.max(r, bud.baseR * 0.012) : Math.max(r, 0.0035);
    points.push(cursor.clone());
    radii.push(r);
    tangents.push(dir.clone());
    if (i === segs) break;

    sideFrame(dir, fn, fb);
    const wob = tier.jitter * (isTrunk ? 1 : 1.4);
    const a1 = Math.sin(t * wobbleFreq * Math.PI * 2 + wobblePhase) * wob + (rng.unit() - 0.5) * wob;
    const a2 = Math.cos(t * wobbleFreq * Math.PI * 1.7 + wobblePhase * 1.7) * wob + (rng.unit() - 0.5) * wob;
    dir.addScaledVector(fn, a1).addScaledVector(fb, a2);
    dir.addScaledVector(UP, tier.upBias * (isTrunk ? 1 : 0.4 + t));
    dir.y -= sagTotal * t * (1 / segs) * 2.4;
    dir.y += tier.tipLift * Math.max(0, t - 0.62) * (1 / segs) * 5.2;
    if (isTrunk) {
      dir.x += bias.leanX * (1 / segs) * (1.6 - t);
      dir.z += bias.leanZ * (1 / segs) * (1.6 - t);
    }
    dir.normalize();
    cursor.addScaledVector(dir, step * (0.92 + rng.unit() * 0.16));
  }

  const limb: Limb = {
    level: bud.level,
    points,
    radii,
    tangents,
    length: liveLen,
    atParent: bud.atParent,
    broken,
  };
  state.limbs.push(limb);
  if (bud.stub) return limb;

  budChildren(state, limb, bud, liveLen, segs, isTrunk, points, radii, tangents);
  dropTufts(state, limb, liveLen, segs, points, tangents);
  return limb;
}

function budChildren(
  state: GrowState,
  limb: Limb,
  bud: Bud,
  liveLen: number,
  segs: number,
  isTrunk: boolean,
  points: Vector3[],
  radii: number[],
  tangents: Vector3[],
): void {
  const { profile, rng, bias } = state;
  const childLevel = bud.level + 1;
  if (childLevel >= profile.tiers.length) return;
  const ct = profile.tiers[childLevel] as TierParams;
  const span = Math.max(0, ct.spanEnd - ct.spanStart);
  const densityScale = 0.75 + bias.maturity * 0.45;
  const total = Math.round(liveLen * span * ct.perMeter * densityScale);
  if (total <= 0) return;

  const whorl = ct.whorlCount;
  const flatten = ct.flatten ?? 0;
  const groups = whorl >= 2 ? Math.max(1, Math.round(total / whorl)) : total;
  const fn = new Vector3();
  const fb = new Vector3();
  let az = rng.unit() * Math.PI * 2;

  for (let gi = 0; gi < groups; gi++) {
    const tG = ct.spanStart + span * ((gi + 0.5) / groups);
    const ringN = whorl >= 2 ? whorl : 1;
    az += whorl >= 2 ? PHI * 0.5 + rng.unit() * 0.4 : 0;
    for (let wi = 0; wi < ringN; wi++) {
      const t = Math.min(0.985, tG + (rng.unit() - 0.5) * (span / groups) * 0.6);
      let angleAround: number;
      if (rng.unit() < flatten) {
        angleAround = ((gi + wi) % 2 === 0 ? 0 : Math.PI) + (rng.unit() - 0.5) * 0.55;
      } else if (whorl >= 2) {
        angleAround = az + (wi / ringN) * Math.PI * 2 + (rng.unit() - 0.5) * 0.5;
      } else {
        angleAround = az += PHI + (rng.unit() - 0.5) * 0.35;
      }
      const fi = t * segs;
      const i0 = Math.min(segs - 1, Math.floor(fi));
      const f = fi - i0;
      const pPos = new Vector3().lerpVectors(points[i0] as Vector3, points[i0 + 1] as Vector3, f);
      const pDir = new Vector3()
        .lerpVectors(tangents[i0] as Vector3, tangents[i0 + 1] as Vector3, f)
        .normalize();
      const pR = (radii[i0] as number) * (1 - f) + (radii[i0 + 1] as number) * f;
      sideFrame(pDir, fn, fb);
      const side = new Vector3()
        .addScaledVector(fn, Math.cos(angleAround))
        .addScaledVector(fb, Math.sin(angleAround));
      const lift = ct.angleRoot + (ct.angleEnd - ct.angleRoot) * t + (rng.unit() - 0.5) * 0.16;
      const cDir = new Vector3()
        .addScaledVector(pDir, Math.cos(lift))
        .addScaledVector(side, Math.sin(lift))
        .normalize();
      const env = crownEnvelope(profile.crown, isTrunk ? t : t * 0.6 + 0.4, rng);
      const lean =
        1 + profile.crownLean * (cDir.x * bias.asymX + cDir.z * bias.asymZ) * (isTrunk ? 1 : 0.4);
      const cLen = liveLen * ct.lenScale * env * lean * (1 + (rng.unit() - 0.5) * 2 * ct.lenVar);
      if (cLen < 0.05) continue;
      const cR = Math.min(pR * ct.radScale * (0.55 + env * 0.45), pR * 0.8);
      const stub = profile.stubOdds > 0 && rng.roll(profile.stubOdds);
      extend(state, {
        level: childLevel,
        origin: pPos,
        heading: cDir,
        length: cLen,
        baseR: cR,
        atParent: t,
        stub,
      });
    }
  }
}

function dropTufts(
  state: GrowState,
  limb: Limb,
  liveLen: number,
  segs: number,
  points: Vector3[],
  tangents: Vector3[],
): void {
  const { profile, rng } = state;
  const canopy = profile.canopy;
  if (!canopy || limb.level !== canopy.tier || limb.broken) return;

  const from = Math.max(0, canopy.fromT);
  const run = liveLen * (1 - from);
  const n = Math.max(1, Math.round(run / canopy.stride));
  const orient = new Quaternion();
  const twist = new Quaternion();
  const droop = new Quaternion();
  const fn = new Vector3();
  const fb = new Vector3();
  for (let i = 0; i <= n; i++) {
    const t = Math.min(1, from + (1 - from) * (i / n));
    const fi = t * segs;
    const i0 = Math.min(segs - 1, Math.floor(fi));
    const f = fi - i0;
    const aPos = new Vector3().lerpVectors(points[i0] as Vector3, points[i0 + 1] as Vector3, f);
    const aDir = new Vector3()
      .lerpVectors(tangents[i0] as Vector3, tangents[i0 + 1] as Vector3, f)
      .normalize();
    const terminal = i === n;
    sideFrame(aDir, fn, fb);
    const around = terminal
      ? 0
      : canopy.twoRanked
        ? (i % 2 === 0 ? 0 : Math.PI) + (rng.unit() - 0.5) * 0.6
        : PHI * i + (rng.unit() - 0.5) * 0.7;
    const out = terminal
      ? aDir.clone()
      : new Vector3()
          .addScaledVector(aDir, Math.cos(canopy.tilt))
          .addScaledVector(
            new Vector3().addScaledVector(fn, Math.cos(around)).addScaledVector(fb, Math.sin(around)),
            Math.sin(canopy.tilt),
          )
          .normalize();
    orient.setFromUnitVectors(new Vector3(0, 0, 1), out);
    const localY = new Vector3(0, 1, 0).applyQuaternion(orient);
    const flatUp = new Vector3().addScaledVector(out, -out.y).add(UP).normalize();
    const twistAngle = Math.atan2(
      new Vector3().crossVectors(localY, flatUp).dot(out),
      localY.dot(flatUp),
    );
    twist.setFromAxisAngle(out, twistAngle + (rng.unit() - 0.5) * 0.5);
    orient.premultiply(twist);
    const sideAxis = new Vector3(1, 0, 0).applyQuaternion(orient);
    droop.setFromAxisAngle(sideAxis, (rng.unit() - 0.5) * 0.24 + 0.08);
    orient.premultiply(droop);
    const sc =
      (canopy.sizeRange[0] + rng.unit() * (canopy.sizeRange[1] - canopy.sizeRange[0])) *
      (terminal ? 0.85 : 0.72 + t * 0.42);
    state.tufts.push({
      position: aPos.clone().addScaledVector(out, sc * 0.06),
      orient: orient.clone(),
      scale: sc,
      tintJitter: rng.unit() * 2 - 1,
      dryness: Math.max(0, 1 - t) * 0.7 + rng.unit() * 0.3,
    });
  }
}

export function cultivate(
  profile: TreeProfile,
  rng: SeedStream,
  bias?: Partial<GrowthBias>,
): BranchTree {
  const growth: GrowthBias = {
    leanX: (rng.unit() - 0.5) * 0.12,
    leanZ: (rng.unit() - 0.5) * 0.12,
    asymX: 0,
    asymZ: 0,
    maturity: 0.5 + rng.unit() * 0.5,
    ...bias,
  };
  if (growth.asymX === 0 && growth.asymZ === 0) {
    const a = rng.unit() * Math.PI * 2;
    growth.asymX = Math.cos(a);
    growth.asymZ = Math.sin(a);
  }

  const height =
    (profile.height[0] + rng.unit() * (profile.height[1] - profile.height[0])) *
    (0.72 + growth.maturity * 0.36);

  const state: GrowState = {
    profile,
    rng,
    bias: growth,
    limbs: [],
    tufts: [],
    budget: 9000,
  };
  extend(state, {
    level: 0,
    origin: new Vector3(0, 0, 0),
    heading: new Vector3(growth.leanX * 0.7, 1, growth.leanZ * 0.7).normalize(),
    length: height,
    baseR: height * profile.girth,
    atParent: 0,
    stub: false,
  });

  let minY = Infinity;
  let maxY = -Infinity;
  let maxR = 0.5;
  for (const tuft of state.tufts) {
    minY = Math.min(minY, tuft.position.y);
    maxY = Math.max(maxY, tuft.position.y);
    maxR = Math.max(maxR, Math.hypot(tuft.position.x, tuft.position.z));
  }
  if (!Number.isFinite(minY)) {
    minY = height * 0.3;
    maxY = height;
  }
  return {
    limbs: state.limbs,
    tufts: state.tufts,
    height,
    crownY: (minY + maxY) * 0.5,
    crownRadius: maxR,
  };
}
