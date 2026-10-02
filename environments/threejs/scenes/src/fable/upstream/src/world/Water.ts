import * as THREE from 'three';
import { WATER_VERTEX, WATER_FRAGMENT } from '../shaders/water';
import { WATER, WORLD } from '../config';
import type { Terrain } from './Terrain';
import type { SharedEnvUniforms } from './Environment';

const WATER_SEGMENTS = WATER.segmentsPerChunk;

/**
 * Water system. One shared shader material drives every water chunk; each
 * chunk that dips below the water level gets a grid mesh at the surface with
 * a per-vertex "depth below surface" attribute baked from the terrain field.
 * Sky palette / sun / wind uniforms are shared with the Environment so the
 * water tracks time of day and weather automatically.
 */
export class Water {
  readonly material: THREE.ShaderMaterial;
  private prevPlayer = new THREE.Vector2();
  private playerVel = new THREE.Vector2();

  constructor(env: SharedEnvUniforms) {
    this.material = new THREE.ShaderMaterial({
      vertexShader: WATER_VERTEX,
      fragmentShader: WATER_FRAGMENT,
      uniforms: {
        ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog),
        uTime: env.uTime,
        uSunDir: env.uSunDir,
        uSunColor: env.uSunColor,
        uZenithColor: env.uZenithColor,
        uHorizonColor: env.uHorizonColor,
        uWindDir: env.uWindDir,
        uWindStrength: env.uWindStrength,
        uNight: env.uNight,
        uCloudCover: env.uCloudCover,
        uStarAngle: env.uStarAngle,
        uShallowColor: { value: new THREE.Color(0x39595a) },
        uDeepColor: { value: new THREE.Color(0x102530) },
        uPlayerPos: { value: new THREE.Vector3() },
        uPlayerVel: { value: new THREE.Vector2() },
        uPlayerRipple: { value: 0 },
      },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      fog: true,
    });
  }

  /** Build a water mesh for chunk (cx, cz), or null when the chunk is dry. */
  buildChunkWater(cx: number, cz: number, terrain: Terrain): THREE.Mesh | null {
    const size = WORLD.chunkSize;
    const originX = cx * size;
    const originZ = cz * size;

    // Quick reject: sample a coarse grid for any submerged terrain.
    let hasWater = false;
    const coarse = WATER.coarseRejectSamples;
    for (let iz = 0; iz <= coarse && !hasWater; iz++) {
      for (let ix = 0; ix <= coarse; ix++) {
        const h = terrain.getHeightAt(originX + (ix / coarse) * size, originZ + (iz / coarse) * size);
        if (h < WORLD.waterLevel + 0.3) {
          hasWater = true;
          break;
        }
      }
    }
    if (!hasWater) return null;

    const vertsPerSide = WATER_SEGMENTS + 1;
    const positions = new Float32Array(vertsPerSide * vertsPerSide * 3);
    const depths = new Float32Array(vertsPerSide * vertsPerSide);
    const indices = new Uint16Array(WATER_SEGMENTS * WATER_SEGMENTS * 6);

    let vi = 0;
    let di = 0;
    for (let iz = 0; iz < vertsPerSide; iz++) {
      for (let ix = 0; ix < vertsPerSide; ix++) {
        const lx = (ix / WATER_SEGMENTS) * size;
        const lz = (iz / WATER_SEGMENTS) * size;
        positions[vi] = lx;
        positions[vi + 1] = 0;
        positions[vi + 2] = lz;
        const h = terrain.getHeightAt(originX + lx, originZ + lz);
        depths[di] = Math.max(0, WORLD.waterLevel - h);
        vi += 3;
        di++;
      }
    }

    let ii = 0;
    for (let iz = 0; iz < WATER_SEGMENTS; iz++) {
      for (let ix = 0; ix < WATER_SEGMENTS; ix++) {
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
    geometry.setAttribute('aDepth', new THREE.BufferAttribute(depths, 1));
    geometry.setIndex(new THREE.BufferAttribute(indices, 1));
    geometry.computeBoundingSphere();

    const mesh = new THREE.Mesh(geometry, this.material);
    mesh.position.set(originX, WORLD.waterLevel, originZ);
    mesh.renderOrder = 2;
    return mesh;
  }

  update(dt: number, playerPos: THREE.Vector3, wadeDepth: number, playerMoving: boolean): void {
    const u = this.material.uniforms;
    (u.uPlayerPos.value as THREE.Vector3).copy(playerPos);

    // Horizontal player velocity (drives the directional wake).
    if (dt > 0) {
      this.playerVel.set(
        (playerPos.x - this.prevPlayer.x) / dt,
        (playerPos.z - this.prevPlayer.y) / dt,
      );
      const cap = 4;
      if (this.playerVel.lengthSq() > cap * cap) this.playerVel.setLength(cap);
      (u.uPlayerVel.value as THREE.Vector2).lerp(this.playerVel, 0.2);
    }
    this.prevPlayer.set(playerPos.x, playerPos.z);

    // Ripples fade in while wading, stronger when moving.
    const target = wadeDepth > 0.05 ? (playerMoving ? 1.0 : 0.45) : 0;
    u.uPlayerRipple.value += (target - u.uPlayerRipple.value) * Math.min(1, dt * 5);
  }

}
