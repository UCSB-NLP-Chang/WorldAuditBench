// Fish: instanced barramundi (Khronos CC0 glTF sample) plus procedural silver schooling fish,
// driven by a light boids model (separation / alignment / cohesion / roaming / diver avoidance).
import * as THREE from 'three';
import { seabedHeight } from '../upstream/scene/environment.js';
import { bakedGeometry } from './assets.js';
import { applySwim, applyUnderwater } from './caustics.js';

const TAU = Math.PI * 2;
let seed = 0x5eaf00d;
function rnd() { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; }
function rr(a, b) { return a + rnd() * (b - a); }

function silverFishTexture() {
  const c = document.createElement('canvas');
  c.width = 128; c.height = 64;
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, 0, 64);
  g.addColorStop(0, '#2c4e6b'); g.addColorStop(0.35, '#7fa4bd'); g.addColorStop(0.55, '#d9e6ee'); g.addColorStop(1, '#e8eef2');
  ctx.fillStyle = g; ctx.fillRect(0, 0, 128, 64);
  ctx.fillStyle = 'rgba(40,70,90,0.55)'; ctx.fillRect(0, 26, 128, 3);
  ctx.fillStyle = 'rgba(255,255,255,0.35)';
  for (let x = 0; x < 128; x += 6) for (let y = 4; y < 60; y += 6) { ctx.beginPath(); ctx.arc(x + (y % 12 ? 3 : 0), y, 2.2, 0, TAU); ctx.fill(); }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
// unit-length fish (head at +z), body lathe + tail + dorsal fin
function silverFishGeometry() {
  const pts = [];
  for (let i = 0; i <= 12; i++) {
    const t = i / 12;
    const r = Math.sin(t * Math.PI) * 0.11 * (1 - t * 0.35) + 0.004;
    pts.push(new THREE.Vector2(r, t - 0.5));
  }
  const body = new THREE.LatheGeometry(pts, 14);
  body.rotateX(-Math.PI / 2);           // lathe axis (y) -> z, tail at -z
  body.scale(0.55, 1, 1);
  const tail = new THREE.BufferGeometry();
  tail.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, -0.48, 0, 0.14, -0.66, 0, 0, -0.58, 0, -0.14, -0.66], 3));
  tail.setAttribute('uv', new THREE.Float32BufferAttribute([0.9, 0.5, 1, 0.9, 1, 0.5, 1, 0.1], 2));
  tail.setIndex([0, 1, 2, 0, 2, 3]);
  tail.computeVertexNormals();
  const fin = new THREE.BufferGeometry();
  fin.setAttribute('position', new THREE.Float32BufferAttribute([0, 0.08, 0.15, 0, 0.2, -0.05, 0, 0.09, -0.2], 3));
  fin.setAttribute('uv', new THREE.Float32BufferAttribute([0.4, 0.2, 0.5, 0.05, 0.6, 0.2], 2));
  fin.setIndex([0, 1, 2]);
  fin.computeVertexNormals();
  const merged = [body, tail, fin];
  // manual merge (BufferGeometryUtils would also work; keep this module self-contained)
  let count = 0;
  const pos = [], uv = [], nor = [], idx = [];
  for (const g of merged) {
    const p = g.attributes.position, u = g.attributes.uv, n = g.attributes.normal, ix = g.index;
    for (let i = 0; i < p.count; i++) { pos.push(p.getX(i), p.getY(i), p.getZ(i)); uv.push(u.getX(i), u.getY(i)); nor.push(n.getX(i), n.getY(i), n.getZ(i)); }
    for (let i = 0; i < ix.count; i++) idx.push(ix.getX(i) + count);
    count += p.count;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  geo.setIndex(idx);
  return geo;
}

class School {
  constructor({ mesh, count, center, radius, speed, scale, roam, avoid = 3.0, bodyLength = 1 }) {
    this.mesh = mesh; this.count = count; this.center = center.clone(); this.home = center.clone();
    this.radius = radius; this.speed = speed; this.roam = roam; this.avoid = avoid; this.bodyLength = bodyLength;
    this.fish = [];
    for (let i = 0; i < count; i++) {
      const a = rnd() * TAU, d = Math.sqrt(rnd()) * radius;
      const p = center.clone().add(new THREE.Vector3(Math.cos(a) * d, rr(-0.6, 0.6), Math.sin(a) * d));
      const h = rnd() * TAU;
      this.fish.push({
        p, v: new THREE.Vector3(Math.cos(h), 0, Math.sin(h)).multiplyScalar(speed * rr(0.7, 1.1)),
        acc: new THREE.Vector3(), s: rr(scale[0], scale[1]), phase: rnd() * TAU,
      });
    }
    this.tmp = new THREE.Vector3(); this.tmp2 = new THREE.Vector3(); this.tmp3 = new THREE.Vector3(); this.dummy = new THREE.Object3D();
    this.phaseAttr = new THREE.InstancedBufferAttribute(new Float32Array(count), 1);
    this.speedAttr = new THREE.InstancedBufferAttribute(new Float32Array(count), 1);
    for (let i = 0; i < count; i++) { this.phaseAttr.setX(i, this.fish[i].phase); this.speedAttr.setX(i, rr(0.85, 1.25)); }
    mesh.geometry.setAttribute('aPhase', this.phaseAttr);
    mesh.geometry.setAttribute('aSpeed', this.speedAttr);
  }
  step(dt, time, camera) {
    const { fish, tmp, tmp2 } = this;
    // roaming centre drifts on a slow loop
    this.center.set(
      this.home.x + Math.sin(time * 0.11 + this.roam) * 5.5,
      this.home.y + Math.sin(time * 0.07 + this.roam * 2) * 0.8,
      this.home.z + Math.cos(time * 0.09 + this.roam) * 5.5,
    );
    const n = fish.length;
    for (let i = 0; i < n; i++) {
      const f = fish[i];
      f.acc.set(0, 0, 0);
      let sepN = 0, aliN = 0, cohN = 0;
      const sep = tmp.set(0, 0, 0), ali = tmp2.set(0, 0, 0);
      const coh = this.tmp3.set(0, 0, 0);
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const o = fish[j];
        const dx = f.p.x - o.p.x, dy = f.p.y - o.p.y, dz = f.p.z - o.p.z;
        const d2 = dx * dx + dy * dy + dz * dz;
        const sepR = 0.55 * this.bodyLength;
        if (d2 < sepR * sepR && d2 > 1e-6) { const inv = 1 / Math.sqrt(d2); sep.x += dx * inv; sep.y += dy * inv; sep.z += dz * inv; sepN++; }
        if (d2 < 9) { ali.add(o.v); aliN++; coh.add(o.p); cohN++; }
      }
      if (sepN) f.acc.addScaledVector(sep, 2.4 / sepN);
      if (aliN) f.acc.addScaledVector(ali.multiplyScalar(1 / aliN).sub(f.v), 0.9);
      if (cohN) f.acc.addScaledVector(coh.multiplyScalar(1 / cohN).sub(f.p), 0.35);
      // stay near the roaming centre
      const toC = coh.copy(this.center).sub(f.p);
      const dist = toC.length();
      if (dist > this.radius) f.acc.addScaledVector(toC.normalize(), 0.8 * (dist - this.radius));
      // wander
      f.acc.x += Math.sin(time * 1.3 + f.phase * 3) * 0.35;
      f.acc.z += Math.cos(time * 1.1 + f.phase * 2) * 0.35;
      f.acc.y += Math.sin(time * 0.7 + f.phase) * 0.12;
      // diver avoidance
      const cx = f.p.x - camera.position.x, cy = f.p.y - camera.position.y, cz = f.p.z - camera.position.z;
      const cd = Math.hypot(cx, cy, cz);
      if (cd < this.avoid && cd > 1e-3) { const k = (this.avoid - cd) / this.avoid * 6; f.acc.x += cx / cd * k; f.acc.y += cy / cd * k * 0.4; f.acc.z += cz / cd * k; }
      // vertical bounds: seabed + 0.9 .. surface - 1.0 (a bug may pin the school to a band relative to the seabed)
      const sb = seabedHeight(f.p.x, f.p.z);
      const floor = sb + (this.yBand ? this.yBand[0] : 0.9);
      const ceil = this.yBand ? sb + this.yBand[1] : -1.0;
      if (f.p.y < floor) f.acc.y += (floor - f.p.y) * 4;
      if (f.p.y > ceil) f.acc.y -= (f.p.y - ceil) * 4;
      f.v.addScaledVector(f.acc, dt);
      const sp = f.v.length();
      const max = this.speed * 1.6, min = this.speed * 0.45;
      if (sp > max) f.v.multiplyScalar(max / sp);
      else if (sp < min) f.v.multiplyScalar(min / Math.max(sp, 1e-4));
      f.p.addScaledVector(f.v, dt);
    }
    // write instance matrices (head = +z)
    const d = this.dummy;
    for (let i = 0; i < n; i++) {
      const f = fish[i];
      d.position.copy(f.p);
      tmp.copy(f.p);
      if (this.reverse) tmp.sub(f.v); else tmp.add(f.v);   // bug wt16: tail-first
      d.up.set(0, this.upsideDown ? -1 : 1, 0);              // bug wt17: rolled 180 degrees
      d.lookAt(tmp);
      d.scale.setScalar(f.s);
      d.updateMatrix();
      this.mesh.setMatrixAt(i, d.matrix);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
  }
}

// headFlip: the BarramundiFish glTF already has its head at +z (widest cross-section at +z, thin tail at -z);
// the instance matrices look along +z, so no flip (a flip made the schools swim tail-first).
export function createFish(scene, { headFlip = false, debug = false } = {}) {
  const schools = [];
  const underwaterObjects = [];

  // barramundi (0.64 m model)
  const { geometry: barraGeo, material: barraSrc } = bakedGeometry('BarramundiFish');
  if (headFlip) barraGeo.rotateY(Math.PI);
  barraGeo.computeBoundingBox();
  const bb = barraGeo.boundingBox;
  barraGeo.translate(0, -(bb.min.y + bb.max.y) / 2, -(bb.min.z + bb.max.z) / 2);
  const barraMat = barraSrc.clone();
  barraMat.side = THREE.DoubleSide;
  applySwim(barraMat, { amplitude: 0.05, frequency: 5.5, length: 0.64 });
  applyUnderwater(barraMat, { strength: 0.35, scale: 0.6, tint: false });
  const barraGroups = [
    { count: 9, center: new THREE.Vector3(6, -3.2, -4), radius: 3.2, speed: 0.75, scale: [0.85, 1.25], roam: 0.3 },
    { count: 6, center: new THREE.Vector3(-8, -3.6, 6), radius: 2.8, speed: 0.7, scale: [1.0, 1.5], roam: 2.1 },
    { count: 3, center: new THREE.Vector3(0, -2.6, 0), radius: 5.0, speed: 0.55, scale: [1.5, 1.9], roam: 4.0, avoid: 2.2 },
  ];
  for (const g of barraGroups) {
    const mesh = new THREE.InstancedMesh(barraGeo.clone(), barraMat, g.count);
    mesh.castShadow = true; mesh.receiveShadow = false; mesh.frustumCulled = false;
    mesh.name = 'FISH_BARRAMUNDI';
    scene.add(mesh); underwaterObjects.push(mesh);
    schools.push(new School({ mesh, bodyLength: 0.64, ...g }));
  }

  // silver schooling fish (procedural, ~0.2 m)
  const silverGeo = silverFishGeometry();
  const silverMat = new THREE.MeshStandardMaterial({ map: silverFishTexture(), roughness: 0.35, metalness: 0.45, side: THREE.DoubleSide });
  applySwim(silverMat, { amplitude: 0.06, frequency: 9, length: 1.0 });
  const silverGroups = [
    { count: 70, center: new THREE.Vector3(10, -2.5, -8), radius: 2.2, speed: 1.1, scale: [0.16, 0.24], roam: 1.0, avoid: 3.5 },
    { count: 55, center: new THREE.Vector3(-3, -2.8, -11), radius: 2.0, speed: 1.0, scale: [0.15, 0.22], roam: 2.6, avoid: 3.5 },
    { count: 60, center: new THREE.Vector3(-13, -3.5, 9), radius: 2.4, speed: 1.0, scale: [0.18, 0.26], roam: 5.2, avoid: 3.5 },
  ];
  for (const g of silverGroups) {
    const mesh = new THREE.InstancedMesh(silverGeo.clone(), silverMat, g.count);
    mesh.castShadow = false; mesh.frustumCulled = false;
    mesh.name = 'FISH_SCHOOL';
    scene.add(mesh); underwaterObjects.push(mesh);
    schools.push(new School({ mesh, bodyLength: 0.2, ...g }));
  }

  if (debug) {
    // a static barramundi at (0,-3.2,9) facing +z, for orientation checks
    const m = new THREE.Mesh(barraGeo.clone(), barraSrc.clone());
    m.position.set(0, -3.2, 9); m.scale.setScalar(1.5);
    scene.add(m); underwaterObjects.push(m);
  }
  let last = null;
  return {
    underwaterObjects,
    schools,
    update(time, underwaterMix, camera) {
      const dt = last === null ? 1 / 60 : THREE.MathUtils.clamp(time - last, 0, 0.05);
      last = time;
      for (const s of schools) s.step(dt, time, camera);
    },
    getDiagnostics(camera) {
      return schools.map((s) => ({ count: s.count, nearest: Math.min(...s.fish.map((f) => f.p.distanceTo(camera.position))) }));
    },
  };
}
