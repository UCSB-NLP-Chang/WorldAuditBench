import * as THREE from 'three';
import { Noise2D } from '../procedural/Noise';
import { combineSeed } from '../utils/Random';
import { WORLD } from '../config';
import { smoothstep } from '../utils/MathUtils';
import type { Biomes } from './Biomes';

/**
 * Analytic terrain height field. Height is a pure function of (x, z) and the
 * seed, so chunks line up perfectly, normals are continuous across borders,
 * and the player can query the ground anywhere via getHeightAt.
 *
 * Layers:
 *  - low-frequency "continent" noise (lakes form where it dips below 0)
 *  - rolling hills (mid-frequency fBm)
 *  - ridged mountains gated by a mountain mask
 *  - high-frequency detail so the ground isn't a rubber sheet
 *  - domain warping on top so nothing looks grid-aligned
 */
export class Terrain {
  private warpNoiseX: Noise2D;
  private warpNoiseZ: Noise2D;
  private continentNoise: Noise2D;
  private hillNoise: Noise2D;
  private rangeNoise: Noise2D;
  private ridgeNoise: Noise2D;
  private craggyNoise: Noise2D;
  private detailNoise: Noise2D;

  /** Grid step of the rendered terrain mesh (for mesh-matched sampling). */
  private gridStep: number;

  constructor(seed: number, terrainSegments: number) {
    this.gridStep = WORLD.chunkSize / terrainSegments;
    this.warpNoiseX = new Noise2D(combineSeed(seed, 101));
    this.warpNoiseZ = new Noise2D(combineSeed(seed, 102));
    this.continentNoise = new Noise2D(combineSeed(seed, 103));
    this.hillNoise = new Noise2D(combineSeed(seed, 104));
    this.rangeNoise = new Noise2D(combineSeed(seed, 105));
    this.ridgeNoise = new Noise2D(combineSeed(seed, 106));
    this.detailNoise = new Noise2D(combineSeed(seed, 107));
    this.craggyNoise = new Noise2D(combineSeed(seed, 108));
  }

  /**
   * Range mask in [0, 1]: where mountain massifs live. Very low frequency,
   * so each range is a kilometres-wide domain instead of a lone peak.
   */
  getRangeMask(x: number, z: number): number {
    const W = WORLD;
    const r = this.rangeNoise.fbm(x * W.rangeFreq, z * W.rangeFreq, 3);
    return smoothstep(0.02, 0.62, r);
  }

  getHeightAt(x: number, z: number): number {
    const W = WORLD;

    // Domain warp breaks up directional noise artifacts and bends ranges
    // into curved, natural-looking arcs.
    const wx = x + this.warpNoiseX.fbm(x * W.warpFreq, z * W.warpFreq, 3) * W.warpAmp;
    const wz = z + this.warpNoiseZ.fbm(x * W.warpFreq, z * W.warpFreq, 3) * W.warpAmp;

    const continent = this.continentNoise.fbm(wx * W.continentFreq, wz * W.continentFreq, 3);
    let h = continent * W.continentAmp;

    // Mountain ranges: wide, smooth massif domains. The same noise drives a
    // wider foothill apron so ranges rise gradually out of the lowlands.
    const rangeRaw = this.rangeNoise.fbm(wx * W.rangeFreq, wz * W.rangeFreq, 3);
    const rangeMask = smoothstep(0.02, 0.62, rangeRaw);
    const foothill = smoothstep(-0.32, 0.62, rangeRaw);

    // Rolling hills, damped near lake basins (gentle shores) and inside
    // mountain domains (the massif supplies its own relief).
    const hills = this.hillNoise.fbm(wx * W.hillFreq, wz * W.hillFreq, 5);
    const basinDamp = smoothstep(-0.55, 0.1, continent);
    h += hills * W.hillAmp * (0.35 + 0.65 * basinDamp) * (1 - rangeMask * 0.6);

    h += foothill * foothill * W.foothillAmp;

    if (rangeMask > 0.002) {
      // Average spaced ridged taps into broad connected spines; a single
      // sharp ridged octave reads as isolated artificial cones.
      const spread = 110;
      // softness rounds the ridge crests so steep crests stay smooth at the
      // mesh resolution instead of aliasing into jagged triangulated edges.
      const rs = W.ridgeSoftness;
      const ridge =
        this.ridgeNoise.ridged(wx * W.ridgeFreq, wz * W.ridgeFreq, 4, 2.02, 0.5, rs) * 0.5 +
        this.ridgeNoise.ridged((wx + spread) * W.ridgeFreq, (wz - spread) * W.ridgeFreq, 4, 2.02, 0.5, rs) * 0.25 +
        this.ridgeNoise.ridged((wx - spread) * W.ridgeFreq, (wz + spread) * W.ridgeFreq, 4, 2.02, 0.5, rs) * 0.25;
      const crest = smoothstep(0.18, 0.88, ridge);
      // Mass term: most of the budget is the broad body of the massif, the
      // crest carves the skyline on top of it.
      const mass = Math.pow(rangeMask, 1.4) * (0.34 + 0.66 * crest * crest * (3 - 2 * crest));
      h += mass * W.mountainAmp;

      // Mid-frequency rocky relief on the flanks (rounded shapes, not spikes;
      // the softness keeps the little creases from reading as sharp shards).
      const craggy = this.craggyNoise.ridged(wx * W.craggyFreq, wz * W.craggyFreq, 2, 2.1, 0.5, W.craggySoftness);
      h += (craggy - 0.5) * W.craggyAmp * rangeMask;
    }

    // Fine surface detail, faded inside mountain domains so steep faces stay
    // smooth at the mesh resolution instead of aliasing into jagged shards.
    h += this.detailNoise.fbm(x * W.detailFreq, z * W.detailFreq, 2) * W.detailAmp * (1 - rangeMask * 0.65);

    return h;
  }

  /**
   * Height of the *rendered* triangle mesh at (x, z): bilinear interpolation
   * between the same grid samples the chunk geometry uses. Placing grass,
   * props, and the player with this (instead of the analytic field) keeps
   * everything glued to the visible ground — nothing floats or sinks.
   */
  getMeshHeightAt(x: number, z: number): number {
    const s = this.gridStep;
    const gx = Math.floor(x / s);
    const gz = Math.floor(z / s);
    const fx = x / s - gx;
    const fz = z / s - gz;
    const h00 = this.getHeightAt(gx * s, gz * s);
    const h10 = this.getHeightAt((gx + 1) * s, gz * s);
    const h01 = this.getHeightAt(gx * s, (gz + 1) * s);
    const h11 = this.getHeightAt((gx + 1) * s, (gz + 1) * s);
    // Match the triangle split used in the chunk index buffer (a-c-b / b-c-d).
    if (fx + fz <= 1) {
      return h00 + (h10 - h00) * fx + (h01 - h00) * fz;
    }
    return h11 + (h01 - h11) * (1 - fx) + (h10 - h11) * (1 - fz);
  }

  /**
   * Surface normal from central differences of the height field. `e` is the
   * sampling stencil half-width; callers building mesh geometry pass their
   * grid step so the normal describes the rendered triangles (smooth shading)
   * rather than sub-triangle detail the mesh can't show (faceted shading).
   */
  getNormalAt(x: number, z: number, out: THREE.Vector3, e = 1.2): THREE.Vector3 {
    const hL = this.getHeightAt(x - e, z);
    const hR = this.getHeightAt(x + e, z);
    const hD = this.getHeightAt(x, z - e);
    const hU = this.getHeightAt(x, z + e);
    out.set(hL - hR, 2 * e, hD - hU);
    return out.normalize();
  }

  /**
   * Build one chunk's terrain geometry synchronously (used at warmup). Vertices
   * are local to the chunk origin (the mesh is positioned at cx*size, 0,
   * cz*size). Vertex colors encode the biome blend.
   */
  buildChunkGeometry(cx: number, cz: number, segments: number, biomes: Biomes): THREE.BufferGeometry {
    const gen = this.streamChunkGeometry(cx, cz, segments, biomes);
    let step = gen.next();
    while (!step.done) step = gen.next();
    return step.value;
  }

  /**
   * Same geometry build as a generator so the chunk streamer can spread the
   * thousands of analytic height/normal samples across several frames instead
   * of spiking a frame whenever a new chunk loads. Yields between vertex-row
   * batches; the result (returned when done) is byte-identical to the
   * synchronous build, so nothing about the terrain changes — only when the
   * work happens.
   */
  *streamChunkGeometry(
    cx: number,
    cz: number,
    segments: number,
    biomes: Biomes,
  ): Generator<void, THREE.BufferGeometry, void> {
    const size = WORLD.chunkSize;
    const originX = cx * size;
    const originZ = cz * size;
    const vertsPerSide = segments + 1;

    const positions = new Float32Array(vertsPerSide * vertsPerSide * 3);
    const normals = new Float32Array(vertsPerSide * vertsPerSide * 3);
    const colors = new Float32Array(vertsPerSide * vertsPerSide * 3);
    const uvs = new Float32Array(vertsPerSide * vertsPerSide * 2);
    const snowAmount = new Float32Array(vertsPerSide * vertsPerSide);
    const splat = new Float32Array(vertsPerSide * vertsPerSide * 4);
    const indices = new Uint32Array(segments * segments * 6);

    const normal = new THREE.Vector3();
    const color = new THREE.Color();

    // Sample normals slightly wider than the mesh grid so every vertex normal
    // reflects the slope of the triangles meeting it. A fixed fine stencil
    // captured detail finer than the geometry, which made steep ridges shade
    // as jagged facets that didn't match the surface. normalSmoothness scales
    // the stencil: higher = softer shading across sharp ridges. Floored at a
    // small positive width so a value of 0 still yields valid normals (sharp
    // shading) instead of a zero-length normal that lights to black.
    const normalStencil = Math.max((size / segments) * WORLD.normalSmoothness, 0.05);

    let vi = 0;
    let uvi = 0;
    let si = 0;
    for (let iz = 0; iz < vertsPerSide; iz++) {
      // Yield every few rows so the streamer can time-slice this across frames.
      if (iz > 0 && iz % 4 === 0) yield;
      for (let ix = 0; ix < vertsPerSide; ix++) {
        const lx = (ix / segments) * size;
        const lz = (iz / segments) * size;
        const wxp = originX + lx;
        const wzp = originZ + lz;

        const h = this.getHeightAt(wxp, wzp);
        positions[vi] = lx;
        positions[vi + 1] = h;
        positions[vi + 2] = lz;

        // Analytic normals keep chunk borders seamless (computeVertexNormals
        // would produce visible seams at edges).
        this.getNormalAt(wxp, wzp, normal, normalStencil);
        normals[vi] = normal.x;
        normals[vi + 1] = normal.y;
        normals[vi + 2] = normal.z;

        biomes.getGroundColor(wxp, wzp, h, normal.y, color);
        colors[vi] = color.r;
        colors[vi + 1] = color.g;
        colors[vi + 2] = color.b;

        uvs[uvi] = wxp / size;
        uvs[uvi + 1] = wzp / size;

        snowAmount[si] = biomes.getSnowFactor(wxp, wzp, h, normal.y);
        biomes.getSplatWeights(wxp, wzp, h, normal.y, splat, si * 4);

        vi += 3;
        uvi += 2;
        si++;
      }
    }

    let ii = 0;
    for (let iz = 0; iz < segments; iz++) {
      for (let ix = 0; ix < segments; ix++) {
        const a = iz * vertsPerSide + ix;
        const b = a + 1;
        const c = a + vertsPerSide;
        const d = c + 1;
        indices[ii++] = a;
        indices[ii++] = c;
        indices[ii++] = b;
        indices[ii++] = b;
        indices[ii++] = c;
        indices[ii++] = d;
      }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    geometry.setAttribute('aSnow', new THREE.BufferAttribute(snowAmount, 1));
    geometry.setAttribute('aSplat', new THREE.BufferAttribute(splat, 4));
    geometry.setIndex(new THREE.BufferAttribute(indices, 1));
    geometry.computeBoundingSphere();
    return geometry;
  }
}

/**
 * Read-through height/normal cache for one chunk, backed by the heights the
 * terrain mesh already baked into `geometry.position.y` at each grid node.
 *
 * Scattering grass, trees, and props means sampling the ground thousands of
 * times per chunk; doing that against the analytic field re-evaluates dozens of
 * noise octaves per query. This reuses the already-computed grid instead:
 * `meshHeight()` returns *exactly* what `Terrain.getMeshHeightAt()` would (same
 * grid corners, same triangle split), and normals come from grid central
 * differences. Samples that fall outside the chunk's own grid (the seam rows)
 * fall back to the analytic terrain so nothing shifts at chunk borders.
 */
export class HeightField {
  private readonly heights: ArrayLike<number>;
  private readonly n: number; // vertices per side
  private readonly step: number;

  constructor(
    private readonly terrain: Terrain,
    geometry: THREE.BufferGeometry,
    segments: number,
    private readonly originX: number,
    private readonly originZ: number,
  ) {
    this.heights = (geometry.getAttribute('position') as THREE.BufferAttribute).array;
    this.n = segments + 1;
    this.step = WORLD.chunkSize / segments;
  }

  private node(ix: number, iz: number): number {
    return this.heights[(iz * this.n + ix) * 3 + 1] as number;
  }

  /** Rendered-mesh height: exact within the chunk, analytic at the seam. */
  meshHeight(x: number, z: number): number {
    const lx = (x - this.originX) / this.step;
    const lz = (z - this.originZ) / this.step;
    const gx = Math.floor(lx);
    const gz = Math.floor(lz);
    if (gx < 0 || gz < 0 || gx + 1 >= this.n || gz + 1 >= this.n) {
      return this.terrain.getMeshHeightAt(x, z);
    }
    const fx = lx - gx;
    const fz = lz - gz;
    const h00 = this.node(gx, gz);
    const h10 = this.node(gx + 1, gz);
    const h01 = this.node(gx, gz + 1);
    const h11 = this.node(gx + 1, gz + 1);
    if (fx + fz <= 1) return h00 + (h10 - h00) * fx + (h01 - h00) * fz;
    return h11 + (h01 - h11) * (1 - fx) + (h10 - h11) * (1 - fz);
  }

  /** Ground height used by biome rules (bilinear; analytic at the seam). */
  height(x: number, z: number): number {
    return this.meshHeight(x, z);
  }

  /** Surface normal from grid central differences; analytic at the seam. */
  normal(x: number, z: number, out: THREE.Vector3): THREE.Vector3 {
    const lx = (x - this.originX) / this.step;
    const lz = (z - this.originZ) / this.step;
    const gx = Math.floor(lx);
    const gz = Math.floor(lz);
    if (gx - 1 < 0 || gz - 1 < 0 || gx + 2 >= this.n || gz + 2 >= this.n) {
      return this.terrain.getNormalAt(x, z, out);
    }
    const d = this.step;
    const hl = this.meshHeight(x - d, z);
    const hr = this.meshHeight(x + d, z);
    const hd = this.meshHeight(x, z - d);
    const hu = this.meshHeight(x, z + d);
    out.set(hl - hr, 2 * d, hd - hu);
    return out.normalize();
  }
}
