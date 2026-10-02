// Reef dressing: Poly Haven rocks, procedural corals, sponges, sea fans, anemones, seagrass and kelp.
import * as THREE from 'three';
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';
import { seabedHeight, seabedNormal } from '../upstream/scene/environment.js';
import { models } from './assets.js';
import { applyUnderwater, applySway } from './caustics.js';

const TAU = Math.PI * 2;
let seed = 0x2f6e2b1;
function rnd() { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; }
function rr(a, b) { return a + rnd() * (b - a); }
const up = new THREE.Vector3(0, 1, 0);
const tmpN = new THREE.Vector3();
const tmpQ = new THREE.Quaternion();

function alignToGround(obj, x, z, tilt = 1) {
  const n = seabedNormal(x, z);
  tmpN.set(n.x, n.y, n.z);
  tmpQ.setFromUnitVectors(up, tmpN);
  obj.quaternion.copy(tmpQ);
  if (tilt !== 1) obj.quaternion.slerp(new THREE.Quaternion(), 1 - tilt);
  obj.rotateY(rnd() * TAU);
}

function vertexColorGeometry(geo, colorFn) {
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    colorFn(c, pos.getX(i), pos.getY(i), pos.getZ(i), i);
    colors[i * 3] = c.r; colors[i * 3 + 1] = c.g; colors[i * 3 + 2] = c.b;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  return geo;
}

function noise3(x, y, z) {
  return Math.sin(x * 3.1 + Math.sin(y * 2.7)) * 0.5 + Math.sin(y * 4.3 + Math.sin(z * 3.3)) * 0.3 + Math.sin(z * 5.1 + x * 1.7) * 0.2;
}

// ---- coral generators (each returns a Group placed with its base at y=0)
function staghorn(color) {
  const parts = [];
  const dir = new THREE.Vector3();
  const m = new THREE.Matrix4();
  function branch(origin, direction, len, radius, depth) {
    const end = origin.clone().addScaledVector(direction, len);
    const g = new THREE.CylinderGeometry(radius * 0.72, radius, len, 6, 1);
    g.translate(0, len / 2, 0);
    m.makeRotationFromQuaternion(tmpQ.setFromUnitVectors(up, direction));
    m.setPosition(origin);
    g.applyMatrix4(m);
    parts.push(g);
    if (depth === 0) return;
    const n = 2 + (rnd() < 0.45 ? 1 : 0);
    for (let i = 0; i < n; i++) {
      dir.copy(direction);
      dir.x += rr(-0.75, 0.75); dir.z += rr(-0.75, 0.75); dir.y += rr(0.1, 0.6);
      dir.normalize();
      branch(end, dir, len * rr(0.62, 0.8), radius * 0.72, depth - 1);
    }
  }
  branch(new THREE.Vector3(0, 0, 0), new THREE.Vector3(rr(-0.2, 0.2), 1, rr(-0.2, 0.2)).normalize(), rr(0.28, 0.42), rr(0.045, 0.07), 4);
  const geo = BufferGeometryUtils.mergeGeometries(parts, false);
  const base = new THREE.Color(color);
  vertexColorGeometry(geo, (c, x, y) => { c.copy(base).offsetHSL(0, 0, -0.18 + Math.min(0.3, y * 0.25) + rnd() * 0.04); });
  return geo;
}
function tableCoral() {
  const stem = new THREE.CylinderGeometry(0.16, 0.24, 0.35, 10);
  stem.translate(0, 0.17, 0);
  const r = rr(0.55, 1.1);
  const top = new THREE.CylinderGeometry(r, r * 0.8, 0.09, 26, 3);
  const p = top.attributes.position;
  const lobes = 4 + Math.floor(rnd() * 3), lobePhase = rnd() * TAU, squash = rr(0.7, 1.0);
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), z = p.getZ(i), y = p.getY(i);
    const a = Math.atan2(z, x), rad = Math.hypot(x, z) / r;
    const edge = 1 + 0.16 * Math.sin(a * lobes + lobePhase) * rad;   // lobed outline
    p.setX(i, x * edge); p.setZ(i, z * edge * squash);
    if (y > 0) p.setY(i, y + 0.06 * Math.abs(noise3(x * 4, 0, z * 4)) + (rad > 0.9 ? -0.03 : 0));
  }
  top.computeVertexNormals();
  top.translate(0, 0.38, 0);
  const geo = BufferGeometryUtils.mergeGeometries([stem, top], false);
  const base = new THREE.Color(0xa8874f);
  vertexColorGeometry(geo, (c, x, y, z) => { c.copy(base).offsetHSL(rnd() * 0.02, 0, (y > 0.36 ? 0.05 : -0.2) + noise3(x, y, z) * 0.05); });
  return geo;
}
function brainCoral(color) {
  const r = rr(0.35, 0.8);
  const geo = new THREE.SphereGeometry(r, 36, 24);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const len = Math.hypot(x, y, z) || 1;
    const nx = x / len, ny = y / len, nz = z / len;
    const groove = 0.5 + 0.5 * Math.sin(nx * 26 + Math.sin(nz * 20 + ny * 9) * 3.5 + Math.sin(ny * 17) * 2);
    const d = r * (1 + groove * 0.06 + noise3(nx * 2, ny * 2, nz * 2) * 0.03);
    p.setXYZ(i, nx * d, Math.max(ny * d * 0.72, -r * 0.2), nz * d);
  }
  geo.computeVertexNormals();
  const base = new THREE.Color(color);
  vertexColorGeometry(geo, (c, x, y, z) => { const groove = 0.5 + 0.5 * Math.sin(x / r * 26 + Math.sin(z / r * 20 + y / r * 9) * 3.5); c.copy(base).offsetHSL(0, 0, groove * 0.18 - 0.12); });
  return geo;
}
function tubeSponge(color) {
  const parts = [];
  const n = 3 + Math.floor(rnd() * 4);
  for (let i = 0; i < n; i++) {
    const h = rr(0.3, 0.9), rt = rr(0.05, 0.09);
    const g = new THREE.CylinderGeometry(rt, rt * 0.7, h, 10, 1, true);
    g.translate(0, h / 2, 0);
    const a = rnd() * TAU, d = rr(0.02, 0.16);
    g.rotateX(rr(-0.25, 0.25)); g.rotateZ(rr(-0.25, 0.25));
    g.translate(Math.cos(a) * d, 0, Math.sin(a) * d);
    parts.push(g);
  }
  const geo = BufferGeometryUtils.mergeGeometries(parts, false);
  const base = new THREE.Color(color);
  vertexColorGeometry(geo, (c, x, y) => { c.copy(base).offsetHSL(0, 0, -0.1 + y * 0.12); });
  return geo;
}
function anemone(color, tipColor) {
  const parts = [];
  const base = new THREE.SphereGeometry(0.14, 12, 8, 0, TAU, 0, Math.PI / 2);
  base.scale(1.2, 0.7, 1.2);
  parts.push(base);
  const n = 26;
  for (let i = 0; i < n; i++) {
    const g = new THREE.CylinderGeometry(0.012, 0.022, 0.22, 5, 1);
    g.translate(0, 0.11, 0);
    const a = (i / n) * TAU + rnd() * 0.3;
    const ring = i % 2 === 0 ? 0.09 : 0.05;
    g.rotateX(rr(0.5, 1.0) * (i % 2 === 0 ? 1 : 0.6));
    g.rotateY(a);
    g.translate(Math.cos(a) * ring, 0.07, Math.sin(a) * ring);
    parts.push(g);
  }
  const geo = BufferGeometryUtils.mergeGeometries(parts, false);
  const b = new THREE.Color(color), t = new THREE.Color(tipColor);
  vertexColorGeometry(geo, (c, x, y) => { c.copy(b).lerp(t, THREE.MathUtils.clamp((y - 0.08) / 0.25, 0, 1)); });
  return geo;
}
function seaFanTexture() {
  const c = document.createElement('canvas');
  c.width = 256; c.height = 256;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, 256, 256);
  ctx.strokeStyle = '#ffffff';
  ctx.lineCap = 'round';
  function grow(x, y, angle, len, w, depth) {
    const nx = x + Math.cos(angle) * len, ny = y - Math.sin(angle) * len;
    ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(nx, ny); ctx.stroke();
    if (depth === 0) return;
    const n = 2 + (rnd() < 0.5 ? 1 : 0);
    for (let i = 0; i < n; i++) grow(nx, ny, angle + rr(-0.75, 0.75), len * rr(0.6, 0.8), Math.max(0.8, w * 0.7), depth - 1);
  }
  grow(128, 250, Math.PI / 2, 40, 6, 6);
  const t = new THREE.CanvasTexture(c);
  return t;
}

// ---- vegetation geometry
function bladeGeometry(width, height, segments) {
  const g = new THREE.PlaneGeometry(width, height, 1, segments);
  g.translate(0, height / 2, 0);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const t = p.getY(i) / height;
    p.setX(i, p.getX(i) * (1 - t * 0.85));   // taper to the tip
  }
  return g;
}

export async function createReef(scene) {
  const group = new THREE.Group();
  group.name = 'REEF';
  scene.add(group);
  const underwaterObjects = [group];

  // ---- rocks (Poly Haven CC0), tinted for the underwater look
  const rockTint = new THREE.Color(0x9fb0aa);
  const patchedMaterials = new Set();
  function placeRock(id, x, z, rot, scale = 1, sink = 0.35, tilt = 0.6) {
    const proto = models[id];
    if (!proto) return null;
    const obj = proto.clone();
    obj.traverse((o) => {
      if (o.isMesh) {
        if (!patchedMaterials.has(o.material)) {
          o.material.color.multiply(rockTint);
          o.material.roughness = Math.min(1, (o.material.roughness ?? 1) + 0.05);
          applyUnderwater(o.material, { strength: 0.8, scale: 0.6 });
          patchedMaterials.add(o.material);
        }
        o.castShadow = o.receiveShadow = true;
      }
    });
    const bb = proto.userData.bbox;
    obj.position.set(x, seabedHeight(x, z) - bb.min.y * scale - sink, z);
    alignToGround(obj, x, z, tilt);
    obj.rotateY(rot);
    obj.scale.setScalar(scale);
    obj.name = 'ROCK';
    group.add(obj);
    return obj;
  }
  // main ridge (north-east arc, r ≈ 12.5) and the south-west rise (r ≈ 17)
  placeRock('rock_face_01', 9.5, -8.5, 0.6, 1.0, 0.8, 0.3);
  placeRock('rock_face_02', 13.5, -2.5, -1.9, 1.05, 0.7, 0.3);
  placeRock('rock_face_02', 3.5, -12.5, 2.4, 0.85, 0.7, 0.3);
  placeRock('namaqualand_boulder_03', 12.2, 4.5, 0.4, 1.1, 0.35);
  placeRock('namaqualand_boulder_04', 6.8, -11.9, 2.1, 1.0, 0.4);
  placeRock('namaqualand_boulder_04', -2.5, -13.4, 1.1, 0.8, 0.4);
  placeRock('namaqualand_boulder_06', 10.6, 0.6, 0.2, 1.3, 0.2);
  placeRock('namaqualand_boulder_06', 5.0, 12.5, 1.6, 1.1, 0.2);
  placeRock('boulder_01', -12.5, 11.5, 0.9, 1.4, 0.35);
  placeRock('boulder_01', -15.5, 5.5, 2.2, 1.1, 0.35);
  placeRock('namaqualand_boulder_03', -14.0, -9.0, 2.9, 0.9, 0.35);
  placeRock('rock_moss_set_01', -6.0, 8.5, 0.3, 1.0, 0.12, 0.9);
  placeRock('rock_moss_set_01', 15.0, -9.5, 1.7, 1.0, 0.12, 0.9);
  placeRock('rock_moss_set_01', -9.5, -3.0, 2.6, 0.9, 0.12, 0.9);
  placeRock('boulder_01', 18.5, 3.5, 0.4, 0.9, 0.3);
  placeRock('namaqualand_boulder_06', -4.5, -6.5, 2.8, 1.0, 0.2);

  // ---- corals
  const coralMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0 });
  applyUnderwater(coralMat, { strength: 0.9, scale: 0.6 });
  const spongeMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, side: THREE.DoubleSide });
  applyUnderwater(spongeMat, { strength: 0.7, scale: 0.6 });
  const anemoneMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7 });
  applyUnderwater(anemoneMat, { strength: 0.7, scale: 0.6 });
  applySway(anemoneMat, { amplitude: 0.06, frequency: 1.6, height: 0.32 });
  const fanTex = seaFanTexture();
  const fanMat = new THREE.MeshStandardMaterial({ color: 0xb8304a, alphaMap: fanTex, transparent: true, alphaTest: 0.35, side: THREE.DoubleSide, roughness: 0.9 });
  applyUnderwater(fanMat, { strength: 0.5, scale: 0.6, tint: true });
  applySway(fanMat, { amplitude: 0.12, frequency: 0.9, height: 1.1 });
  const fanMat2 = fanMat.clone(); fanMat2.color.set(0x7a3fa0); applyUnderwater(fanMat2, { strength: 0.5, scale: 0.6 }); applySway(fanMat2, { amplitude: 0.12, frequency: 0.8, height: 1.1 });

  const coralPalette = [0xf27a6a, 0xf5a96b, 0xd8628f, 0xf2d06b, 0x8fd1c4, 0xe07a8a];
  function coral(kind, x, z, rot = rnd() * TAU, scale = 1) {
    let geo, mat = coralMat;
    if (kind === 'staghorn') geo = staghorn(coralPalette[Math.floor(rnd() * coralPalette.length)]);
    else if (kind === 'table') geo = tableCoral();
    else if (kind === 'brain') geo = brainCoral(rnd() < 0.5 ? 0xb9b25a : 0x8fa04c);
    else if (kind === 'sponge') { geo = tubeSponge(rnd() < 0.5 ? 0x7b4fb0 : 0xe6c34a); mat = spongeMat; }
    else if (kind === 'anemone') { geo = anemone(rnd() < 0.5 ? 0x67b36d : 0xd66e9a, rnd() < 0.5 ? 0xf0f2a6 : 0xffb3d9); mat = anemoneMat; }
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, seabedHeight(x, z) - 0.02, z);
    alignToGround(mesh, x, z, 0.8);
    mesh.rotateY(rot);
    mesh.scale.setScalar(scale);
    mesh.castShadow = mesh.receiveShadow = true;
    mesh.name = 'CORAL_' + kind.toUpperCase();
    group.add(mesh);
    return mesh;
  }
  function seaFan(x, z, scale = 1) {
    const g = new THREE.PlaneGeometry(0.9, 1.1, 1, 6);
    g.translate(0, 0.55, 0);
    const mesh = new THREE.Mesh(g, rnd() < 0.5 ? fanMat : fanMat2);
    mesh.position.set(x, seabedHeight(x, z), z);
    mesh.rotation.y = rnd() * TAU;
    mesh.scale.setScalar(scale);
    mesh.castShadow = false; mesh.receiveShadow = true;
    mesh.name = 'SEA_FAN';
    group.add(mesh);
  }
  // clusters around the ridge and the rocks
  const clusters = [[9.0, -5.0, 3.2], [12.0, 1.0, 2.6], [5.5, -10.0, 3.0], [0.5, -12.0, 2.5], [14.5, -6.5, 2.4], [-4.0, -10.5, 2.4], [-13.0, 8.5, 2.6], [-15.0, -6.0, 2.2], [7.0, 9.5, 2.0], [-7.5, 6.0, 1.8]];
  for (const [cx, cz, cr] of clusters) {
    const n = 5 + Math.floor(rnd() * 4);
    for (let i = 0; i < n; i++) {
      const a = rnd() * TAU, d = Math.sqrt(rnd()) * cr;
      const x = cx + Math.cos(a) * d, z = cz + Math.sin(a) * d;
      const k = rnd();
      const kind = k < 0.32 ? 'staghorn' : k < 0.5 ? 'brain' : k < 0.66 ? 'table' : k < 0.85 ? 'sponge' : 'anemone';
      coral(kind, x, z, rnd() * TAU, rr(0.8, 1.4));
    }
    if (rnd() < 0.8) seaFan(cx + rr(-1.5, 1.5), cz + rr(-1.5, 1.5), rr(0.8, 1.5));
  }
  // a few lone anemones / brains in the sand
  for (let i = 0; i < 10; i++) { const a = rnd() * TAU, d = rr(5, 22); coral(rnd() < 0.5 ? 'anemone' : 'brain', Math.cos(a) * d, Math.sin(a) * d, rnd() * TAU, rr(0.7, 1.1)); }

  // ---- seagrass (instanced blades in patches) and kelp stands
  const grassMat = new THREE.MeshStandardMaterial({ color: 0x2f7d46, roughness: 0.85, side: THREE.DoubleSide });
  applyUnderwater(grassMat, { strength: 0.5, scale: 0.6 });
  applySway(grassMat, { amplitude: 0.12, frequency: 1.2, height: 0.55 });
  const blade = bladeGeometry(0.1, 0.55, 5);
  const patches = [[-7, -6, 3.5], [8, 5, 3.0], [-11, 3, 3.2], [3, 15, 3.4], [-3, 10, 2.6], [18, -12, 3.0], [-19, -11, 3.2], [16, 12, 2.8], [-1, -4, 2.2], [20, 0, 2.5]];
  let total = 0;
  const counts = patches.map(() => 180 + Math.floor(rnd() * 80));
  counts.forEach((c) => { total += c; });
  const grass = new THREE.InstancedMesh(blade, grassMat, total);
  const dummy = new THREE.Object3D();
  let gi = 0;
  patches.forEach(([px, pz, pr], pi) => {
    for (let i = 0; i < counts[pi]; i++) {
      const a = rnd() * TAU, d = Math.pow(rnd(), 0.7) * pr;
      const x = px + Math.cos(a) * d, z = pz + Math.sin(a) * d;
      dummy.position.set(x, seabedHeight(x, z) - 0.03, z);
      dummy.rotation.set(rr(-0.15, 0.15), rnd() * TAU, rr(-0.15, 0.15));
      dummy.scale.set(rr(0.8, 1.3), rr(0.7, 1.5), 1);
      dummy.updateMatrix();
      grass.setMatrixAt(gi++, dummy.matrix);
    }
  });
  grass.instanceMatrix.needsUpdate = true;
  grass.castShadow = false; grass.receiveShadow = true;
  grass.name = 'SEAGRASS';
  group.add(grass);

  const kelpMat = new THREE.MeshStandardMaterial({ color: 0x3a5a22, roughness: 0.85, side: THREE.DoubleSide });
  applyUnderwater(kelpMat, { strength: 0.5, scale: 0.6 });
  applySway(kelpMat, { amplitude: 0.45, frequency: 0.55, height: 4.2 });
  const kelpBlade = bladeGeometry(0.22, 4.2, 14);
  const stands = [[11.5, -6.5, 1.6], [4.5, -9.0, 1.4], [-13.5, 9.5, 1.5], [14.0, 3.5, 1.2], [-8.5, -2.5, 1.2]];
  let kelpTotal = 0;
  const kelpCounts = stands.map(() => 9 + Math.floor(rnd() * 7));
  kelpCounts.forEach((c) => { kelpTotal += c; });
  const kelp = new THREE.InstancedMesh(kelpBlade, kelpMat, kelpTotal);
  let ki = 0;
  stands.forEach(([px, pz, pr], si) => {
    for (let i = 0; i < kelpCounts[si]; i++) {
      const a = rnd() * TAU, d = Math.sqrt(rnd()) * pr;
      const x = px + Math.cos(a) * d, z = pz + Math.sin(a) * d;
      const floor = seabedHeight(x, z);
      dummy.position.set(x, floor - 0.05, z);
      dummy.rotation.set(rr(-0.1, 0.1), rnd() * TAU, rr(-0.1, 0.1));
      dummy.scale.set(rr(0.8, 1.2), Math.min(1.25, (-0.9 - floor) / 4.2) * rr(0.75, 1.0), 1);
      dummy.updateMatrix();
      kelp.setMatrixAt(ki++, dummy.matrix);
    }
  });
  kelp.instanceMatrix.needsUpdate = true;
  kelp.castShadow = false; kelp.receiveShadow = true;
  kelp.name = 'KELP';
  group.add(kelp);

  return {
    group,
    underwaterObjects,
    update() {},
  };
}
