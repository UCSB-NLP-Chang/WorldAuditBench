import * as THREE from 'three';
import { FAR_TERRAIN, WORLD } from '../config';
import { smoothstep } from '../utils/MathUtils';
import type { Terrain } from './Terrain';
import type { Biomes } from './Biomes';

const FAR_SIZE = FAR_TERRAIN.size;
const FAR_SEGMENTS = FAR_TERRAIN.segments;
const REBUILD_DISTANCE = FAR_TERRAIN.rebuildDistance;
const ROWS_PER_FRAME = FAR_TERRAIN.rowsPerFrame;

// One quad of the far mesh. Normals are sampled with a stencil this wide so
// they describe the rendered slope (smooth shading) instead of picking up
// sub-grid craggy noise that aliases into faceted shards at this resolution.
const FAR_GRID = FAR_SIZE / FAR_SEGMENTS;

/**
 * Distant landscape: one coarse, vertex-colored mega-mesh sampling the same
 * analytic height field far beyond the streamed chunks — huge mountain
 * ranges on the horizon for one draw call. Rebuilt incrementally (a few rows
 * per frame) as the player roams.
 *
 * To avoid poking through the detailed near chunks, each far vertex takes
 * the MINIMUM of several height taps (never bridges above valleys) and the
 * mesh is progressively sunk toward the player position.
 */
export class FarTerrain {
  private mesh: THREE.Mesh;
  private farWater: THREE.Mesh;
  private center = new THREE.Vector2(1e9, 1e9);

  // Incremental build state.
  private building = false;
  private buildRow = 0;
  private buildCenter = new THREE.Vector2();
  private positions: Float32Array | null = null;
  private colors: Float32Array | null = null;
  private normals: Float32Array | null = null;
  private indices: Uint32Array | null = null;

  private normalV = new THREE.Vector3();
  private color = new THREE.Color();
  private forestColor = new THREE.Color(0.05, 0.09, 0.04);

  constructor(
    scene: THREE.Scene,
    private terrain: Terrain,
    private biomes: Biomes,
  ) {
    this.mesh = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1.0 }),
    );
    this.mesh.castShadow = false;
    this.mesh.receiveShadow = false;
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = -5;
    scene.add(this.mesh);

    // Giant simple water sheet so distant basins read as lakes/sea.
    this.farWater = new THREE.Mesh(
      new THREE.PlaneGeometry(FAR_SIZE, FAR_SIZE).rotateX(-Math.PI / 2),
      new THREE.MeshStandardMaterial({
        color: 0x1d3744,
        roughness: 0.3,
        metalness: 0.1,
      }),
    );
    this.farWater.position.y = WORLD.waterLevel - 0.5;
    this.farWater.renderOrder = -6;
    scene.add(this.farWater);
  }

  update(playerPos: THREE.Vector3): void {
    this.farWater.position.x = playerPos.x;
    this.farWater.position.z = playerPos.z;

    if (this.building) {
      this.buildStep();
      return;
    }

    const dx = playerPos.x - this.center.x;
    const dz = playerPos.z - this.center.y;
    if (dx * dx + dz * dz < REBUILD_DISTANCE * REBUILD_DISTANCE) return;

    // Start an incremental rebuild centred on the player.
    this.building = true;
    this.buildRow = 0;
    this.buildCenter.set(playerPos.x, playerPos.z);
    const verts = FAR_SEGMENTS + 1;
    this.positions = new Float32Array(verts * verts * 3);
    this.colors = new Float32Array(verts * verts * 3);
    this.normals = new Float32Array(verts * verts * 3);
  }

  /** First full build can run synchronously (called once at startup). */
  buildNow(playerPos: THREE.Vector3): void {
    this.building = true;
    this.buildRow = 0;
    this.buildCenter.set(playerPos.x, playerPos.z);
    const verts = FAR_SEGMENTS + 1;
    this.positions = new Float32Array(verts * verts * 3);
    this.colors = new Float32Array(verts * verts * 3);
    this.normals = new Float32Array(verts * verts * 3);
    while (this.building) this.buildStep();
  }

  private sampleRow(iz: number): void {
    const verts = FAR_SEGMENTS + 1;
    const positions = this.positions!;
    const colors = this.colors!;
    const normals = this.normals!;
    const cx = this.buildCenter.x;
    const cz = this.buildCenter.y;

    for (let ix = 0; ix < verts; ix++) {
      const x = cx + (ix / FAR_SEGMENTS - 0.5) * FAR_SIZE;
      const z = cz + (iz / FAR_SEGMENTS - 0.5) * FAR_SIZE;

      // Min of 4 taps: the coarse mesh never bridges above a valley floor.
      const o = 16;
      const h = Math.min(
        this.terrain.getHeightAt(x, z),
        this.terrain.getHeightAt(x + o, z + o),
        this.terrain.getHeightAt(x - o, z + o),
        this.terrain.getHeightAt(x, z - o),
      );

      // Sink: a little everywhere, a lot near the player where detailed
      // chunks live (the near region fully hides the far mesh there).
      const dist = Math.hypot(x - cx, z - cz);
      const sink = 4 + 70 * smoothstep(1100, 250, dist);

      const vi = (iz * verts + ix) * 3;
      positions[vi] = x;
      positions[vi + 1] = h - sink;
      positions[vi + 2] = z;

      // Smooth analytic normal over a full quad. A stencil this wide averages
      // out the sub-grid craggy relief that the mesh can't resolve, so distant
      // ranges shade as continuous slopes instead of faceted triangles. This
      // replaces computeVertexNormals(), which faceted off the min-sampled
      // surface and made the shading jagged.
      const e = FAR_GRID;
      const hL = this.terrain.getHeightAt(x - e, z);
      const hR = this.terrain.getHeightAt(x + e, z);
      const hD = this.terrain.getHeightAt(x, z - e);
      const hU = this.terrain.getHeightAt(x, z + e);
      this.normalV.set(hL - hR, 2 * e, hD - hU).normalize();
      normals[vi] = this.normalV.x;
      normals[vi + 1] = this.normalV.y;
      normals[vi + 2] = this.normalV.z;

      this.biomes.getGroundColor(x, z, h, this.normalV.y, this.color);
      // Distant forests tint the ground dark green where trees would be.
      if (h > WORLD.waterLevel + 1 && h < WORLD.treeLine && this.normalV.y > 0.62) {
        const forest = this.biomes.getForestMask(x, z);
        const f = Math.max(0, (forest - 0.5) * 2) * 0.55;
        this.color.lerp(this.forestColor, f);
      }
      colors[vi] = this.color.r;
      colors[vi + 1] = this.color.g;
      colors[vi + 2] = this.color.b;
    }
  }

  private buildStep(): void {
    const verts = FAR_SEGMENTS + 1;
    const lastRow = Math.min(this.buildRow + ROWS_PER_FRAME, verts);
    for (; this.buildRow < lastRow; this.buildRow++) {
      this.sampleRow(this.buildRow);
    }
    if (this.buildRow < verts) return;

    // All rows sampled: build indices once and swap the geometry in.
    if (!this.indices) {
      this.indices = new Uint32Array(FAR_SEGMENTS * FAR_SEGMENTS * 6);
      let ii = 0;
      for (let iz = 0; iz < FAR_SEGMENTS; iz++) {
        for (let ix = 0; ix < FAR_SEGMENTS; ix++) {
          const a = iz * verts + ix;
          const b = a + 1;
          const c = a + verts;
          const d = c + 1;
          this.indices[ii++] = a;
          this.indices[ii++] = c;
          this.indices[ii++] = b;
          this.indices[ii++] = b;
          this.indices[ii++] = c;
          this.indices[ii++] = d;
        }
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.positions!, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(this.colors!, 3));
    geo.setAttribute('normal', new THREE.BufferAttribute(this.normals!, 3));
    geo.setIndex(new THREE.BufferAttribute(this.indices, 1));
    geo.computeBoundingSphere();

    const old = this.mesh.geometry;
    this.mesh.geometry = geo;
    old.dispose();

    this.center.copy(this.buildCenter);
    this.positions = null;
    this.colors = null;
    this.normals = null;
    this.building = false;
  }

}
