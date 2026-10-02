import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { SeededRandom, combineSeed } from '../utils/Random';
import { Noise2D } from '../procedural/Noise';
import { STRUCTURES, WORLD } from '../config';
import type { MaterialLibrary } from '../procedural/Materials';
import type { Terrain } from './Terrain';
import type { Biomes } from './Biomes';
import type { CylinderCollider } from '../core/CameraController';

export interface StructureBuild {
  group: THREE.Group;
  colliders: CylinderCollider[];
}

type StructureKind =
  | 'tombstones'
  | 'spire'
  | 'floating-island'
  | 'colossal-flora'
  | 'fossil'
  | 'monolith-ring';

/** One structure at most per super-cell of this many chunks per side. */
const SUPER_CELL = STRUCTURES.superCellChunks;
const SPAWN_CHANCE = STRUCTURES.spawnChance;

/**
 * Procedural fantasy landmarks: weathered tombstone fields, twisted stone
 * spires, floating islands, colossal flora, fossilized remains, and monolith
 * rings. Placement is sparse (one candidate per super-cell of chunks) and
 * biome-aware so landmarks feel discovered, not scattered.
 */
export class Structures {
  private deformNoise: Noise2D;

  constructor(
    private seed: number,
    private materials: MaterialLibrary,
  ) {
    this.deformNoise = new Noise2D(combineSeed(seed, 911));
  }

  /**
   * Natural deformity: displace vertices along their normal by smooth noise
   * so primitives lose their perfect machine shapes.
   */
  private displace(geo: THREE.BufferGeometry, rng: SeededRandom, amount: number, freq: number): void {
    const pos = geo.getAttribute('position') as THREE.BufferAttribute;
    const ox = rng.range(0, 100);
    const oz = rng.range(0, 100);
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const z = pos.getZ(i);
      const n = this.deformNoise.fbm(ox + (x + y * 0.7) * freq, oz + (z - y * 0.6) * freq, 2);
      const len = Math.hypot(x, z) + 1e-4;
      pos.setX(i, x + (x / len) * n * amount);
      pos.setY(i, y + n * amount * 0.45);
      pos.setZ(i, z + (z / len) * n * amount);
    }
    geo.computeVertexNormals();
  }

  /** Build the structure (if any) for this chunk. Deterministic per seed. */
  maybeBuildForChunk(cx: number, cz: number, terrain: Terrain, biomes: Biomes): StructureBuild | null {
    // One candidate chunk per super-cell keeps landmarks rare and spaced.
    const scx = Math.floor(cx / SUPER_CELL);
    const scz = Math.floor(cz / SUPER_CELL);
    const cellRng = new SeededRandom(combineSeed(this.seed, scx, scz, 9101));
    if (!cellRng.chance(SPAWN_CHANCE)) return null;
    const pickX = scx * SUPER_CELL + cellRng.int(0, SUPER_CELL - 1);
    const pickZ = scz * SUPER_CELL + cellRng.int(0, SUPER_CELL - 1);
    if (pickX !== cx || pickZ !== cz) return null;

    const rng = new SeededRandom(combineSeed(this.seed, cx, cz, 9102));
    const size = WORLD.chunkSize;
    const x = (cx + rng.range(0.3, 0.7)) * size;
    const z = (cz + rng.range(0.3, 0.7)) * size;
    const h = terrain.getMeshHeightAt(x, z);
    const normal = new THREE.Vector3();
    terrain.getNormalAt(x, z, normal);
    if (h < WORLD.waterLevel + 1.2) return null;

    const moisture = biomes.getMoisture(x, z);
    const snow = h > WORLD.snowHeight - 10;
    const steep = normal.y < 0.78;

    let kind: StructureKind;
    const roll = rng.next();
    if (roll < 0.07) {
      kind = 'floating-island';
    } else if (snow || steep) {
      kind = roll < 0.55 ? 'spire' : 'monolith-ring';
    } else if (moisture < 0.34) {
      kind = roll < 0.5 ? 'fossil' : 'tombstones';
    } else {
      kind = roll < 0.38 ? 'tombstones' : roll < 0.68 ? 'colossal-flora' : 'monolith-ring';
    }
    // Flat-ground kinds need reasonably level terrain.
    if (steep && (kind === 'tombstones' || kind === 'fossil' || kind === 'colossal-flora')) {
      return null;
    }

    const group = new THREE.Group();
    const colliders: CylinderCollider[] = [];
    switch (kind) {
      case 'tombstones':
        this.buildTombstones(group, rng, terrain, x, z);
        break;
      case 'spire':
        this.buildSpire(group, colliders, rng, x, h, z);
        break;
      case 'floating-island':
        this.buildFloatingIsland(group, rng, x, h, z);
        break;
      case 'colossal-flora':
        this.buildColossalFlora(group, colliders, rng, x, h, z);
        break;
      case 'fossil':
        this.buildFossil(group, rng, terrain, x, z);
        break;
      case 'monolith-ring':
        this.buildMonolithRing(group, colliders, rng, terrain, x, z);
        break;
    }

    group.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.userData.ownsGeometry = true;
        mesh.castShadow = true;
        mesh.receiveShadow = true;
      }
    });
    return { group, colliders };
  }

  private buildTombstones(group: THREE.Group, rng: SeededRandom, terrain: Terrain, x: number, z: number): void {
    const count = rng.int(5, 10);
    const parts: THREE.BufferGeometry[] = [];
    for (let i = 0; i < count; i++) {
      const a = rng.range(0, Math.PI * 2);
      const r = rng.range(1.5, 9);
      const sx = x + Math.cos(a) * r;
      const sz = z + Math.sin(a) * r;
      const sy = terrain.getMeshHeightAt(sx, sz);
      const w = rng.range(0.5, 0.9);
      const ht = rng.range(0.8, 1.7);
      const slab = new THREE.BoxGeometry(w, ht, w * 0.28, 2, 3, 1);
      // Rounded head: pull the top edge corners in.
      const pos = slab.getAttribute('position') as THREE.BufferAttribute;
      for (let v = 0; v < pos.count; v++) {
        if (pos.getY(v) > ht * 0.49) {
          pos.setX(v, pos.getX(v) * 0.55);
        }
      }
      this.displace(slab, rng, 0.05, 1.4);
      slab.rotateX(rng.range(-0.18, 0.18));
      slab.rotateZ(rng.range(-0.22, 0.22));
      slab.rotateY(rng.range(0, Math.PI * 2));
      slab.translate(sx - x, sy + ht * 0.32, sz - z);
      parts.push(slab);
    }
    const merged = mergeGeometries(parts)!;
    const mesh = new THREE.Mesh(merged, rng.chance(0.5) ? this.materials.mossStone : this.materials.ancientStone);
    mesh.position.set(x, 0, z);
    group.add(mesh);
  }

  private buildSpire(
    group: THREE.Group,
    colliders: CylinderCollider[],
    rng: SeededRandom,
    x: number,
    h: number,
    z: number,
  ): void {
    const height = rng.range(20, 42);
    const baseR = rng.range(2.6, 4.4);
    const points: THREE.Vector2[] = [];
    const steps = 12;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      // Tapering profile with bulges so the silhouette reads hand-carved.
      const bulge = 1 + Math.sin(t * Math.PI * rng.range(2.2, 3.4)) * 0.16 * (1 - t);
      points.push(new THREE.Vector2(baseR * Math.pow(1 - t, 0.72) * bulge + 0.12, t * height));
    }
    const geo = new THREE.LatheGeometry(points, 10);
    // Twist around the vertical axis.
    const twist = rng.range(0.5, 1.4);
    const pos = geo.getAttribute('position') as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) {
      const t = pos.getY(i) / height;
      const ang = t * twist;
      const px = pos.getX(i);
      const pz = pos.getZ(i);
      pos.setX(i, px * Math.cos(ang) - pz * Math.sin(ang));
      pos.setZ(i, px * Math.sin(ang) + pz * Math.cos(ang));
    }
    this.displace(geo, rng, 0.45, 0.22);
    const mesh = new THREE.Mesh(geo, this.materials.rock);
    mesh.position.set(x, h - 1.5, z);
    mesh.rotation.z = rng.range(-0.06, 0.06);
    group.add(mesh);
    colliders.push({ x, z, radius: baseR * 0.9 });

    // A faint crystal lodged near the top catches night light.
    const crystal = new THREE.Mesh(new THREE.OctahedronGeometry(rng.range(0.7, 1.2), 0), this.materials.crystal);
    crystal.position.set(x + rng.range(-0.6, 0.6), h + height * rng.range(0.78, 0.9), z + rng.range(-0.6, 0.6));
    crystal.rotation.set(rng.range(0, 2), rng.range(0, 2), rng.range(0, 2));
    group.add(crystal);
  }

  private buildFloatingIsland(group: THREE.Group, rng: SeededRandom, x: number, h: number, z: number): void {
    const hover = h + rng.range(34, 58);
    const r = rng.range(7, 12);

    // Underside: inverted, heavily deformed cone of rock.
    const bottom = new THREE.ConeGeometry(r, r * rng.range(1.1, 1.6), 9, 4);
    bottom.rotateX(Math.PI);
    this.displace(bottom, rng, r * 0.16, 0.32);
    const bottomMesh = new THREE.Mesh(bottom, this.materials.rock);
    bottomMesh.position.set(x, hover, z);
    group.add(bottomMesh);

    // Top: mossy soil disc with a gentle dome.
    const top = new THREE.CylinderGeometry(r * 0.98, r * 0.9, r * 0.28, 9, 2);
    this.displace(top, rng, r * 0.08, 0.5);
    const topMesh = new THREE.Mesh(top, this.materials.mossStone);
    topMesh.position.set(x, hover + r * 0.12, z);
    group.add(topMesh);

    // Crown: a small stone + crystal so the island glints at night.
    const crown = new THREE.Mesh(new THREE.DodecahedronGeometry(r * 0.22, 0), this.materials.ancientStone);
    this.displace(crown.geometry as THREE.BufferGeometry, rng, r * 0.05, 0.8);
    crown.position.set(x + rng.range(-2, 2), hover + r * 0.36, z + rng.range(-2, 2));
    group.add(crown);
    const crystal = new THREE.Mesh(new THREE.OctahedronGeometry(r * 0.16, 0), this.materials.crystal);
    crystal.position.set(x - rng.range(-2, 2), hover + r * 0.4, z - rng.range(-2, 2));
    group.add(crystal);
  }

  private buildColossalFlora(
    group: THREE.Group,
    colliders: CylinderCollider[],
    rng: SeededRandom,
    x: number,
    h: number,
    z: number,
  ): void {
    const height = rng.range(9, 17);
    const stemR = height * rng.range(0.07, 0.1);

    // Bent stem.
    const stem = new THREE.CylinderGeometry(stemR * 0.62, stemR, height, 9, 6);
    stem.translate(0, height / 2, 0);
    const bendX = rng.range(-0.08, 0.08);
    const bendZ = rng.range(-0.08, 0.08);
    const spos = stem.getAttribute('position') as THREE.BufferAttribute;
    for (let i = 0; i < spos.count; i++) {
      const t = spos.getY(i) / height;
      spos.setX(i, spos.getX(i) + bendX * height * t * t);
      spos.setZ(i, spos.getZ(i) + bendZ * height * t * t);
    }
    this.displace(stem, rng, stemR * 0.2, 0.6);
    const stemMesh = new THREE.Mesh(stem, this.materials.barkBirch);
    stemMesh.position.set(x, h - 0.4, z);
    group.add(stemMesh);

    // Cap: squashed, deformed sphere with luminous underside crystals.
    const capR = height * rng.range(0.34, 0.46);
    const cap = new THREE.SphereGeometry(capR, 12, 8, 0, Math.PI * 2, 0, Math.PI * 0.62);
    cap.scale(1, 0.62, 1);
    this.displace(cap, rng, capR * 0.1, 0.4);
    const capMat = this.materials.crystal;
    const capMesh = new THREE.Mesh(cap, capMat);
    capMesh.position.set(x + bendX * height, h + height * 0.96, z + bendZ * height);
    group.add(capMesh);

    colliders.push({ x, z, radius: stemR });
  }

  private buildFossil(group: THREE.Group, rng: SeededRandom, terrain: Terrain, x: number, z: number): void {
    const ribs = rng.int(5, 9);
    const span = rng.range(7, 14);
    const dir = rng.range(0, Math.PI * 2);
    const dx = Math.cos(dir);
    const dz = Math.sin(dir);
    const parts: THREE.BufferGeometry[] = [];
    for (let i = 0; i < ribs; i++) {
      const t = i / Math.max(ribs - 1, 1);
      const rx = x + dx * (t - 0.5) * span;
      const rz = z + dz * (t - 0.5) * span;
      const ry = terrain.getMeshHeightAt(rx, rz);
      const arcR = (1 - Math.abs(t - 0.5) * 1.2) * rng.range(2.2, 3.2);
      const rib = new THREE.TorusGeometry(arcR, arcR * 0.09, 5, 10, Math.PI * rng.range(0.7, 0.95));
      rib.rotateZ(Math.PI * 0.06 * rng.range(-1, 1));
      rib.rotateY(dir + Math.PI / 2 + rng.range(-0.12, 0.12));
      this.displace(rib, rng, 0.06, 1.1);
      rib.translate(rx - x, ry - 0.4 + arcR * 0.18, rz - z);
      parts.push(rib);
    }
    // Buried skull-ish mass at one end.
    const sx = x + dx * span * 0.62;
    const sz = z + dz * span * 0.62;
    const sy = terrain.getMeshHeightAt(sx, sz);
    const skull = new THREE.SphereGeometry(rng.range(1.0, 1.5), 8, 6);
    skull.scale(1.25, 0.8, 1);
    this.displace(skull, rng, 0.18, 0.9);
    skull.translate(sx - x, sy + 0.25, sz - z);
    parts.push(skull);

    const mesh = new THREE.Mesh(mergeGeometries(parts)!, this.materials.bone);
    mesh.position.set(x, 0, z);
    group.add(mesh);
  }

  private buildMonolithRing(
    group: THREE.Group,
    colliders: CylinderCollider[],
    rng: SeededRandom,
    terrain: Terrain,
    x: number,
    z: number,
  ): void {
    const count = rng.int(5, 9);
    const ringR = rng.range(6, 11);
    const parts: THREE.BufferGeometry[] = [];
    for (let i = 0; i < count; i++) {
      const a = (i / count) * Math.PI * 2 + rng.range(-0.14, 0.14);
      const sx = x + Math.cos(a) * ringR;
      const sz = z + Math.sin(a) * ringR;
      const sy = terrain.getMeshHeightAt(sx, sz);
      const ht = rng.range(3.2, 6.5);
      const w = rng.range(0.9, 1.5);
      const stone = new THREE.BoxGeometry(w, ht, w * 0.7, 2, 4, 2);
      this.displace(stone, rng, 0.16, 0.7);
      stone.rotateX(rng.range(-0.1, 0.1));
      stone.rotateZ(rng.range(-0.12, 0.12));
      stone.rotateY(a + rng.range(-0.3, 0.3));
      stone.translate(sx - x, sy + ht * 0.36, sz - z);
      parts.push(stone);
      colliders.push({ x: sx, z: sz, radius: w * 0.75 });
    }
    const mesh = new THREE.Mesh(mergeGeometries(parts)!, this.materials.ancientStone);
    mesh.position.set(x, 0, z);
    group.add(mesh);
  }
}
