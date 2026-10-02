import * as THREE from 'three';
import type { SeededRandom } from '../utils/Random';
import type { MaterialLibrary } from '../procedural/Materials';
import type { SharedEnvUniforms } from './Environment';

/**
 * Procedural campfire fire — no sprite sheets, no imported flipbooks. The
 * flame is a clutch of upward-tapering quads that the vertex shader turns into
 * cylindrical billboards (always facing the camera, always upright), and the
 * fragment shader carves them into living, scrolling tongues of fbm noise mapped
 * through a black-body heat ramp. The hot core is written above 1.0 so the
 * renderer's bloom pass blooms it; a separate soft, fbm-broken glow billboard
 * scatters warm light into the air around the flames (no hard sprite halo).
 * Embers are GPU-animated points. Each campfire bakes its own noise seed so
 * neighbouring fires flicker out of step.
 */

const NOISE_GLSL = /* glsl */ `
float hash(vec2 p) {
  p = fract(p * vec2(123.34, 345.45));
  p += dot(p, p + 34.345);
  return fract(p.x * p.y);
}
float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 4; i++) { v += a * vnoise(p); p *= 2.0; a *= 0.5; }
  return v;
}
`;

// Cylindrical billboard: face the camera in the horizontal plane, stay upright.
const BILLBOARD_GLSL = /* glsl */ `
vec3 billboard(vec3 local, float sway) {
  vec3 origin = (modelMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
  vec3 toCam = cameraPosition - origin;
  toCam.y = 0.0;
  float l = length(toCam);
  toCam = l > 1e-4 ? toCam / l : vec3(0.0, 0.0, 1.0);
  vec3 right = vec3(-toCam.z, 0.0, toCam.x);
  return origin + right * (local.x + sway) + vec3(0.0, local.y, 0.0);
}
`;

const FLAME_VERTEX = /* glsl */ `
uniform float uTime;
attribute float aSeed;
varying vec2 vUv;
varying float vSeed;
${BILLBOARD_GLSL}
void main() {
  vUv = uv;
  vSeed = aSeed;
  float sway = sin(uTime * 2.4 + aSeed * 8.0 + position.y * 1.0) * 0.09 * position.y;
  gl_Position = projectionMatrix * viewMatrix * vec4(billboard(position, sway), 1.0);
}
`;

const FLAME_FRAGMENT = /* glsl */ `
uniform float uTime;
varying vec2 vUv;
varying float vSeed;
${NOISE_GLSL}
void main() {
  float t = uTime;
  float cx = vUv.x - 0.5;
  float n = fbm(vec2(vUv.x * 3.0 + vSeed * 10.0, vUv.y * 2.4 - t * 1.8 + vSeed * 5.0));
  float warp = (n - 0.5) * 0.5 * (0.4 + vUv.y);
  float width = mix(0.46, 0.04, pow(vUv.y, 0.7));
  float body = smoothstep(width, 0.0, abs(cx + warp));
  float tongue = fbm(vec2(vUv.x * 4.0 + vSeed * 3.0, vUv.y * 3.0 - t * 2.4));
  float topCut = smoothstep(1.0, 0.2, vUv.y + (tongue - 0.5) * 0.7);
  float baseFade = smoothstep(0.0, 0.09, vUv.y);
  float intensity = body * topCut * baseFade;
  intensity *= 0.82 + 0.32 * fbm(vec2(t * 1.6 + vSeed * 20.0, t * 1.1));
  if (intensity < 0.02) discard;

  // black-body heat ramp, hot core pushed into HDR so bloom catches it
  vec3 col = vec3(0.0);
  col = mix(col, vec3(0.75, 0.07, 0.0), smoothstep(0.0, 0.28, intensity));
  col = mix(col, vec3(1.3, 0.42, 0.02), smoothstep(0.22, 0.5, intensity));
  col = mix(col, vec3(1.7, 1.15, 0.28), smoothstep(0.46, 0.76, intensity));
  col = mix(col, vec3(2.4, 2.1, 1.5), smoothstep(0.74, 1.0, intensity));
  float alpha = clamp(intensity * 1.35, 0.0, 1.0);
  gl_FragColor = vec4(col, alpha);
}
`;

// Soft vertical glow that scatters warm light around the flames.
const SCATTER_VERTEX = /* glsl */ `
uniform float uTime;
attribute float aSeed;
varying vec2 vUv;
varying float vSeed;
${BILLBOARD_GLSL}
void main() {
  vUv = uv;
  vSeed = aSeed;
  gl_Position = projectionMatrix * viewMatrix * vec4(billboard(position, 0.0), 1.0);
}
`;

const SCATTER_FRAGMENT = /* glsl */ `
uniform float uTime;
varying vec2 vUv;
varying float vSeed;
${NOISE_GLSL}
void main() {
  float horiz = smoothstep(0.5, 0.0, abs(vUv.x - 0.5));
  float vert = smoothstep(0.0, 0.14, vUv.y) * smoothstep(1.0, 0.32, vUv.y);
  float base = horiz * horiz * vert;
  // break the round falloff with drifting noise so it never reads as a sphere
  float n = fbm(vec2(vUv.x * 2.5 + vSeed * 4.0, vUv.y * 2.0 - uTime * 0.5));
  float glow = base * (0.5 + 0.8 * n);
  float flick = 0.7 + 0.3 * fbm(vec2(uTime * 1.2 + vSeed * 9.0, uTime * 0.6));
  float a = glow * flick * 0.6;
  if (a < 0.01) discard;
  vec3 col = mix(vec3(1.5, 0.5, 0.12), vec3(1.7, 0.85, 0.3), n) * a;
  gl_FragColor = vec4(col, a);
}
`;

const EMBER_VERTEX = /* glsl */ `
uniform float uTime;
attribute float aSeed;
attribute float aScale;
varying float vGlow;
void main() {
  float life = fract(uTime * 0.32 + aSeed);
  vec3 p = position;
  p.y += life * (1.5 + aSeed * 1.3) * aScale;
  p.x += sin(uTime * 1.5 + aSeed * 30.0) * 0.22 * life * aScale;
  p.z += cos(uTime * 1.3 + aSeed * 22.0) * 0.22 * life * aScale;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = -mv.z;
  gl_PointSize = clamp((34.0 + aSeed * 34.0) / dist, 1.0, 7.0) * (1.0 - life * 0.5);
  vGlow = smoothstep(0.0, 0.15, life) * (1.0 - life);
}
`;

const EMBER_FRAGMENT = /* glsl */ `
varying float vGlow;
void main() {
  vec2 pc = gl_PointCoord - 0.5;
  float a = smoothstep(0.5, 0.05, length(pc)) * vGlow;
  vec3 col = mix(vec3(1.6, 0.5, 0.1), vec3(1.8, 1.3, 0.5), vGlow);
  gl_FragColor = vec4(col * a, a);
}
`;

export interface FireKit {
  flameMaterial: THREE.ShaderMaterial;
  scatterMaterial: THREE.ShaderMaterial;
  emberMaterial: THREE.ShaderMaterial;
}

function additive(material: THREE.ShaderMaterialParameters): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    ...material,
  });
}

/** Shared flame / scatter / ember materials (driven by the world clock). */
export function createFireKit(env: SharedEnvUniforms): FireKit {
  return {
    flameMaterial: additive({
      vertexShader: FLAME_VERTEX,
      fragmentShader: FLAME_FRAGMENT,
      uniforms: { uTime: env.uTime },
      side: THREE.DoubleSide,
    }),
    scatterMaterial: additive({
      vertexShader: SCATTER_VERTEX,
      fragmentShader: SCATTER_FRAGMENT,
      uniforms: { uTime: env.uTime },
      side: THREE.DoubleSide,
    }),
    emberMaterial: additive({
      vertexShader: EMBER_VERTEX,
      fragmentShader: EMBER_FRAGMENT,
      uniforms: { uTime: env.uTime },
    }),
  };
}

/** Deterministic value noise in [-1, 1] for vertex roughening. */
function vnoise3(x: number, y: number, z: number): number {
  const s = Math.sin(x * 12.9898 + y * 78.233 + z * 37.719) * 43758.5453;
  return (s - Math.floor(s)) * 2 - 1;
}

/** Push every vertex along its normal by layered noise — no perfect primitives. */
function roughen(geo: THREE.BufferGeometry, amp: number, seed: number): void {
  geo.computeVertexNormals();
  const p = geo.getAttribute('position') as THREE.BufferAttribute;
  const n = geo.getAttribute('normal') as THREE.BufferAttribute;
  for (let i = 0; i < p.count; i++) {
    const px = p.getX(i);
    const py = p.getY(i);
    const pz = p.getZ(i);
    const d =
      amp *
      (0.7 * vnoise3(px * 2.3 + seed, py * 2.3 + seed * 2.0, pz * 2.3 + seed * 3.0) +
        0.3 * vnoise3(px * 6.1 - seed, py * 6.1, pz * 6.1 + seed));
    p.setXYZ(i, px + n.getX(i) * d, py + n.getY(i) * d, pz + n.getZ(i) * d);
  }
  geo.computeVertexNormals();
}

function flameGeometry(rng: SeededRandom, scale: number): THREE.BufferGeometry {
  const tongues = 5;
  const pos: number[] = [];
  const uv: number[] = [];
  const seed: number[] = [];
  const idx: number[] = [];
  let v = 0;
  for (let i = 0; i < tongues; i++) {
    const w = (0.5 + rng.range(0, 0.45)) * scale;
    const h = (1.0 + rng.range(0, 0.95)) * scale;
    const ox = (i === 0 ? 0 : rng.range(-0.24, 0.24)) * scale;
    const s = rng.range(0, 1);
    const corners = [
      [-w / 2 + ox, 0],
      [w / 2 + ox, 0],
      [w / 2 + ox, h],
      [-w / 2 + ox, h],
    ];
    const uvs = [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ];
    for (let k = 0; k < 4; k++) {
      pos.push(corners[k][0], corners[k][1], 0);
      uv.push(uvs[k][0], uvs[k][1]);
      seed.push(s);
    }
    idx.push(v, v + 1, v + 2, v, v + 2, v + 3);
    v += 4;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setAttribute('aSeed', new THREE.Float32BufferAttribute(seed, 1));
  g.setIndex(idx);
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, scale, 0), scale * 3);
  return g;
}

function scatterGeometry(rng: SeededRandom, scale: number): THREE.BufferGeometry {
  const w = 2.4 * scale;
  const h = 2.6 * scale;
  const s = rng.range(0, 1);
  const g = new THREE.BufferGeometry();
  g.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([-w / 2, 0, 0, w / 2, 0, 0, w / 2, h, 0, -w / 2, h, 0], 3),
  );
  g.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2));
  g.setAttribute('aSeed', new THREE.Float32BufferAttribute([s, s, s, s], 1));
  g.setIndex([0, 1, 2, 0, 2, 3]);
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, scale, 0), scale * 3);
  return g;
}

function emberGeometry(rng: SeededRandom, scale: number): THREE.BufferGeometry {
  const n = 30;
  const pos: number[] = [];
  const seed: number[] = [];
  const sc: number[] = [];
  for (let i = 0; i < n; i++) {
    const r = rng.range(0, 0.3) * scale;
    const a = rng.range(0, Math.PI * 2);
    pos.push(Math.cos(a) * r, rng.range(0.05, 0.4) * scale, Math.sin(a) * r);
    seed.push(rng.range(0, 1));
    sc.push(scale);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('aSeed', new THREE.Float32BufferAttribute(seed, 1));
  g.setAttribute('aScale', new THREE.Float32BufferAttribute(sc, 1));
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, scale, 0), scale * 3);
  return g;
}

/** A single campfire: lightable, with a persisted lit/unlit state. */
export class Campfire {
  lit = false;
  readonly firePos: THREE.Vector3;

  constructor(
    private readonly fireGroup: THREE.Object3D,
    firePos: THREE.Vector3,
    private readonly key: string,
    private readonly litSet: Set<string>,
  ) {
    this.firePos = firePos;
    this.lit = litSet.has(key);
    this.fireGroup.visible = this.lit;
  }

  /** Toggle the fire on/off; returns the new lit state. */
  toggle(): boolean {
    this.lit = !this.lit;
    this.fireGroup.visible = this.lit;
    if (this.lit) this.litSet.add(this.key);
    else this.litSet.delete(this.key);
    return this.lit;
  }
}

/** A lumpy boulder, never a clean icosahedron. */
function rockGeometry(radius: number, rng: SeededRandom): THREE.BufferGeometry {
  const geo = new THREE.IcosahedronGeometry(radius, 1);
  roughen(geo, radius * 0.42, rng.range(0, 100));
  geo.scale(rng.range(0.85, 1.2), rng.range(0.6, 1.0), rng.range(0.85, 1.2));
  return geo;
}

/** Place a knotted, tapering log leaning from `base` toward `apex`. */
function addLog(
  group: THREE.Group,
  material: THREE.Material,
  base: THREE.Vector3,
  apex: THREE.Vector3,
  radius: number,
  rng: SeededRandom,
): void {
  const dir = new THREE.Vector3().subVectors(apex, base);
  const len = dir.length();
  const geo = new THREE.CylinderGeometry(radius * 0.7, radius, len, 7, 4);
  roughen(geo, radius * 0.28, rng.range(0, 100));
  geo.translate(0, len / 2, 0);
  const mesh = new THREE.Mesh(geo, material);
  mesh.userData.ownsGeometry = true;
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
  mesh.position.copy(base);
  group.add(mesh);
}

export interface BuiltCampfire {
  object: THREE.Group;
  campfire: Campfire;
  collisionRadius: number;
}

/**
 * Build the full campfire (~3× a normal cookfire): a stone ring, a teepee of
 * unburnt logs, an ash mound — all noise-roughened, no clean primitives — plus
 * a hidden fire group (flames + scatter glow + embers) revealed when lit.
 */
export function buildCampfire(
  rng: SeededRandom,
  materials: MaterialLibrary,
  kit: FireKit,
  scorchMaterial: THREE.Material,
  baseY: number,
  key: string,
  litSet: Set<string>,
): BuiltCampfire {
  const group = new THREE.Group();
  const scale = rng.range(3.0, 3.5);

  // Scorched ground decal, feathered into the grass.
  const scorchR = 1.25 * scale;
  const scorch = new THREE.Mesh(new THREE.CircleGeometry(scorchR, 32), scorchMaterial);
  scorch.rotation.x = -Math.PI / 2;
  scorch.position.y = 0.03;
  scorch.userData.ownsGeometry = true;
  scorch.receiveShadow = true;
  group.add(scorch);

  // Ash mound (a flattened lumpy dome, not a clean disc).
  const ash = new THREE.IcosahedronGeometry(0.5 * scale, 1);
  roughen(ash, 0.5 * scale * 0.3, rng.range(0, 100));
  ash.scale(1, 0.28, 1);
  ash.translate(0, 0.05 * scale, 0);
  const ashMesh = new THREE.Mesh(ash, materials.charcoal);
  ashMesh.userData.ownsGeometry = true;
  ashMesh.receiveShadow = true;
  group.add(ashMesh);

  // Ring of irregular hearth stones.
  const ringR = 0.72 * scale;
  const stoneCount = rng.int(8, 11);
  for (let i = 0; i < stoneCount; i++) {
    const a = (i / stoneCount) * Math.PI * 2 + rng.range(-0.14, 0.14);
    const s = rng.range(0.14, 0.24) * scale;
    const stone = rockGeometry(s, rng);
    const mesh = new THREE.Mesh(stone, materials.stone);
    mesh.userData.ownsGeometry = true;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.position.set(Math.cos(a) * ringR, s * 0.5, Math.sin(a) * ringR);
    mesh.rotation.set(rng.range(0, 0.5), rng.range(0, Math.PI * 2), rng.range(0, 0.5));
    group.add(mesh);
  }

  // Teepee of logs meeting near the centre.
  const logCount = rng.int(5, 7);
  const apex = new THREE.Vector3(rng.range(-0.05, 0.05) * scale, 0.72 * scale, rng.range(-0.05, 0.05) * scale);
  for (let i = 0; i < logCount; i++) {
    const a = (i / logCount) * Math.PI * 2 + rng.range(-0.22, 0.22);
    const br = (0.32 + rng.range(0, 0.08)) * scale;
    const base = new THREE.Vector3(Math.cos(a) * br, 0.02 * scale, Math.sin(a) * br);
    addLog(group, materials.log, base, apex, 0.05 * scale, rng);
  }

  // ---- fire (hidden until lit) --------------------------------------------
  const fireGroup = new THREE.Group();

  const scatter = new THREE.Mesh(scatterGeometry(rng, scale), kit.scatterMaterial);
  scatter.frustumCulled = false;
  scatter.userData.ownsGeometry = true;
  scatter.position.y = 0.1 * scale;
  fireGroup.add(scatter);

  const flames = new THREE.Mesh(flameGeometry(rng, scale), kit.flameMaterial);
  flames.frustumCulled = false;
  flames.userData.ownsGeometry = true;
  flames.position.y = 0.12 * scale;
  fireGroup.add(flames);

  const embers = new THREE.Points(emberGeometry(rng, scale), kit.emberMaterial);
  embers.frustumCulled = false;
  embers.userData.ownsGeometry = true;
  embers.position.y = 0.2 * scale;
  fireGroup.add(embers);

  group.add(fireGroup);

  const campfire = new Campfire(
    fireGroup,
    new THREE.Vector3(0, baseY + 0.6 * scale, 0), // overwritten with world pos by caller
    key,
    litSet,
  );

  return { object: group, campfire, collisionRadius: 0.45 * scale };
}
