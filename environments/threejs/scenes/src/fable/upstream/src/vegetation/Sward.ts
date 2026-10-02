/**
 * Sward — ground-grass blade geometry.
 *
 * A single blade is a tapered, pre-bent strip with rounded normals so it
 * catches light like a real leaf. Several blades are pre-baked into one tuft so
 * a walking-distance lawn reads as continuous cover without spawning millions
 * of instances. These geometries are shared; the streamer just instances them.
 */
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

/** One four-segment blade, tapered and bent forward, with soft side normals. */
export function bladeStrip(segments = 4): THREE.BufferGeometry {
  const positions: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];
  const baseWidth = 0.023;
  const sideN = 0.616;
  const backN = 0.788;

  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const w = baseWidth * (1 - t * 0.85);
    const bend = t * t * 0.28;
    const y = t * (1 - t * t * 0.06);
    if (i < segments) {
      positions.push(-w, y, bend, w, y, bend);
      normals.push(-sideN, 0.25, -backN, sideN, 0.25, -backN);
      uvs.push(0, t, 1, t);
    } else {
      positions.push(0, y, bend);
      normals.push(0, 0.25, -1);
      uvs.push(0.5, 1);
    }
  }
  for (let i = 0; i < segments; i++) {
    const a = i * 2;
    if (i < segments - 1) indices.push(a, a + 1, a + 3, a, a + 3, a + 2);
    else indices.push(a, a + 1, a + 2);
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geo.setIndex(indices);
  return geo;
}

/** Merge `blades` jittered reference blades into one instanceable tuft. */
export function bladeTuft(blades = 5, segments = 4): THREE.BufferGeometry {
  // self-contained LCG so a tuft is reproducible without touching the world RNG
  let state = 1234567 + blades * 77 + segments * 13;
  const rand = (): number => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
  const parts: THREE.BufferGeometry[] = [];

  for (let b = 0; b < blades; b++) {
    const blade = bladeStrip(segments);
    const yaw = rand() * Math.PI * 2;
    const tall = 0.82 + rand() * 0.78;
    const lean = (rand() - 0.5) * 0.42;
    const ox = (rand() - 0.5) * 0.56;
    const oz = (rand() - 0.5) * 0.56;
    const pos = blade.getAttribute('position') as THREE.BufferAttribute;
    const nrm = blade.getAttribute('normal') as THREE.BufferAttribute;
    const c = Math.cos(yaw);
    const s = Math.sin(yaw);
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i) * 1.45;
      const y = pos.getY(i) * tall;
      const z = pos.getZ(i);
      pos.setXYZ(i, x * c + z * s + ox + lean * y * c, y, z * c - x * s + oz + lean * y * s);
      const nx = nrm.getX(i);
      const nz = nrm.getZ(i);
      nrm.setXYZ(i, nx * c + nz * s, nrm.getY(i), nz * c - nx * s);
    }
    parts.push(blade);
  }

  return mergeGeometries(parts)!;
}
