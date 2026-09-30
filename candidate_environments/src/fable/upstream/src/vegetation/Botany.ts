/**
 * Botany — the shared vocabulary for the procedural flora kit.
 *
 * A `TreeProfile` is a pure data bundle: it tells the branching simulator
 * (Branching.ts) how to grow, the limb extruder (Limbs.ts) how to skin the
 * wood, and the canopy baker (CardAtlas.ts) what leaves to paint. Nothing here
 * holds GPU state — a profile is just numbers, so two worlds with the same seed
 * grow identical plants.
 */

import type { Quaternion, Vector3 } from 'three';

/** How child-branch length scales with position along its parent. */
export type CrownProfile = 'cone' | 'ellipsoid' | 'dome' | 'irregular' | 'column';

/**
 * One tier of the branch hierarchy. `tiers[0]` is always the trunk; `tiers[i]`
 * both describes the geometry of level-i branches AND how they are sprinkled
 * over their (i−1) parent.
 */
export interface TierParams {
  /** children spawned per metre of parent inside the span window */
  perMeter: number;
  /** 0 = spiral (golden-angle) phyllotaxis; n ≥ 2 = rings of n */
  whorlCount: number;
  /** fraction of the parent that bears these children */
  spanStart: number;
  spanEnd: number;
  /** insertion angle off the parent tangent (rad) at span start / end */
  angleRoot: number;
  angleEnd: number;
  /** child length = parent length × lenScale × crownEnvelope(t) */
  lenScale: number;
  /** ± fractional length jitter */
  lenVar: number;
  /** child base radius = parent radius at t × radScale */
  radScale: number;
  /** polyline resolution */
  segments: number;
  /** random heading wobble per segment (rad) */
  jitter: number;
  /** vertical pull per segment: <0 droops downward, >0 reaches up */
  upBias: number;
  /** cumulative cantilever sag toward the tip (rad over the whole branch) */
  sag: number;
  /** upward flick concentrated at the very tip (conifer secondaries) */
  tipLift: number;
  /** radius falloff exponent along the branch */
  taperPow: number;
  /**
   * 0 = radial spread; 1 = strictly two-sided within the bough plane
   * (conifer branchlets, distichous twigs). Fractions blend the two.
   */
  flatten?: number;
}

export interface CanopyParams {
  style: 'needleFan' | 'leafTuft';
  /** which branch tier carries the leaf anchors */
  tier: number;
  /** anchor spacing along the carrying branch (m) */
  stride: number;
  /** anchors begin at this fraction along the branch */
  fromT: number;
  /** world size of one fan/tuft (m), [min, max] */
  sizeRange: [number, number];
  /** outward tilt of the spray from the branch axis (rad) */
  tilt: number;
  /** leaves per tuft (leafTuft only) */
  tuftRange: [number, number];
  /** blend of geometric normal toward the crown-sphere normal (0..1) */
  domeBlend: number;
  /** leaves alternate two-ranked along the twig instead of spiralling */
  twoRanked?: boolean;
  /** atlas-bake override: 'fern' draws one arching pinnate frond */
  bakeStyle?: 'fern';
  /**
   * Card placement of the baked twig atlas onto big alpha-tested quads.
   * 'flat' = single bough-plane plate, 'cross' = two perpendicular quads
   * for volumetric broadleaf reads. `scale` enlarges the card vs anchor size.
   */
  plate: { mode: 'flat' | 'cross'; scale: number };
  /** the leaf/needle geometry for this species */
  blade: LeafForm;
}

export interface LeafForm {
  /** single leaf length / width (m); for fans this is the needle length */
  len: number;
  width: number;
  /** width-profile exponent (1 ≈ ellipse, >1 lance-shaped) */
  pointiness: number;
  /** fold along the midrib (V cross-section) */
  fold: number;
  /** lengthwise downward curl */
  curl: number;
  /** needles per fan (needleFan only) */
  needles: number;
  /** fan layout: 0 = flat comb, 1 = radial bottlebrush */
  radial: number;
}

export interface TreeProfile {
  id: string;
  label: string;
  kind: 'conifer' | 'broadleaf' | 'snag';
  /** mature height window (m) */
  height: [number, number];
  /** trunk base radius as a fraction of height */
  girth: number;
  crown: CrownProfile;
  /** light-competition crown lean strength (0..~0.5) */
  crownLean: number;
  tiers: TierParams[];
  canopy: CanopyParams | null;
  /** root buttress: amplitude, falloff height (m), lobe count */
  buttress: { amp: number; rise: number; lobes: number };
  /** around-trunk texture repeats at the base */
  barkTiling: number;
  /** base leaf albedo + per-instance hue swing */
  leafColor: { r: number; g: number; b: number; hueVar: number };
  /** flowering: a fraction of baked leaves turn bloom-coloured */
  bloom?: { r: number; g: number; b: number; frac: number };
  /** bark albedo tint fed to the shared wood material */
  woodTint: { r: number; g: number; b: number };
  /** trunk snapped at this fraction (snags); 0 = intact */
  snapAt: number;
  /** odds any given branch is a broken stub */
  stubOdds: number;
}

/** Continuous, per-plant deformation knobs layered on top of the seed. */
export interface GrowthBias {
  /** world lean (slope / wind response), magnitude ~0..0.25 */
  leanX: number;
  leanZ: number;
  /** crown asymmetry direction (unit XZ) */
  asymX: number;
  asymZ: number;
  /** 0 sapling .. 1 veteran: scales height + branch density */
  maturity: number;
}

export interface Limb {
  level: number;
  /** polyline points in tree-local space (origin at 0,0,0) */
  points: Vector3[];
  /** radius at each point */
  radii: number[];
  /** unit tangent at each point */
  tangents: Vector3[];
  length: number;
  /** fraction along the parent where this limb attaches */
  atParent: number;
  /** snapped / stub limbs get a jagged cap */
  broken: boolean;
}

export interface Tuft {
  position: Vector3;
  orient: Quaternion;
  scale: number;
  /** per-tuft hue jitter (−1..1) */
  tintJitter: number;
  /** 0 fresh .. 1 dry/old (inner & lower crown) */
  dryness: number;
}

export interface BranchTree {
  limbs: Limb[];
  tufts: Tuft[];
  height: number;
  crownY: number;
  crownRadius: number;
}
