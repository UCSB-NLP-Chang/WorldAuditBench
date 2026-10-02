import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { SeededRandom, combineSeed } from '../utils/Random';
import { WORLD } from '../config';
import type { Terrain, HeightField } from './Terrain';
import type { Biomes } from './Biomes';
import type { SharedEnvUniforms } from './Environment';

const FIREFLY_VERTEX = /* glsl */ `
uniform float uTime;
uniform float uNight;
attribute float aPhase;
varying float vAlpha;

void main() {
  vec3 p = position;
  // Slow wandering drift: small lissajous path per particle.
  p.x += sin(uTime * 0.6 + aPhase * 13.0) * 1.1;
  p.y += sin(uTime * 0.9 + aPhase * 29.0) * 0.55 + 0.4;
  p.z += cos(uTime * 0.5 + aPhase * 17.0) * 1.1;

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = -mv.z;
  gl_PointSize = clamp(30.0 / dist, 1.0, 5.0);

  // Blink: each firefly pulses on its own rhythm; all fade out by day.
  float blink = smoothstep(0.25, 0.9, sin(uTime * 1.7 + aPhase * 80.0) * 0.5 + 0.5);
  vAlpha = blink * uNight * smoothstep(55.0, 18.0, dist);
}
`;

const FIREFLY_FRAGMENT = /* glsl */ `
varying float vAlpha;

void main() {
  vec2 pc = gl_PointCoord - 0.5;
  float d = length(pc);
  float a = smoothstep(0.5, 0.08, d) * vAlpha;
  gl_FragColor = vec4(vec3(0.72, 1.0, 0.45) * a, a);
}
`;

/** Add a per-vertex `aGlow` attribute (0 dark .. 1 fully emissive). */
function withGlow(
  geo: THREE.BufferGeometry,
  fn: (x: number, y: number, z: number) => number,
): THREE.BufferGeometry {
  const p = geo.getAttribute('position') as THREE.BufferAttribute;
  const g = new Float32Array(p.count);
  for (let i = 0; i < p.count; i++) g[i] = fn(p.getX(i), p.getY(i), p.getZ(i));
  geo.setAttribute('aGlow', new THREE.Float32BufferAttribute(g, 1));
  return geo;
}

/** Gentle organic wobble: nudge each vertex along its normal by hash noise. */
function wobble(geo: THREE.BufferGeometry, amp: number): void {
  geo.computeVertexNormals();
  const p = geo.getAttribute('position') as THREE.BufferAttribute;
  const n = geo.getAttribute('normal') as THREE.BufferAttribute;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    const y = p.getY(i);
    const z = p.getZ(i);
    const h = Math.sin(x * 51.3 + y * 17.7 + z * 29.1) * 43758.5453;
    const d = amp * ((h - Math.floor(h)) * 2 - 1);
    p.setXYZ(i, x + n.getX(i) * d, y + n.getY(i) * d, z + n.getZ(i) * d);
  }
  geo.computeVertexNormals();
}

/**
 * A small mushroom: a tapered stem, a smooth squashed cap that droops at the
 * rim, and a gill cone closing the underside so it is never see-through. Glow
 * is concentrated in the gills (`aGlow` 1) plus a scatter of cap speckles; the
 * cap body stays a dark, natural mushroom colour.
 */
function buildMushroom(): THREE.BufferGeometry {
  const R = 0.13;
  const rim = 0.24; // y of the cap rim, sitting atop the stem

  const stem = new THREE.CylinderGeometry(0.03, 0.058, 0.26, 8, 2);
  stem.translate(0, 0.13, 0);
  withGlow(stem, () => 0.05);

  // Cap dome (upper hemisphere), squashed and drooped at the edge.
  const dome = new THREE.SphereGeometry(R, 20, 10, 0, Math.PI * 2, 0, Math.PI * 0.5);
  dome.scale(1, 0.62, 1);
  const dp = dome.getAttribute('position') as THREE.BufferAttribute;
  for (let i = 0; i < dp.count; i++) {
    const y = dp.getY(i);
    const edge = 1 - Math.min(1, y / (R * 0.62));
    dp.setY(i, y - edge * edge * 0.05); // rim droops down
  }
  wobble(dome, 0.012);
  dome.translate(0, rim, 0);
  withGlow(dome, (x, y, z) => {
    const h = Math.sin(x * 89.1 + y * 41.7 + z * 67.3) * 43758.5453;
    return h - Math.floor(h) > 0.84 ? 0.95 : 0.12; // occasional glowing speckle
  });

  // Gill cone closing the underside (apex pointing down toward the stem).
  const gillH = R * 0.8;
  const gills = new THREE.ConeGeometry(R * 0.97, gillH, 20, 1);
  gills.rotateX(Math.PI);
  gills.translate(0, rim - gillH / 2, 0);
  withGlow(gills, () => 1.0);

  return mergeGeometries([stem, dome, gills])!;
}

/**
 * Bioluminescent night life: glowing mushroom clusters and luminous flowers
 * (emissive ramps up after dark) plus drifting firefly particles. Built per
 * detail chunk in moist forest areas; all share two emissive materials and
 * one firefly shader so the cost stays at a couple of draw calls per chunk.
 */
export class Glow {
  private shroomGeometry: THREE.BufferGeometry;
  private flowerGeometry: THREE.BufferGeometry;
  private shroomMaterial: THREE.MeshStandardMaterial;
  private flowerMaterial: THREE.MeshStandardMaterial;
  private fireflyMaterial: THREE.ShaderMaterial;

  constructor(
    private seed: number,
    env: SharedEnvUniforms,
  ) {
    this.shroomGeometry = buildMushroom();

    // Luminous flower: short stem + star of four petals.
    const fStem = new THREE.CylinderGeometry(0.02, 0.03, 0.3, 5, 1);
    fStem.translate(0, 0.15, 0);
    const petals: THREE.BufferGeometry[] = [fStem];
    for (let i = 0; i < 4; i++) {
      const petal = new THREE.PlaneGeometry(0.16, 0.22);
      petal.rotateX(-Math.PI * 0.34);
      petal.rotateY((i / 4) * Math.PI * 2);
      petal.translate(0, 0.32, 0);
      petals.push(petal);
    }
    this.flowerGeometry = mergeGeometries(petals)!;

    // Per-vertex `aGlow` modulates the emissive so only the gills (and a few
    // cap speckles) light up — the cap body stays a dark, natural mushroom.
    this.shroomMaterial = new THREE.MeshStandardMaterial({
      color: 0x243a30,
      emissive: 0x47f0cf,
      emissiveIntensity: 0,
      roughness: 0.72,
      side: THREE.DoubleSide,
    });
    this.shroomMaterial.onBeforeCompile = (shader) => {
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nattribute float aGlow;\nvarying float vMushGlow;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvMushGlow = aGlow;');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying float vMushGlow;')
        .replace(
          '#include <emissivemap_fragment>',
          '#include <emissivemap_fragment>\ntotalEmissiveRadiance *= vMushGlow;',
        );
    };
    this.shroomMaterial.customProgramCacheKey = () => 'shroomGlow';
    this.flowerMaterial = new THREE.MeshStandardMaterial({
      color: 0x2c2440,
      emissive: 0xb46ef0,
      emissiveIntensity: 0,
      roughness: 0.6,
      side: THREE.DoubleSide,
    });

    this.fireflyMaterial = new THREE.ShaderMaterial({
      vertexShader: FIREFLY_VERTEX,
      fragmentShader: FIREFLY_FRAGMENT,
      uniforms: {
        uTime: env.uTime,
        uNight: env.uNight,
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
  }

  /** Ramp plant glow with darkness (called once per frame). */
  update(night: number): void {
    const glow = night * night;
    // gills carry full aGlow, so push intensity a little for a bright underside
    this.shroomMaterial.emissiveIntensity = glow * 3.4;
    this.flowerMaterial.emissiveIntensity = glow * 2.2;
  }

  /**
   * Glow content for a detail chunk, or null where conditions are wrong
   * (dry, open, snowy, or underwater terrain).
   */
  buildForChunk(cx: number, cz: number, terrain: Terrain, biomes: Biomes, field: HeightField): THREE.Group | null {
    const rng = new SeededRandom(combineSeed(this.seed, cx, cz, 7813));
    const size = WORLD.chunkSize;
    const originX = cx * size;
    const originZ = cz * size;

    // Probe the chunk centre: glow life wants moist, forested lowland.
    const probeX = originX + size / 2;
    const probeZ = originZ + size / 2;
    const moisture = biomes.getMoisture(probeX, probeZ);
    const forest = biomes.getForestMask(probeX, probeZ);
    if (moisture < 0.45 || forest < 0.4) return null;
    if (!rng.chance(0.75)) return null;

    const group = new THREE.Group();
    const normal = new THREE.Vector3();

    // --- Mushroom + flower clusters ---
    const clusters = rng.int(2, 5);
    const shroomPlacements: THREE.Matrix4[] = [];
    const flowerPlacements: THREE.Matrix4[] = [];
    const pos = new THREE.Vector3();
    const quat = new THREE.Quaternion();
    const scl = new THREE.Vector3();
    const euler = new THREE.Euler();
    for (let c = 0; c < clusters; c++) {
      const ccx = originX + rng.next() * size;
      const ccz = originZ + rng.next() * size;
      const isShroom = rng.chance(0.6);
      const count = rng.int(4, 10);
      for (let i = 0; i < count; i++) {
        const px = ccx + rng.range(-2.2, 2.2);
        const pz = ccz + rng.range(-2.2, 2.2);
        const h = field.height(px, pz);
        field.normal(px, pz, normal);
        if (h < WORLD.waterLevel + 0.4 || h > WORLD.snowHeight - 14 || normal.y < 0.7) continue;
        pos.set(px, field.meshHeight(px, pz) - 0.02, pz);
        euler.set(0, rng.range(0, Math.PI * 2), rng.range(-0.12, 0.12));
        quat.setFromEuler(euler);
        scl.setScalar(rng.range(0.8, isShroom ? 2.6 : 1.5));
        const m = new THREE.Matrix4().compose(pos, quat, scl);
        (isShroom ? shroomPlacements : flowerPlacements).push(m);
      }
    }
    if (shroomPlacements.length > 0) {
      group.add(this.buildInstanced(this.shroomGeometry, this.shroomMaterial, shroomPlacements));
    }
    if (flowerPlacements.length > 0) {
      group.add(this.buildInstanced(this.flowerGeometry, this.flowerMaterial, flowerPlacements));
    }

    // --- Fireflies: one Points cloud over the chunk's lush spots ---
    const flyCount = rng.int(18, 34);
    const positions = new Float32Array(flyCount * 3);
    const phases = new Float32Array(flyCount);
    let placed = 0;
    for (let i = 0; i < flyCount; i++) {
      const px = originX + rng.next() * size;
      const pz = originZ + rng.next() * size;
      const h = field.height(px, pz);
      if (h < WORLD.waterLevel - 0.5 || h > WORLD.snowHeight - 14) continue;
      positions[placed * 3] = px;
      positions[placed * 3 + 1] = Math.max(h, WORLD.waterLevel) + rng.range(0.5, 2.4);
      positions[placed * 3 + 2] = pz;
      phases[placed] = rng.next();
      placed++;
    }
    if (placed > 2) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(positions.subarray(0, placed * 3), 3));
      geo.setAttribute('aPhase', new THREE.BufferAttribute(phases.subarray(0, placed), 1));
      geo.computeBoundingSphere();
      const points = new THREE.Points(geo, this.fireflyMaterial);
      points.userData.ownsGeometry = true;
      points.renderOrder = 4;
      group.add(points);
    }

    return group.children.length > 0 ? group : null;
  }

  private buildInstanced(
    geometry: THREE.BufferGeometry,
    material: THREE.Material,
    matrices: THREE.Matrix4[],
  ): THREE.InstancedMesh {
    const mesh = new THREE.InstancedMesh(geometry, material, matrices.length);
    for (let i = 0; i < matrices.length; i++) mesh.setMatrixAt(i, matrices[i]);
    mesh.instanceMatrix.needsUpdate = true;
    mesh.castShadow = false;
    mesh.receiveShadow = false;
    return mesh;
  }
}
