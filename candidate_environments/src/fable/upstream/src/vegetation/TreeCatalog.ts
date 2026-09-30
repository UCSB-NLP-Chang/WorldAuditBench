/**
 * TreeCatalog — the species roster.
 *
 * Every entry is a pure `TreeProfile`: branching tiers for Branching.ts, a
 * canopy recipe for CardAtlas.ts, plus colour and bark tints. The roster spans
 * spires (spruce/pine), broadleaves (beech/birch), a squat cliff-clinger
 * (karst), a dead snag, a tall heavy-trunked elder oak, and a rare flowering
 * cherry — enough silhouettes that a forest never looks stamped.
 *
 * Invariant: leaves never sit directly on a primary branch. Every leafy
 * species terminates in a fine flattened twig tier and the canopy attaches
 * THERE, so fullness comes from thousands of small sprays on that lattice.
 * Wood colour is handled by lightweight tints, not baked bark variants.
 */

import type { TreeProfile } from './Botany';

export const SPRUCE: TreeProfile = {
  id: 'spruce',
  label: 'Spruce (conifer)',
  kind: 'conifer',
  height: [19, 27],
  girth: 0.017,
  crown: 'cone',
  crownLean: 0.22,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 16, jitter: 0.015, upBias: 0.05, sag: 0, tipLift: 0, taperPow: 1.0,
    },
    {
      // primaries: near-horizontal spokes, gentle sag, up-hooked tips
      perMeter: 5.0, whorlCount: 4, spanStart: 0.09, spanEnd: 0.985,
      angleRoot: 1.78, angleEnd: 0.55, lenScale: 0.19, lenVar: 0.2, radScale: 0.32,
      segments: 6, jitter: 0.06, upBias: -0.03, sag: 0.3, tipLift: 0.28, taperPow: 1.05,
    },
    {
      // branchlets: two-ranked lattice filling the bough plane
      perMeter: 5.5, whorlCount: 0, spanStart: 0.12, spanEnd: 0.98,
      angleRoot: 1.05, angleEnd: 0.8, lenScale: 0.24, lenVar: 0.35, radScale: 0.4,
      segments: 3, jitter: 0.08, upBias: -0.05, sag: 0.45, tipLift: 0.12, taperPow: 0.9,
      flatten: 1,
    },
  ],
  canopy: {
    style: 'needleFan',
    tier: 2,
    stride: 0.16,
    fromT: 0.05,
    sizeRange: [0.22, 0.35],
    tilt: 0.5,
    tuftRange: [1, 1],
    domeBlend: 0.62,
    twoRanked: true,
    plate: { mode: 'flat', scale: 2.6 },
    blade: { len: 0.1, width: 0.024, pointiness: 1, fold: 0, curl: 0, needles: 30, radial: 0 },
  },
  buttress: { amp: 0.5, rise: 1.0, lobes: 5 },
  barkTiling: 5,
  leafColor: { r: 0.045, g: 0.10, b: 0.05, hueVar: 0.24 },
  woodTint: { r: 0.32, g: 0.24, b: 0.19 },
  snapAt: 0,
  stubOdds: 0.02,
};

export const PINE: TreeProfile = {
  id: 'pine',
  label: 'Mountain pine (conifer)',
  kind: 'conifer',
  height: [12, 19],
  girth: 0.021,
  crown: 'dome',
  crownLean: 0.34,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 12, jitter: 0.06, upBias: 0.03, sag: 0, tipLift: 0, taperPow: 0.92,
    },
    {
      perMeter: 1.8, whorlCount: 3, spanStart: 0.42, spanEnd: 0.97,
      angleRoot: 1.5, angleEnd: 0.55, lenScale: 0.45, lenVar: 0.32, radScale: 0.4,
      segments: 8, jitter: 0.14, upBias: 0.08, sag: 0.3, tipLift: 0.32, taperPow: 0.85,
    },
    {
      perMeter: 2.6, whorlCount: 0, spanStart: 0.35, spanEnd: 1.0,
      angleRoot: 0.9, angleEnd: 0.55, lenScale: 0.32, lenVar: 0.34, radScale: 0.45,
      segments: 4, jitter: 0.13, upBias: 0.06, sag: 0.16, tipLift: 0.22, taperPow: 0.85,
    },
    {
      // twiglets rising at the ends — pine carries needles here
      perMeter: 4.2, whorlCount: 0, spanStart: 0.4, spanEnd: 1.0,
      angleRoot: 0.8, angleEnd: 0.5, lenScale: 0.4, lenVar: 0.4, radScale: 0.5,
      segments: 2, jitter: 0.15, upBias: 0.1, sag: 0.1, tipLift: 0.15, taperPow: 0.8,
    },
  ],
  canopy: {
    style: 'needleFan',
    tier: 3,
    stride: 0.11,
    fromT: 0.3,
    sizeRange: [0.26, 0.42],
    tilt: 0.55,
    tuftRange: [1, 1],
    domeBlend: 0.66,
    plate: { mode: 'cross', scale: 2.2 },
    blade: { len: 0.21, width: 0.018, pointiness: 1, fold: 0, curl: 0, needles: 88, radial: 1 },
  },
  buttress: { amp: 0.42, rise: 0.8, lobes: 4 },
  barkTiling: 4,
  leafColor: { r: 0.04, g: 0.092, b: 0.048, hueVar: 0.22 },
  woodTint: { r: 0.36, g: 0.26, b: 0.18 },
  snapAt: 0,
  stubOdds: 0.04,
};

export const BEECH: TreeProfile = {
  id: 'beech',
  label: 'Beech (broadleaf)',
  kind: 'broadleaf',
  height: [13, 20],
  girth: 0.024,
  crown: 'ellipsoid',
  crownLean: 0.3,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 9, jitter: 0.05, upBias: 0.04, sag: 0, tipLift: 0, taperPow: 1.25,
    },
    {
      perMeter: 1.5, whorlCount: 0, spanStart: 0.32, spanEnd: 0.94,
      angleRoot: 1.05, angleEnd: 0.5, lenScale: 0.56, lenVar: 0.26, radScale: 0.5,
      segments: 8, jitter: 0.1, upBias: 0.085, sag: 0.22, tipLift: 0.12, taperPow: 0.95,
    },
    {
      perMeter: 2.3, whorlCount: 0, spanStart: 0.25, spanEnd: 0.97,
      angleRoot: 0.92, angleEnd: 0.55, lenScale: 0.46, lenVar: 0.3, radScale: 0.52,
      segments: 5, jitter: 0.13, upBias: 0.05, sag: 0.3, tipLift: 0.08, taperPow: 0.9,
    },
    {
      // distichous twig plates — the layered horizontal beech foliage
      perMeter: 8.0, whorlCount: 0, spanStart: 0.15, spanEnd: 1.0,
      angleRoot: 0.9, angleEnd: 0.6, lenScale: 0.28, lenVar: 0.35, radScale: 0.55,
      segments: 3, jitter: 0.1, upBias: -0.02, sag: 0.15, tipLift: 0.04, taperPow: 0.85,
      flatten: 1,
    },
  ],
  canopy: {
    style: 'leafTuft',
    tier: 3,
    stride: 0.13,
    fromT: 0.1,
    sizeRange: [0.16, 0.24],
    tilt: 1.0,
    tuftRange: [2, 3],
    domeBlend: 0.7,
    twoRanked: true,
    plate: { mode: 'cross', scale: 2.3 },
    blade: { len: 1.0, width: 0.42, pointiness: 1.15, fold: 0.32, curl: 0.22, needles: 0, radial: 0 },
  },
  buttress: { amp: 0.55, rise: 1.2, lobes: 6 },
  barkTiling: 4,
  leafColor: { r: 0.06, g: 0.145, b: 0.035, hueVar: 0.3 },
  woodTint: { r: 0.45, g: 0.42, b: 0.36 },
  snapAt: 0,
  stubOdds: 0.02,
};

export const BIRCH: TreeProfile = {
  id: 'birch',
  label: 'Birch (broadleaf)',
  kind: 'broadleaf',
  height: [9, 15],
  girth: 0.015,
  crown: 'column',
  crownLean: 0.26,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 11, jitter: 0.05, upBias: 0.045, sag: 0, tipLift: 0, taperPow: 1.1,
    },
    {
      perMeter: 2.2, whorlCount: 0, spanStart: 0.3, spanEnd: 0.96,
      angleRoot: 0.95, angleEnd: 0.45, lenScale: 0.4, lenVar: 0.3, radScale: 0.42,
      segments: 7, jitter: 0.11, upBias: 0.02, sag: 0.4, tipLift: -0.04, taperPow: 0.95,
    },
    {
      perMeter: 3.8, whorlCount: 0, spanStart: 0.3, spanEnd: 1.0,
      angleRoot: 0.8, angleEnd: 0.5, lenScale: 0.42, lenVar: 0.34, radScale: 0.5,
      segments: 4, jitter: 0.14, upBias: -0.1, sag: 0.5, tipLift: -0.05, taperPow: 0.9,
    },
    {
      // weeping twig streamers
      perMeter: 6.0, whorlCount: 0, spanStart: 0.3, spanEnd: 1.0,
      angleRoot: 0.7, angleEnd: 0.45, lenScale: 0.35, lenVar: 0.4, radScale: 0.5,
      segments: 3, jitter: 0.12, upBias: -0.3, sag: 0.7, tipLift: -0.05, taperPow: 0.85,
      flatten: 0.5,
    },
  ],
  canopy: {
    style: 'leafTuft',
    tier: 3,
    stride: 0.11,
    fromT: 0.15,
    sizeRange: [0.1, 0.16],
    tilt: 0.9,
    tuftRange: [2, 3],
    domeBlend: 0.66,
    twoRanked: true,
    plate: { mode: 'cross', scale: 2.3 },
    blade: { len: 1.0, width: 0.55, pointiness: 1.4, fold: 0.22, curl: 0.3, needles: 0, radial: 0 },
  },
  buttress: { amp: 0.32, rise: 0.7, lobes: 4 },
  barkTiling: 3,
  leafColor: { r: 0.075, g: 0.15, b: 0.03, hueVar: 0.34 },
  woodTint: { r: 0.72, g: 0.7, b: 0.64 },
  snapAt: 0,
  stubOdds: 0.03,
};

export const KARST_GNARL: TreeProfile = {
  id: 'karst',
  label: 'Karst gnarl (cliff broadleaf)',
  kind: 'broadleaf',
  height: [3.5, 6.5],
  girth: 0.045,
  crown: 'irregular',
  crownLean: 0.5,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 9, jitter: 0.34, upBias: -0.05, sag: 0, tipLift: 0.1, taperPow: 0.8,
    },
    {
      perMeter: 2.6, whorlCount: 0, spanStart: 0.15, spanEnd: 0.95,
      angleRoot: 1.35, angleEnd: 0.7, lenScale: 0.62, lenVar: 0.45, radScale: 0.55,
      segments: 7, jitter: 0.3, upBias: 0.06, sag: 0.35, tipLift: 0.18, taperPow: 0.8,
    },
    {
      perMeter: 3.8, whorlCount: 0, spanStart: 0.2, spanEnd: 1.0,
      angleRoot: 1.0, angleEnd: 0.6, lenScale: 0.42, lenVar: 0.4, radScale: 0.55,
      segments: 4, jitter: 0.3, upBias: 0.05, sag: 0.25, tipLift: 0.1, taperPow: 0.85,
    },
    {
      // gnarled twiglets bearing layered leaf plates
      perMeter: 5.0, whorlCount: 0, spanStart: 0.25, spanEnd: 1.0,
      angleRoot: 0.85, angleEnd: 0.55, lenScale: 0.4, lenVar: 0.45, radScale: 0.5,
      segments: 2, jitter: 0.25, upBias: 0.04, sag: 0.2, tipLift: 0.1, taperPow: 0.85,
      flatten: 0.4,
    },
  ],
  canopy: {
    style: 'leafTuft',
    tier: 3,
    stride: 0.055,
    fromT: 0.12,
    sizeRange: [0.11, 0.16],
    tilt: 0.9,
    tuftRange: [2, 4],
    domeBlend: 0.66,
    twoRanked: true,
    plate: { mode: 'cross', scale: 2.2 },
    blade: { len: 1.0, width: 0.5, pointiness: 1.2, fold: 0.3, curl: 0.24, needles: 0, radial: 0 },
  },
  buttress: { amp: 0.9, rise: 0.7, lobes: 6 },
  barkTiling: 3,
  leafColor: { r: 0.05, g: 0.12, b: 0.04, hueVar: 0.24 },
  woodTint: { r: 0.4, g: 0.34, b: 0.28 },
  snapAt: 0,
  stubOdds: 0.1,
};

export const SNAG: TreeProfile = {
  id: 'snag',
  label: 'Snag (dead standing)',
  kind: 'snag',
  height: [8, 15],
  girth: 0.022,
  crown: 'cone',
  crownLean: 0.3,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 13, jitter: 0.06, upBias: 0.04, sag: 0, tipLift: 0, taperPow: 0.9,
    },
    {
      perMeter: 2.4, whorlCount: 0, spanStart: 0.2, spanEnd: 0.97,
      angleRoot: 1.6, angleEnd: 0.85, lenScale: 0.38, lenVar: 0.45, radScale: 0.32,
      segments: 6, jitter: 0.14, upBias: -0.1, sag: 0.6, tipLift: 0.05, taperPow: 0.75,
    },
    {
      perMeter: 1.8, whorlCount: 0, spanStart: 0.2, spanEnd: 1.0,
      angleRoot: 1.1, angleEnd: 0.7, lenScale: 0.3, lenVar: 0.5, radScale: 0.4,
      segments: 3, jitter: 0.2, upBias: -0.08, sag: 0.4, tipLift: 0, taperPow: 0.7,
    },
  ],
  canopy: null,
  buttress: { amp: 0.6, rise: 0.9, lobes: 5 },
  barkTiling: 4,
  leafColor: { r: 0.1, g: 0.09, b: 0.07, hueVar: 0.1 },
  woodTint: { r: 0.46, g: 0.42, b: 0.37 },
  snapAt: 0.62,
  stubOdds: 0.28,
};

export const ELDER_OAK: TreeProfile = {
  id: 'oak',
  label: 'Elder oak (broadleaf)',
  kind: 'broadleaf',
  height: [22, 34],
  girth: 0.041, // heavy, buttressed bole
  crown: 'dome',
  crownLean: 0.34,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 10, jitter: 0.07, upBias: 0.03, sag: 0, tipLift: 0, taperPow: 1.45,
    },
    {
      // few, massive scaffold limbs reaching wide then up
      perMeter: 0.9, whorlCount: 0, spanStart: 0.26, spanEnd: 0.9,
      angleRoot: 1.2, angleEnd: 0.55, lenScale: 0.62, lenVar: 0.3, radScale: 0.62,
      segments: 9, jitter: 0.14, upBias: 0.07, sag: 0.34, tipLift: 0.16, taperPow: 0.95,
    },
    {
      perMeter: 2.0, whorlCount: 0, spanStart: 0.2, spanEnd: 0.98,
      angleRoot: 1.0, angleEnd: 0.55, lenScale: 0.5, lenVar: 0.34, radScale: 0.55,
      segments: 5, jitter: 0.16, upBias: 0.04, sag: 0.32, tipLift: 0.1, taperPow: 0.9,
    },
    {
      // dense distichous spray tier carrying the broad lobed leaves
      perMeter: 7.5, whorlCount: 0, spanStart: 0.15, spanEnd: 1.0,
      angleRoot: 0.9, angleEnd: 0.6, lenScale: 0.3, lenVar: 0.35, radScale: 0.55,
      segments: 3, jitter: 0.12, upBias: -0.02, sag: 0.18, tipLift: 0.05, taperPow: 0.85,
      flatten: 0.85,
    },
  ],
  canopy: {
    style: 'leafTuft',
    tier: 3,
    stride: 0.12,
    fromT: 0.1,
    sizeRange: [0.18, 0.28],
    tilt: 1.0,
    tuftRange: [2, 4],
    domeBlend: 0.72,
    twoRanked: true,
    plate: { mode: 'cross', scale: 2.45 },
    // broad, blunt, lightly lobed oak leaf
    blade: { len: 1.0, width: 0.62, pointiness: 0.9, fold: 0.26, curl: 0.18, needles: 0, radial: 0 },
  },
  buttress: { amp: 0.78, rise: 1.6, lobes: 7 },
  barkTiling: 5,
  leafColor: { r: 0.052, g: 0.125, b: 0.034, hueVar: 0.28 },
  woodTint: { r: 0.34, g: 0.29, b: 0.22 },
  snapAt: 0,
  stubOdds: 0.03,
};

export const CHERRY: TreeProfile = {
  id: 'cherry',
  label: 'Flowering cherry (broadleaf)',
  kind: 'broadleaf',
  height: [9, 14],
  girth: 0.022,
  crown: 'ellipsoid',
  crownLean: 0.28,
  tiers: [
    {
      perMeter: 0, whorlCount: 0, spanStart: 0, spanEnd: 0,
      angleRoot: 0, angleEnd: 0, lenScale: 0, lenVar: 0, radScale: 0,
      segments: 9, jitter: 0.06, upBias: 0.05, sag: 0, tipLift: 0, taperPow: 1.2,
    },
    {
      perMeter: 1.7, whorlCount: 0, spanStart: 0.22, spanEnd: 0.9,
      angleRoot: 1.15, angleEnd: 0.55, lenScale: 0.56, lenVar: 0.3, radScale: 0.52,
      segments: 7, jitter: 0.12, upBias: 0.1, sag: 0.24, tipLift: 0.16, taperPow: 0.95,
    },
    {
      perMeter: 2.6, whorlCount: 0, spanStart: 0.2, spanEnd: 0.98,
      angleRoot: 0.95, angleEnd: 0.55, lenScale: 0.46, lenVar: 0.32, radScale: 0.54,
      segments: 5, jitter: 0.14, upBias: 0.06, sag: 0.26, tipLift: 0.12, taperPow: 0.9,
    },
    {
      // fine flowering spurs — where the bloom-flecked tufts cluster
      perMeter: 8.5, whorlCount: 0, spanStart: 0.15, spanEnd: 1.0,
      angleRoot: 0.85, angleEnd: 0.6, lenScale: 0.26, lenVar: 0.36, radScale: 0.55,
      segments: 3, jitter: 0.11, upBias: 0.0, sag: 0.16, tipLift: 0.06, taperPow: 0.85,
      flatten: 0.7,
    },
  ],
  canopy: {
    style: 'leafTuft',
    tier: 3,
    stride: 0.1,
    fromT: 0.1,
    sizeRange: [0.14, 0.22],
    tilt: 0.95,
    tuftRange: [2, 3],
    domeBlend: 0.7,
    twoRanked: true,
    plate: { mode: 'cross', scale: 2.35 },
    blade: { len: 1.0, width: 0.46, pointiness: 1.3, fold: 0.24, curl: 0.2, needles: 0, radial: 0 },
  },
  buttress: { amp: 0.4, rise: 0.8, lobes: 5 },
  barkTiling: 4,
  // muted spring green; the bloom does most of the visual work
  leafColor: { r: 0.07, g: 0.135, b: 0.045, hueVar: 0.26 },
  bloom: { r: 0.82, g: 0.46, b: 0.55, frac: 0.62 }, // soft sakura pink
  woodTint: { r: 0.36, g: 0.27, b: 0.24 },
  snapAt: 0,
  stubOdds: 0.02,
};

export const TREE_CATALOG: readonly TreeProfile[] = [
  SPRUCE,
  PINE,
  BEECH,
  BIRCH,
  KARST_GNARL,
  SNAG,
  ELDER_OAK,
  CHERRY,
];
