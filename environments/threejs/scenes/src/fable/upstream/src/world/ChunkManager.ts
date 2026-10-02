import * as THREE from 'three';
import { STREAMING, WORLD, type QualitySettings } from '../config';
import type { Terrain } from './Terrain';
import { HeightField } from './Terrain';
import type { Biomes } from './Biomes';
import { GRASS_TILES_PER_CHUNK, type Vegetation, type TreePlacement } from './Vegetation';
import type { Props } from './Rocks';
import type { Water } from './Water';
import type { Interactables, Interactable } from './Interactables';
import type { Structures } from './Structures';
import type { Glow } from './Glow';
import type { MaterialLibrary } from '../procedural/Materials';
import type { CylinderCollider } from '../core/CameraController';

type VegLevel = 'detail' | 'detail-edge' | 'far';

interface Chunk {
  cx: number;
  cz: number;
  group: THREE.Group;
  terrainMesh: THREE.Mesh;
  /** read-through height/normal cache over this chunk's terrain grid */
  field: HeightField;
  waterMesh: THREE.Mesh | null;
  vegGroup: THREE.Group | null;
  grassGroup: THREE.Group | null;
  vegLevel: VegLevel | null;
  staticColliders: CylinderCollider[];
  vegColliders: CylinderCollider[];
  treePlacements: ReturnType<Vegetation['generateTreePlacements']> | null;
  interactable: Interactable | null;
}

interface TreeBatch {
  placements: Map<string, TreePlacement[]>;
  group: THREE.Object3D | null;
  dirty: boolean;
}

const DETAIL_TREE_BATCH_SIZE = STREAMING.detailTreeBatchSize;
const FAR_TREE_BATCH_SIZE = STREAMING.farTreeBatchSize;

function chunkKey(cx: number, cz: number): string {
  return `${cx},${cz}`;
}

function treeBatchKey(cx: number, cz: number, batchSize: number): string {
  return `${Math.floor(cx / batchSize)},${Math.floor(cz / batchSize)}`;
}

/**
 * Streams the world in chunks around the player. Terrain builds are budgeted
 * per frame so movement never hitches; vegetation swaps between a detailed
 * LOD (instanced trees, grass, props) and a far LOD (simplified trees, no
 * grass or shadows) based on distance.
 */
export class ChunkManager {
  private chunks = new Map<string, Chunk>();
  private buildQueue: Array<{ cx: number; cz: number }> = [];
  private queued = new Set<string>();
  private activeTerrainJob: {
    cx: number;
    cz: number;
    gen: Generator<void, THREE.BufferGeometry, void>;
  } | null = null;
  private grassBuildQueue: Array<{ key: string; tileIndex: number }> = [];
  private grassQueued = new Set<string>();
  private activeGrassJob: {
    key: string;
    gen: Generator<void, THREE.Group | null, void>;
  } | null = null;
  private totalBuilt = 0;
  private lastPcx = Number.NaN;
  private lastPcz = Number.NaN;
  private lodDirty = true;
  private detailTreeBatches = new Map<string, TreeBatch>();
  private edgeTreeBatches = new Map<string, TreeBatch>();
  private farTreeBatches = new Map<string, TreeBatch>();
  private contentVersion = 0;
  private colliderCacheVersion = -1;
  private colliderCachePcx = Number.NaN;
  private colliderCachePcz = Number.NaN;
  private colliderCache: CylinderCollider[] = [];
  private interactableCacheVersion = -1;
  private interactableCachePcx = Number.NaN;
  private interactableCachePcz = Number.NaN;
  private interactableCache: Interactable[] = [];

  constructor(
    private scene: THREE.Scene,
    private terrain: Terrain,
    private biomes: Biomes,
    private vegetation: Vegetation,
    private props: Props,
    private water: Water,
    private interactables: Interactables,
    private structures: Structures,
    private glow: Glow,
    private materials: MaterialLibrary,
    private quality: QualitySettings,
  ) {}

  /** Build the chunks directly around the spawn point synchronously. */
  warmup(playerPos: THREE.Vector3): void {
    const pcx = Math.floor(playerPos.x / WORLD.chunkSize);
    const pcz = Math.floor(playerPos.z / WORLD.chunkSize);
    for (let dz = -STREAMING.warmupRadius; dz <= STREAMING.warmupRadius; dz++) {
      for (let dx = -STREAMING.warmupRadius; dx <= STREAMING.warmupRadius; dx++) {
        this.buildChunk(pcx + dx, pcz + dz);
        this.updateChunkLOD(this.chunks.get(chunkKey(pcx + dx, pcz + dz))!, pcx, pcz);
      }
    }
    this.flushTreeBatches(Number.POSITIVE_INFINITY);
  }

  update(playerPos: THREE.Vector3): void {
    const size = WORLD.chunkSize;
    const pcx = Math.floor(playerPos.x / size);
    const pcz = Math.floor(playerPos.z / size);
    const radius = this.quality.viewRadius;

    const playerChunkChanged = pcx !== this.lastPcx || pcz !== this.lastPcz;
    if (playerChunkChanged) {
      this.lastPcx = pcx;
      this.lastPcz = pcz;
      this.lodDirty = true;

      // Chunk membership and distance bands only change when crossing a
      // chunk boundary, so avoid scanning the full streaming square every frame.
      for (let dz = -radius; dz <= radius; dz++) {
        for (let dx = -radius; dx <= radius; dx++) {
          const cx = pcx + dx;
          const cz = pcz + dz;
          const key = chunkKey(cx, cz);
          if (!this.chunks.has(key) && !this.queued.has(key)) {
            this.queued.add(key);
            this.buildQueue.push({ cx, cz });
          }
        }
      }

      this.buildQueue.sort(
        (a, b) =>
          (Math.abs(a.cx - pcx) + Math.abs(a.cz - pcz)) -
          (Math.abs(b.cx - pcx) + Math.abs(b.cz - pcz)),
      );
    }

    this.pumpChunkBuilds(pcx, pcz, radius);

    if (this.lodDirty) {
      // Unload chunks that drifted out of range, and adjust a bounded number
      // of LODs until every loaded chunk matches the current player chunk.
      let lodBudget = this.totalBuilt < STREAMING.warmupBuildThreshold
        ? STREAMING.warmupLodUpdatesPerFrame
        : STREAMING.lodUpdatesPerFrame;
      let remaining = false;
      for (const [key, chunk] of this.chunks) {
        const dist = Math.max(Math.abs(chunk.cx - pcx), Math.abs(chunk.cz - pcz));
        if (dist > radius + STREAMING.unloadPaddingChunks) {
          this.disposeChunk(chunk);
          this.chunks.delete(key);
          continue;
        }
        const detailRadius = this.quality.detailRadius;
        const desired: VegLevel =
          dist < detailRadius ? 'detail' : dist === detailRadius ? 'detail-edge' : 'far';
        if (chunk.vegLevel !== desired) {
          if (lodBudget > 0) {
            this.updateChunkLOD(chunk, pcx, pcz);
            lodBudget--;
          } else {
            remaining = true;
          }
        }
      }
      this.lodDirty = remaining;
    }
    this.buildNextGrassTile(playerPos);
    this.flushTreeBatches(performance.now() + STREAMING.treeBatchFlushBudgetMs);
    this.vegetation.updateGrassLod(playerPos);
  }

  /** True once all queued grass tiles have finished streaming in. */
  grassStreamingIdle(): boolean {
    return this.grassBuildQueue.length === 0 && this.activeGrassJob === null;
  }

  /** Debug summary of vegetation LOD states around a position. */
  debugLodSummary(pos: THREE.Vector3): string {
    const pcx = Math.floor(pos.x / WORLD.chunkSize);
    const pcz = Math.floor(pos.z / WORLD.chunkSize);
    const rows: string[] = [];
    for (let dz = -2; dz <= 2; dz++) {
      let row = '';
      for (let dx = -2; dx <= 2; dx++) {
        const c = this.chunks.get(chunkKey(pcx + dx, pcz + dz));
        row += c ? (c.vegLevel === 'detail' ? 'D' : c.vegLevel === 'detail-edge' ? 'E' : c.vegLevel === 'far' ? 'f' : '?') : '.';
      }
      rows.push(row);
    }
    return rows.join(' | ');
  }

  /** Solid obstacles within the player's 3x3 chunk neighbourhood. */
  collectCollidersNear(pos: THREE.Vector3): CylinderCollider[] {
    const pcx = Math.floor(pos.x / WORLD.chunkSize);
    const pcz = Math.floor(pos.z / WORLD.chunkSize);
    if (
      pcx === this.colliderCachePcx &&
      pcz === this.colliderCachePcz &&
      this.colliderCacheVersion === this.contentVersion
    ) {
      return this.colliderCache;
    }
    this.colliderCache.length = 0;
    for (let dz = -1; dz <= 1; dz++) {
      for (let dx = -1; dx <= 1; dx++) {
        const chunk = this.chunks.get(chunkKey(pcx + dx, pcz + dz));
        if (!chunk) continue;
        for (const c of chunk.staticColliders) this.colliderCache.push(c);
        for (const c of chunk.vegColliders) this.colliderCache.push(c);
      }
    }
    this.colliderCachePcx = pcx;
    this.colliderCachePcz = pcz;
    this.colliderCacheVersion = this.contentVersion;
    return this.colliderCache;
  }

  collectInteractablesNear(pos: THREE.Vector3): Interactable[] {
    const pcx = Math.floor(pos.x / WORLD.chunkSize);
    const pcz = Math.floor(pos.z / WORLD.chunkSize);
    if (
      pcx === this.interactableCachePcx &&
      pcz === this.interactableCachePcz &&
      this.interactableCacheVersion === this.contentVersion
    ) {
      return this.interactableCache;
    }
    this.interactableCache.length = 0;
    for (let dz = -1; dz <= 1; dz++) {
      for (let dx = -1; dx <= 1; dx++) {
        const chunk = this.chunks.get(chunkKey(pcx + dx, pcz + dz));
        if (chunk?.interactable) this.interactableCache.push(chunk.interactable);
      }
    }
    this.interactableCachePcx = pcx;
    this.interactableCachePcz = pcz;
    this.interactableCacheVersion = this.contentVersion;
    return this.interactableCache;
  }

  /** Rebuild only grass after live settings change, streamed back in over frames. */
  invalidateVegetation(): void {
    for (const chunk of this.chunks.values()) {
      if (chunk.grassGroup) {
        this.cancelGrassQueue(chunkKey(chunk.cx, chunk.cz));
        this.vegetation.unregisterGrass(chunk.grassGroup);
        this.disposeObject(chunk.grassGroup);
        chunk.group.remove(chunk.grassGroup);
        chunk.grassGroup = null;
      }
      if (chunk.vegLevel && chunk.vegLevel !== 'far') this.queueGrass(chunk);
    }
    this.contentVersion++;
  }

  /**
   * Stream chunk builds under a per-frame time budget. The terrain geometry
   * (thousands of analytic samples) is generated incrementally so crossing a
   * chunk boundary spreads the work over several frames instead of spiking one.
   * Only one chunk is in flight at a time; the rest of the chunk (water,
   * interactable, registration) is finalized once its geometry completes.
   */
  private pumpChunkBuilds(pcx: number, pcz: number, radius: number): void {
    const budget = this.totalBuilt < STREAMING.warmupBuildThreshold
      ? STREAMING.warmupChunkBuildBudgetMs
      : STREAMING.chunkBuildBudgetMs;
    const deadline = performance.now() + budget;
    while (performance.now() < deadline) {
      if (!this.activeTerrainJob) {
        const task = this.takeNextBuildTask(pcx, pcz, radius);
        if (!task) return;
        this.activeTerrainJob = {
          cx: task.cx,
          cz: task.cz,
          gen: this.terrain.streamChunkGeometry(task.cx, task.cz, this.quality.terrainSegments, this.biomes),
        };
      }
      let step = this.activeTerrainJob.gen.next();
      while (!step.done && performance.now() < deadline) step = this.activeTerrainJob.gen.next();
      if (!step.done) return; // out of time mid-chunk; resume next frame

      const job = this.activeTerrainJob;
      this.activeTerrainJob = null;
      this.queued.delete(chunkKey(job.cx, job.cz));
      const inRange = Math.abs(job.cx - pcx) <= radius && Math.abs(job.cz - pcz) <= radius;
      if (inRange && !this.chunks.has(chunkKey(job.cx, job.cz))) {
        this.finalizeChunk(job.cx, job.cz, step.value);
        this.lodDirty = true;
      } else {
        step.value.dispose(); // drifted out of range / already built while building
      }
    }
  }

  /** Pop the nearest still-relevant queued chunk; returns null if none. */
  private takeNextBuildTask(pcx: number, pcz: number, radius: number): { cx: number; cz: number } | null {
    while (this.buildQueue.length > 0) {
      const task = this.buildQueue.shift()!;
      const key = chunkKey(task.cx, task.cz);
      const inRange = Math.abs(task.cx - pcx) <= radius && Math.abs(task.cz - pcz) <= radius;
      if (!inRange || this.chunks.has(key)) {
        this.queued.delete(key);
        continue;
      }
      // Leave `key` in `queued` until the chunk finalizes so the membership
      // scan can't re-queue it while its geometry is still being built.
      return task;
    }
    return null;
  }

  /** Synchronous build (used only at warmup, where a brief load is acceptable). */
  private buildChunk(cx: number, cz: number): void {
    if (this.chunks.has(chunkKey(cx, cz))) return;
    const geometry = this.terrain.buildChunkGeometry(cx, cz, this.quality.terrainSegments, this.biomes);
    this.finalizeChunk(cx, cz, geometry);
  }

  /** Assemble the rest of a chunk around its (already-built) terrain geometry. */
  private finalizeChunk(cx: number, cz: number, geometry: THREE.BufferGeometry): void {
    const key = chunkKey(cx, cz);
    const group = new THREE.Group();

    // Terrain.
    const terrainMesh = new THREE.Mesh(geometry, this.materials.terrain);
    terrainMesh.position.set(cx * WORLD.chunkSize, 0, cz * WORLD.chunkSize);
    terrainMesh.receiveShadow = true;
    terrainMesh.castShadow = false;
    terrainMesh.userData.ownsGeometry = true;
    group.add(terrainMesh);

    // Reuse the heights the terrain mesh just baked so vegetation can sample the
    // ground without re-evaluating the analytic noise field thousands of times.
    const field = new HeightField(
      this.terrain, geometry, this.quality.terrainSegments, cx * WORLD.chunkSize, cz * WORLD.chunkSize,
    );

    // Water (only where terrain dips below the surface).
    const waterMesh = this.water.buildChunkWater(cx, cz, this.terrain);
    if (waterMesh) {
      waterMesh.userData.ownsGeometry = true;
      group.add(waterMesh);
    }

    // Interactable point of interest (sparse).
    const staticColliders: CylinderCollider[] = [];
    let interactable: Interactable | null = null;
    const poi = this.interactables.maybeCreateForChunk(cx, cz, this.terrain, this.biomes);
    if (poi) {
      interactable = poi.interactable;
      group.add(poi.interactable.object);
      staticColliders.push(...poi.colliders);
    }

    // Fantasy landmark (rarer still; spaced by super-cell).
    const landmark = this.structures.maybeBuildForChunk(cx, cz, this.terrain, this.biomes);
    if (landmark) {
      group.add(landmark.group);
      staticColliders.push(...landmark.colliders);
    }

    this.freezeStaticMatrices(group);
    this.scene.add(group);
    this.totalBuilt++;
    this.contentVersion++;
    this.chunks.set(key, {
      cx,
      cz,
      group,
      terrainMesh,
      field,
      waterMesh,
      vegGroup: null,
      grassGroup: null,
      vegLevel: null,
      staticColliders,
      vegColliders: [],
      treePlacements: null,
      interactable,
    });
  }

  /** Swap vegetation LOD when the chunk's distance band changes. */
  private updateChunkLOD(chunk: Chunk, pcx: number, pcz: number): boolean {
    const dist = Math.max(Math.abs(chunk.cx - pcx), Math.abs(chunk.cz - pcz));
    const detailRadius = this.quality.detailRadius;
    const desired: VegLevel =
      dist < detailRadius ? 'detail' : dist === detailRadius ? 'detail-edge' : 'far';
    if (chunk.vegLevel === desired) return false;

    // Grass lives outside the band swap: it is built once per chunk and only
    // torn down when the chunk drops to the far band or unloads. Distance
    // thinning is handled per-tile in Vegetation.updateGrassLod.
    if (desired === 'far' && (chunk.grassGroup || this.grassQueued.has(chunkKey(chunk.cx, chunk.cz)))) {
      this.cancelGrassQueue(chunkKey(chunk.cx, chunk.cz));
      if (chunk.grassGroup) {
        this.vegetation.unregisterGrass(chunk.grassGroup);
        this.disposeObject(chunk.grassGroup);
        chunk.group.remove(chunk.grassGroup);
        chunk.grassGroup = null;
      }
    }

    // detail <-> detail-edge: props, glow, colliders, and tree placements are
    // identical in both bands - only shadow flags differ. Move the built tree
    // batch and flip shadows instead of disposing and regenerating the chunk.
    if (
      chunk.vegGroup &&
      chunk.vegLevel &&
      chunk.vegLevel !== 'far' &&
      desired !== 'far'
    ) {
      const from = chunk.vegLevel === 'detail' ? this.detailTreeBatches : this.edgeTreeBatches;
      const to = desired === 'detail' ? this.detailTreeBatches : this.edgeTreeBatches;
      this.transferTreeBatch(from, to, chunk, desired === 'detail');
      chunk.vegLevel = desired;
      if (!chunk.grassGroup) this.queueGrass(chunk);
      this.contentVersion++;
      return true;
    }

    if (chunk.vegGroup) {
      if (chunk.vegLevel === 'far') this.unregisterTrees(this.farTreeBatches, chunk, FAR_TREE_BATCH_SIZE);
      else if (chunk.vegLevel === 'detail-edge') {
        this.unregisterTrees(this.edgeTreeBatches, chunk, DETAIL_TREE_BATCH_SIZE);
      } else if (chunk.vegLevel) {
        this.unregisterTrees(this.detailTreeBatches, chunk, DETAIL_TREE_BATCH_SIZE);
      }
      this.disposeObject(chunk.vegGroup);
      chunk.group.remove(chunk.vegGroup);
      chunk.vegGroup = null;
      chunk.vegColliders = [];
    }

    const placements =
      chunk.treePlacements ??
      (chunk.treePlacements = this.vegetation.generateTreePlacements(chunk.cx, chunk.cz, this.terrain, this.biomes, chunk.field));
    const vegGroup = new THREE.Group();

    if (desired !== 'far') {
      const batches = desired === 'detail' ? this.detailTreeBatches : this.edgeTreeBatches;
      this.registerTrees(batches, chunk, placements, DETAIL_TREE_BATCH_SIZE);
      chunk.vegColliders = this.vegetation.buildTreeColliders(placements);

      const propsBuilt = this.props.buildProps(chunk.cx, chunk.cz, this.terrain, this.biomes, true, chunk.field);
      vegGroup.add(propsBuilt.group);
      chunk.vegColliders.push(...propsBuilt.colliders);

      // Bioluminescent night life only near the player (detail band).
      const glowGroup = this.glow.buildForChunk(chunk.cx, chunk.cz, this.terrain, this.biomes, chunk.field);
      if (glowGroup) vegGroup.add(glowGroup);
    } else {
      // Far chunks: batched simplified tree templates (no shadows/grass).
      this.registerTrees(this.farTreeBatches, chunk, placements, FAR_TREE_BATCH_SIZE);

      // Boulders still render at distance (they shape the silhouette).
      const propsBuilt = this.props.buildProps(chunk.cx, chunk.cz, this.terrain, this.biomes, false, chunk.field);
      vegGroup.add(propsBuilt.group);
    }

    chunk.group.add(vegGroup);
    this.freezeStaticMatrices(vegGroup);
    chunk.vegGroup = vegGroup;
    chunk.vegLevel = desired;
    if (desired !== 'far' && !chunk.grassGroup) this.queueGrass(chunk);
    this.contentVersion++;
    return true;
  }

  /**
   * Move a chunk's trees between the shadowed and unshadowed batch maps. The
   * common case (one chunk per detail batch) reuses the existing meshes and
   * only flips shadow flags, avoiding a rebuild on every boundary crossing.
   */
  private transferTreeBatch(
    from: Map<string, TreeBatch>,
    to: Map<string, TreeBatch>,
    chunk: Chunk,
    shadows: boolean,
  ): void {
    if (from === to) return;
    const bKey = treeBatchKey(chunk.cx, chunk.cz, DETAIL_TREE_BATCH_SIZE);
    const cKey = chunkKey(chunk.cx, chunk.cz);
    const src = from.get(bKey);
    if (
      src?.group &&
      !src.dirty &&
      src.placements.size === 1 &&
      src.placements.has(cKey) &&
      !to.has(bKey)
    ) {
      from.delete(bKey);
      src.group.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.castShadow = shadows;
          mesh.receiveShadow = shadows;
        }
      });
      to.set(bKey, src);
      return;
    }
    const placements = src?.placements.get(cKey) ?? chunk.treePlacements!;
    this.unregisterTrees(from, chunk, DETAIL_TREE_BATCH_SIZE);
    this.registerTrees(to, chunk, placements, DETAIL_TREE_BATCH_SIZE);
  }

  private queueGrass(chunk: Chunk): void {
    const key = chunkKey(chunk.cx, chunk.cz);
    if (this.grassQueued.has(key)) return;
    this.grassQueued.add(key);
    // Grass hangs off the chunk root so tree/prop band swaps never touch it.
    const grassGroup = new THREE.Group();
    chunk.group.add(grassGroup);
    chunk.grassGroup = grassGroup;
    for (let tileIndex = 0; tileIndex < GRASS_TILES_PER_CHUNK; tileIndex++) {
      this.grassBuildQueue.push({ key, tileIndex });
    }
  }

  private cancelGrassQueue(key: string): void {
    if (this.activeGrassJob?.key === key) {
      // Abort the in-flight tile; the generator's cleanup releases its
      // partially filled instance buffers.
      this.activeGrassJob.gen.return(null);
      this.activeGrassJob = null;
    }
    if (!this.grassQueued.delete(key)) return;
    this.grassBuildQueue = this.grassBuildQueue.filter((task) => task.key !== key);
  }

  private takeNearestGrassTask(
    playerPos: THREE.Vector3,
  ): { key: string; tileIndex: number } | null {
    if (this.grassBuildQueue.length === 0) return null;
    let nearestIndex = 0;
    let nearestDistSq = Number.POSITIVE_INFINITY;
    const tilesPerSide = Math.sqrt(GRASS_TILES_PER_CHUNK);
    const tileSize = WORLD.chunkSize / tilesPerSide;
    for (let i = 0; i < this.grassBuildQueue.length; i++) {
      const task = this.grassBuildQueue[i];
      const chunk = this.chunks.get(task.key);
      if (!chunk) continue;
      const tx = task.tileIndex % tilesPerSide;
      const tz = Math.floor(task.tileIndex / tilesPerSide);
      const dx = chunk.cx * WORLD.chunkSize + (tx + 0.5) * tileSize - playerPos.x;
      const dz = chunk.cz * WORLD.chunkSize + (tz + 0.5) * tileSize - playerPos.z;
      const distSq = dx * dx + dz * dz;
      if (distSq < nearestDistSq) {
        nearestDistSq = distSq;
        nearestIndex = i;
      }
    }
    return this.grassBuildQueue.splice(nearestIndex, 1)[0];
  }

  private finishGrassTask(key: string): void {
    if (!this.grassBuildQueue.some((pending) => pending.key === key)) {
      this.grassQueued.delete(key);
    }
  }

  /**
   * Time-sliced grass streaming. Tile generation is dominated by analytic
   * terrain sampling, so instead of building one whole tile per frame (which
   * spikes when the detail-edge ring loads), the tile generator is pumped
   * row by row until the frame budget runs out and resumed next frame.
   */
  private buildNextGrassTile(playerPos: THREE.Vector3): void {
    const budget = this.totalBuilt < STREAMING.warmupBuildThreshold
      ? STREAMING.warmupGrassBuildBudgetMs
      : STREAMING.grassBuildBudgetMs;
    const deadline = performance.now() + budget;
    for (;;) {
      if (!this.activeGrassJob) {
        const task = this.takeNearestGrassTask(playerPos);
        if (!task) return;
        const chunk = this.chunks.get(task.key);
        if (!chunk || chunk.vegLevel === 'far' || !chunk.grassGroup) {
          this.finishGrassTask(task.key);
          continue;
        }
        this.activeGrassJob = {
          key: task.key,
          gen: this.vegetation.buildGrassTile(
            chunk.cx,
            chunk.cz,
            task.tileIndex,
            this.terrain,
            this.biomes,
            chunk.field,
          ),
        };
      }
      let step: IteratorResult<void, THREE.Group | null>;
      do {
        step = this.activeGrassJob.gen.next();
      } while (!step.done && performance.now() < deadline);
      if (!step.done) return; // Out of time mid-tile; resume next frame.
      const { key } = this.activeGrassJob;
      this.activeGrassJob = null;
      const chunk = this.chunks.get(key);
      const grass = step.value;
      if (grass && chunk?.grassGroup && chunk.vegLevel !== 'far') {
        chunk.grassGroup.add(grass);
        this.freezeStaticMatrices(grass);
      } else if (grass) {
        this.vegetation.unregisterGrass(grass);
        this.disposeObject(grass);
      }
      this.finishGrassTask(key);
      if (performance.now() >= deadline) return;
    }
  }

  private disposeChunk(chunk: Chunk): void {
    this.cancelGrassQueue(chunkKey(chunk.cx, chunk.cz));
    if (chunk.vegLevel === 'far') this.unregisterTrees(this.farTreeBatches, chunk, FAR_TREE_BATCH_SIZE);
    else if (chunk.vegLevel === 'detail-edge') {
      this.unregisterTrees(this.edgeTreeBatches, chunk, DETAIL_TREE_BATCH_SIZE);
    } else if (chunk.vegLevel) {
      this.unregisterTrees(this.detailTreeBatches, chunk, DETAIL_TREE_BATCH_SIZE);
    }
    this.vegetation.unregisterGrass(chunk.group);
    this.disposeObject(chunk.group);
    this.scene.remove(chunk.group);
    this.contentVersion++;
  }

  private registerTrees(
    batches: Map<string, TreeBatch>,
    chunk: Chunk,
    placements: TreePlacement[],
    batchSize: number,
  ): void {
    const key = treeBatchKey(chunk.cx, chunk.cz, batchSize);
    let batch = batches.get(key);
    if (!batch) {
      batch = { placements: new Map(), group: null, dirty: true };
      batches.set(key, batch);
    }
    batch.placements.set(chunkKey(chunk.cx, chunk.cz), placements);
    batch.dirty = true;
  }

  private unregisterTrees(batches: Map<string, TreeBatch>, chunk: Chunk, batchSize: number): void {
    const key = treeBatchKey(chunk.cx, chunk.cz, batchSize);
    const batch = batches.get(key);
    if (!batch) return;
    batch.placements.delete(chunkKey(chunk.cx, chunk.cz));
    batch.dirty = true;
  }

  /**
   * Rebuild dirty tree batches under a frame-time budget. Nearby (detail)
   * batches flush first; whatever misses the deadline stays dirty and is
   * picked up on the following frames, spreading boundary-crossing churn.
   */
  private flushTreeBatches(deadline: number): void {
    this.flushTreeBatchMap(this.detailTreeBatches, 'detail', deadline);
    // The edge ring lies outside the 95 m shadow frustum. Keeping it out of
    // the shadow pass avoids submitting whole batched sectors for no result.
    this.flushTreeBatchMap(this.edgeTreeBatches, 'edge', deadline);
    this.flushTreeBatchMap(this.farTreeBatches, 'far', deadline);
  }

  private flushTreeBatchMap(
    batches: Map<string, TreeBatch>,
    lod: 'detail' | 'edge' | 'far',
    deadline: number,
  ): void {
    for (const [key, batch] of batches) {
      if (!batch.dirty) continue;
      if (performance.now() >= deadline) return;
      if (batch.group) {
        this.disposeObject(batch.group);
        this.scene.remove(batch.group);
        batch.group = null;
      }
      if (batch.placements.size === 0) {
        batches.delete(key);
        continue;
      }

      let total = 0;
      for (const chunkPlacements of batch.placements.values()) total += chunkPlacements.length;
      const placements = new Array<TreePlacement>(total);
      let offset = 0;
      for (const chunkPlacements of batch.placements.values()) {
        for (let i = 0; i < chunkPlacements.length; i++) {
          placements[offset++] = chunkPlacements[i];
        }
      }
      const trees =
        lod === 'far'
          ? this.vegetation.buildFarTrees(placements)
          : this.vegetation.buildDetailedTrees(placements, lod === 'detail');
      this.scene.add(trees);
      this.freezeStaticMatrices(trees);
      batch.group = trees;
      batch.dirty = false;
    }
  }

  /** Static chunk objects never need local or world matrices recomputed per frame. */
  private freezeStaticMatrices(root: THREE.Object3D): void {
    root.updateMatrixWorld(true);
    root.traverse((obj) => {
      obj.updateMatrix();
      obj.matrixAutoUpdate = false;
      obj.matrixWorldAutoUpdate = false;
    });
  }

  /**
   * Dispose per-chunk GPU resources. Shared template geometries/materials
   * are left alone; per-chunk geometry (terrain, water, merged far trees,
   * interactable parts) is tagged with userData.ownsGeometry, and
   * InstancedMesh.dispose() frees per-chunk instance attribute buffers
   * without touching the shared template geometry.
   */
  private disposeObject(root: THREE.Object3D): void {
    root.traverse((obj) => {
      const instanced = obj as THREE.InstancedMesh;
      if (instanced.isInstancedMesh) {
        instanced.dispose();
        return;
      }
      const mesh = obj as THREE.Mesh;
      if (mesh.isMesh && mesh.userData.ownsGeometry) {
        mesh.geometry.dispose();
      }
      const sprite = obj as THREE.Sprite;
      if (sprite.isSprite) {
        sprite.material.dispose();
      }
      const points = obj as THREE.Points;
      if (points.isPoints && points.userData.ownsGeometry) {
        points.geometry.dispose();
      }
    });
  }

}
