/**
 * Assemble — profile + seed → renderable geometry.
 *
 * Grows the skeleton once, skins the wood into a bark buffer, and scatters
 * canopy cards into a foliage buffer. The two LOD knobs cut cost where it is
 * invisible: lower LODs stop the tube hierarchy below the leaf-bearing tier
 * (the cards already own that volume) and thin the card set to a fixed budget,
 * enlarging the survivors so painted coverage holds.
 */

import { Vector3 } from 'three';
import type { BufferGeometry } from 'three';
import type { SeedStream } from './SeedStream';
import { scatterCards } from './CardAtlas';
import { cultivate } from './Branching';
import { MeshForge } from './MeshForge';
import { extrudeSkeleton } from './Limbs';
import type { BranchTree, GrowthBias, TreeProfile } from './Botany';

export interface TreeMesh {
  bark: BufferGeometry;
  /** card foliage (atlas material) — null for snags */
  foliage: BufferGeometry | null;
  tree: BranchTree;
  metrics: { tris: number; tufts: number; limbs: number; height: number };
}

export function assembleTree(
  profile: TreeProfile,
  rng: SeedStream,
  opts?: {
    lod?: 0 | 1 | 2;
    bias?: Partial<GrowthBias>;
  },
): TreeMesh {
  const lod = opts?.lod ?? 1;
  const tree = cultivate(profile, rng, opts?.bias);

  // --- bark -----------------------------------------------------------------
  const leafTier = profile.canopy?.tier ?? 2;
  const barkForge = new MeshForge();
  const lodK = lod === 0 ? 1 : lod === 1 ? 0.6 : 0.32;
  const maxLevel =
    lod === 0 ? 99 : lod === 1 ? Math.max(1, leafTier - 1) : Math.max(1, leafTier - 2);
  extrudeSkeleton(barkForge, tree, rng.derive('bark'), {
    lodK,
    uTiling: profile.barkTiling,
    buttress: { ...profile.buttress, phase: rng.unit() * Math.PI * 2 },
    maxLevel,
    stride: lod === 2 ? 2 : 1,
  });
  const barkTris = barkForge.faceCount;
  const bark = barkForge.finish();

  // --- foliage --------------------------------------------------------------
  let foliage: BufferGeometry | null = null;
  let foliageTris = 0;
  if (profile.canopy && tree.tufts.length > 0) {
    const canopy = profile.canopy;
    const center = new Vector3(0, tree.crownY, 0);
    const radius = Math.max(tree.crownRadius, (tree.height - tree.crownY) * 0.9);
    // Thin tufts to a card budget and enlarge survivors (≈ sqrt of the thinning
    // factor preserves painted coverage), so a dense-tier species costs the
    // same as a sparse one. Near LODs keep more, smaller cards; far LODs keep
    // coverage with fewer, fatter cards.
    const budget = lod === 0 ? 5200 : lod === 1 ? 2600 : 300;
    const keepEvery = Math.max(1, Math.ceil(tree.tufts.length / budget));
    const tufts =
      keepEvery > 1 ? tree.tufts.filter((_, i) => i % keepEvery === 0) : tree.tufts;
    const sizeCap = lod === 2 ? 3.1 : 1.9;
    const plate =
      keepEvery > 1
        ? {
            ...canopy.plate,
            scale: canopy.plate.scale * Math.min(sizeCap, Math.sqrt(keepEvery) * 0.9 + 0.12),
          }
        : canopy.plate;
    const folForge = new MeshForge();
    scatterCards(folForge, tufts, plate, rng.derive('foliage'));
    folForge.blendToSphere(center, radius, canopy.domeBlend);
    folForge.bakeCrownShade(center, radius, 0.55);
    foliageTris += folForge.faceCount;
    foliage = folForge.finish();
  }

  return {
    bark,
    foliage,
    tree,
    metrics: {
      tris: barkTris + foliageTris,
      tufts: tree.tufts.length,
      limbs: tree.limbs.length,
      height: tree.height,
    },
  };
}
