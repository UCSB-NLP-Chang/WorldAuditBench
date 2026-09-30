import * as THREE from 'three';
import { mergeVertices } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { SeededRandom, combineSeed } from '../utils/Random';
import { Noise2D } from '../procedural/Noise';
import { WORLD, type QualitySettings } from '../config';
import type { MaterialLibrary } from '../procedural/Materials';
import type { Terrain, HeightField } from './Terrain';
import type { Biomes } from './Biomes';
import type { CylinderCollider } from '../core/CameraController';

/**
 * Landscape props: boulders, small stones, fallen logs, shrubs, and flowers.
 * Template geometries are built once; chunks place them with InstancedMesh.
 */
export class Props {
  private boulderGeos: THREE.BufferGeometry[] = [];
  private stoneGeo: THREE.BufferGeometry;
  private logGeo: THREE.BufferGeometry;
  private seed: number;

  constructor(seed: number, private materials: MaterialLibrary, private quality: QualitySettings) {
    this.seed = seed;
    const rng = new SeededRandom(combineSeed(seed, 401));
    const noise = new Noise2D(combineSeed(seed, 402));

    // Boulders: icosahedra displaced by noise -> rugged but smooth-shaded.
    for (let v = 0; v < 3; v++) {
      // Weld vertices so displaced boulders get smooth normals, not facets.
      const geo = mergeVertices(new THREE.IcosahedronGeometry(1, 2), 1e-4);
      const pos = geo.getAttribute('position') as THREE.BufferAttribute;
      const stretch = { x: rng.range(0.8, 1.4), y: rng.range(0.6, 1.0), z: rng.range(0.8, 1.4) };
      for (let i = 0; i < pos.count; i++) {
        const x = pos.getX(i);
        const y = pos.getY(i);
        const z = pos.getZ(i);
        const n = noise.fbm(x * 1.4 + v * 19, (y + z) * 1.4 - v * 7, 3);
        const d = 1 + n * 0.35;
        pos.setXYZ(i, x * d * stretch.x, y * d * stretch.y, z * d * stretch.z);
      }
      geo.computeVertexNormals();
      this.boulderGeos.push(geo);
    }

    // Small stones: rough low-poly pebbles.
    const stone = new THREE.IcosahedronGeometry(1, 0);
    stone.scale(1.2, 0.7, 1);
    this.stoneGeo = stone;

    // Fallen log: lying tapered cylinder.
    const log = new THREE.CylinderGeometry(0.16, 0.23, 2.6, 7, 1);
    log.rotateZ(Math.PI / 2);
    log.translate(0, 0.16, 0);
    this.logGeo = log;

  }

  /**
   * Boulders exist out to a wider radius than the small props (they read
   * from far away); `includeSmallProps` toggles stones/logs/shrubs/flowers.
   */
  buildProps(
    cx: number,
    cz: number,
    terrain: Terrain,
    biomes: Biomes,
    includeSmallProps: boolean,
    field: HeightField,
  ): { group: THREE.Group; colliders: CylinderCollider[] } {
    const rng = new SeededRandom(combineSeed(this.seed, cx, cz, 8003));
    const size = WORLD.chunkSize;
    const originX = cx * size;
    const originZ = cz * size;
    const group = new THREE.Group();
    const colliders: CylinderCollider[] = [];
    const normal = new THREE.Vector3();
    const composeMatrix = new THREE.Matrix4();
    const composePosition = new THREE.Vector3();
    const composeQuaternion = new THREE.Quaternion();
    const composeEuler = new THREE.Euler();
    const composeScale = new THREE.Vector3();
    const scale = this.quality.propDensityScale;

    const place = (
      geo: THREE.BufferGeometry,
      material: THREE.Material,
      items: Array<{ m: THREE.Matrix4; c?: THREE.Color }>,
      shadows: boolean,
    ) => {
      if (items.length === 0) return;
      const mesh = new THREE.InstancedMesh(geo, material, items.length);
      for (let i = 0; i < items.length; i++) {
        mesh.setMatrixAt(i, items[i].m);
        if (items[i].c) mesh.setColorAt(i, items[i].c!);
      }
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.castShadow = shadows;
      mesh.receiveShadow = true;
      group.add(mesh);
    };

    const compose = (x: number, y: number, z: number, rotY: number, s: number, sy = s) => {
      composePosition.set(x, y, z);
      composeEuler.set(0, rotY, 0);
      composeQuaternion.setFromEuler(composeEuler);
      composeScale.set(s, sy, s);
      composeMatrix.compose(composePosition, composeQuaternion, composeScale);
      return composeMatrix.clone();
    };

    // --- Boulders: prefer steep / rocky / shoreline spots ---
    const boulderItems: Array<{ m: THREE.Matrix4 }>[] = this.boulderGeos.map(() => []);
    const boulderAttempts = Math.floor(14 * scale);
    for (let i = 0; i < boulderAttempts; i++) {
      const x = originX + rng.next() * size;
      const z = originZ + rng.next() * size;
      const h = field.meshHeight(x, z);
      field.normal(x, z, normal);
      const steep = 1 - normal.y;
      const nearWater = Math.abs(h - WORLD.waterLevel) < 4 ? 0.35 : 0;
      const p = steep * 1.6 + nearWater + 0.05;
      if (rng.next() >= p) continue;
      const s = rng.range(1.0, 4.6);
      const variant = rng.int(0, this.boulderGeos.length - 1);
      // Partially sink into the terrain.
      boulderItems[variant].push({ m: compose(x, h - s * 0.3, z, rng.range(0, Math.PI * 2), s) });
      if (s > 1.1) colliders.push({ x, z, radius: s * 0.85 });
    }
    boulderItems.forEach((items, v) => place(this.boulderGeos[v], this.materials.rock, items, true));

    if (!includeSmallProps) return { group, colliders };

    // --- Small stones ---
    const stoneItems: Array<{ m: THREE.Matrix4 }> = [];
    const stoneAttempts = Math.floor(34 * scale);
    for (let i = 0; i < stoneAttempts; i++) {
      const x = originX + rng.next() * size;
      const z = originZ + rng.next() * size;
      const h = field.meshHeight(x, z);
      if (h < WORLD.waterLevel + 0.2) continue;
      const s = rng.range(0.07, 0.3);
      stoneItems.push({ m: compose(x, h - s * 0.25, z, rng.range(0, Math.PI * 2), s) });
    }
    place(this.stoneGeo, this.materials.stone, stoneItems, false);

    // --- Fallen logs ---
    const logItems: Array<{ m: THREE.Matrix4 }> = [];
    if (rng.chance(0.6 * scale)) {
      const x = originX + rng.next() * size;
      const z = originZ + rng.next() * size;
      const h = field.meshHeight(x, z);
      field.normal(x, z, normal);
      if (h > WORLD.waterLevel + 0.5 && normal.y > 0.75) {
        const s = rng.range(0.8, 1.5);
        logItems.push({ m: compose(x, h, z, rng.range(0, Math.PI * 2), s, s) });
        colliders.push({ x, z, radius: 0.35 * s });
      }
    }
    place(this.logGeo, this.materials.log, logItems, true);

    return { group, colliders };
  }

}
