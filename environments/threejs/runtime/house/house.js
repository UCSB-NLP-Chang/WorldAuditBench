/* environments/threejs/runtime/house/house.js - "Family House" scene for the harness (scene type "house").
 * GENERATED from environments/threejs/scenes/src/house/app.js by make_harness_module.py - edit there.
 *
 * Port of the standalone walkthrough build: the same two-storey house (real-scale CC0 Poly Haven
 * furniture + PBR textures, procedural architecture), without its own renderer/player - core.js
 * owns rendering, the capsule player, the BVH collision bake and the agent API. Assets are
 * served from /assets/house/pack (export_pack.py).
 *
 * Differences from the standalone build:
 *  - every mesh of the house (walls, floors, stairs, furniture, exterior) is baked into the
 *    BVH, so collision follows the visual geometry and mesh-mutation bugs automatically;
 *    an invisible ramp over the stairs lets the capsule climb them smoothly
 *  - objects get unique names TAG#n (DINING_CHAIR#1 ...) in placement order for bug targeting
 *  - the sun/hemisphere lights of core.js are reused (retuned), the HDRI sky is loaded
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

const { clamp } = THREE.MathUtils;
const PI = Math.PI;

// ---------------------------------------------------------------------------------------------
// Constants (metres)
// ---------------------------------------------------------------------------------------------
const CEIL = 2.7;            // clear ceiling height
const LEVEL_H = 3.0;         // floor-to-floor
const LEVEL_Y = [0, LEVEL_H];
const EXT_T = 0.3;           // exterior wall thickness (0.18 inner leaf + 0.12 brick outer leaf)
const INT_T = 0.12;
const X0 = -7, X1 = 7, Z0 = -5, Z1 = 5;   // exterior wall centre lines
const STAIR = { x0: -1.74, x1: -0.75, zBottom: 2.4, treads: 15, tread: 0.27, riser: LEVEL_H / 16 };
STAIR.zTop = STAIR.zBottom - STAIR.treads * STAIR.tread;   // -1.65
STAIR.holeZ = 2.0;                                          // south edge of the stairwell opening (2.0: headroom for a 1.92 m capsule on the ramp)
const FRONT_DOOR_ANGLE = 0;   // harness scene: the front door stays shut (the standalone walkthrough opens it)
export const SPAWN = { pos: [0.55, 0, 3.9], yawDeg: 0 };    // hall, just inside the front door, facing north
export const HOUSE_BOUNDS = { minX: -6.6, maxX: 6.6, minZ: -4.6, maxZ: 4.6 };   // interior (exterior doors are locked)

// ---------------------------------------------------------------------------------------------
// Scene handles (assigned by buildHouse)
// ---------------------------------------------------------------------------------------------
let scene = null, renderer = null, BASE = '/assets/house/pack', manifest = null;
const root = new THREE.Group();
root.name = 'HOUSE_ROOT';
const floors = [new THREE.Group(), new THREE.Group()];
floors[0].name = 'GROUND_FLOOR';
floors[1].name = 'UPPER_FLOOR';
floors[1].position.y = LEVEL_H;
root.add(floors[0], floors[1]);
const exterior = new THREE.Group();
exterior.name = 'EXTERIOR';
root.add(exterior);

const colliders = [];   // {box: Box3 (world), floor: 0|1|2(both)} - kept as metadata only (physics = BVH)
const semantic = {};    // tag -> [objects]
let itemCount = 0;
const lamps = [];       // flickering point lights

// register(tag, obj): the LAST tag given to an object wins (makers tag the group, placeGroup
// re-tags it with the plan name); unique names TAG#n are assigned in assignNames()
function register(name, obj) {
  if (obj.userData.tag) {
    const l = semantic[obj.userData.tag];
    const i = l ? l.indexOf(obj) : -1;
    if (i >= 0) l.splice(i, 1);
  } else itemCount++;
  obj.userData.tag = name;
  (semantic[name] || (semantic[name] = [])).push(obj);
  return obj;
}
function assignNames() {
  const counts = {};
  root.traverse(o => {
    const tag = o.userData.tag;
    if (!tag) return;
    counts[tag] = (counts[tag] || 0) + 1;
    o.name = `${tag}#${counts[tag]}`;
  });
}
function addCollider(obj, floor, pad = 0) {
  obj.updateWorldMatrix(true, true);
  const b = new THREE.Box3().setFromObject(obj, true);
  b.min.x -= pad; b.max.x += pad; b.min.z -= pad; b.max.z += pad;
  colliders.push({ box: b, floor });
  return b;
}
function colliderBox(x0, x1, z0, z1, floor) {
  colliders.push({ box: new THREE.Box3(new THREE.Vector3(x0, -1, z0), new THREE.Vector3(x1, 100, z1)), floor });
}
function shadowed(o, cast = true, receive = true) {
  o.traverse(m => { if (m.isMesh) { m.castShadow = cast; m.receiveShadow = receive; } });
  return o;
}

// ---------------------------------------------------------------------------------------------
// Asset decoding
// ---------------------------------------------------------------------------------------------
const texLoader = new THREE.TextureLoader();
const gltfLoader = new GLTFLoader();
let anisotropy = 8;

async function loadTexture(url, srgb) {
  const t = await texLoader.loadAsync(url);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = anisotropy;
  t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  return t;
}
const texCache = {};
async function texSet(id) {
  if (texCache[id]) return texCache[id];
  const kinds = manifest.textures[id] || [];
  const get = k => kinds.includes(k) ? loadTexture(`${BASE}/tex/${id}.${k}.webp`, k === 'diff') : null;
  const [diff, nor, arm] = await Promise.all([get('diff'), get('nor'), get('arm')]);
  return (texCache[id] = { diff, nor, arm });
}
// PBR material whose maps tile every `tile` metres (geometry UVs are in metres)
async function pbr(id, tile, opts = {}) {
  const s = await texSet(id);
  const rep = 1 / tile;
  const m = new THREE.MeshStandardMaterial({
    color: opts.color ?? 0xffffff,
    roughness: opts.roughness ?? 1,
    metalness: opts.metalness ?? 0,
    envMapIntensity: opts.envMapIntensity ?? 1,
    side: opts.side ?? THREE.FrontSide,
  });
  const maps = [];
  if (s.diff && !opts.noDiffuse) { m.map = s.diff.clone(); maps.push(m.map); }
  if (s.nor) { m.normalMap = s.nor.clone(); m.normalScale = new THREE.Vector2(opts.normalScale ?? 1, opts.normalScale ?? 1); maps.push(m.normalMap); }
  if (s.arm) {
    m.aoMap = s.arm.clone(); m.roughnessMap = m.aoMap; m.metalnessMap = m.aoMap; maps.push(m.aoMap);
    m.aoMapIntensity = opts.ao ?? 1;
  }
  for (const t of maps) { t.repeat.set(rep * (opts.repeatX ?? 1), rep * (opts.repeatY ?? 1)); t.rotation = opts.rotation ?? 0; t.needsUpdate = true; }
  return m;
}
const protos = {};
async function loadModel(id) {
  const e = manifest.models[id];
  const gltf = await gltfLoader.loadAsync(`${BASE}/models/${id}.glb`);
  const obj = gltf.scene;
  obj.traverse(o => {
    if (o.isMesh) {
      o.castShadow = o.receiveShadow = true;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats) {
        if (m.transmission > 0) { m.transmission = 0; m.transparent = true; m.opacity = 0.55; m.depthWrite = false; }
        if (m.map) m.map.anisotropy = anisotropy;
      }
    }
  });
  obj.userData.bbox = new THREE.Box3(new THREE.Vector3(e.bbox[0], e.bbox[1], e.bbox[2]), new THREE.Vector3(e.bbox[3], e.bbox[4], e.bbox[5]));
  protos[id] = obj;
  return obj;
}

function boxGeo(w, h, d, uvScale = 1) {
  const g = new THREE.BoxGeometry(w, h, d);
  const uv = g.attributes.uv;
  const dims = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
  for (let i = 0; i < uv.count; i++) {
    const f = Math.floor(i / 4);
    uv.setXY(i, uv.getX(i) * dims[f][0] * uvScale, uv.getY(i) * dims[f][1] * uvScale);
  }
  return g;
}
function curtainGeo(w, h) {
  // pleated panel: plane displaced by a sine wave along its width
  const g = new THREE.PlaneGeometry(w, h, 40, 1);
  const pos = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    pos.setZ(i, Math.sin((x / w) * PI * 2 * 5) * 0.035);
    uv.setXY(i, uv.getX(i) * w * 3, uv.getY(i) * h);
  }
  g.computeVertexNormals();
  return g;
}
function planeGeo(w, h) {
  const g = new THREE.PlaneGeometry(w, h);
  const uv = g.attributes.uv;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * w, uv.getY(i) * h);
  return g;
}
function box(parent, w, h, d, mat, x, y, z, name) {
  const m = new THREE.Mesh(boxGeo(w, h, d), mat);
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  parent.add(m);
  if (name) register(name, m);
  return m;
}
function rbox(parent, w, h, d, r, mat, x, y, z, name) {
  const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, r), mat);
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  parent.add(m);
  if (name) register(name, m);
  return m;
}
function cyl(parent, rt, rb, h, mat, x, y, z, seg = 24, name) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), mat);
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  parent.add(m);
  if (name) register(name, m);
  return m;
}
function group(parent, x, y, z, rot = 0) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  g.rotation.y = rot;
  parent.add(g);
  return g;
}

// ---------------------------------------------------------------------------------------------
// Materials
// ---------------------------------------------------------------------------------------------
const M = {};
async function buildMaterials() {
  // painted plaster: a low-contrast plaster diffuse map normalised to the paint colour (the
  // material colour is the tint divided by the map's mean, so the average stays the paint colour
  // and only the +-5 % grain remains) - a flat colour + normal map reads as a "blank white void"
  // to VLM agents pressed against a wall, and they never turn away
  const PLASTER_MEAN = new THREE.Color(158 / 255, 140 / 255, 120 / 255);   // beige_wall_001 diffuse mean (plain grain, no panel lines)
  const grain = (tint) => { const c = new THREE.Color(tint); c.r /= PLASTER_MEAN.r; c.g /= PLASTER_MEAN.g; c.b /= PLASTER_MEAN.b; return c; };
  const paint = async (color) => pbr('beige_wall_001', 1.2, { color: grain(color), roughness: 0.95, normalScale: 0.6 });
  [M.cream, M.white, M.sage, M.bluegrey, M.yellow] = await Promise.all([
    paint(0xf3eee4), paint(0xf7f6f2), paint(0xd3dccb), paint(0xcbd6e1), paint(0xf1e6cc)]);
  M.ceiling = await pbr('plastered_wall_02', 2.5, { color: 0xffffff, normalScale: 0.25, noDiffuse: true, roughness: 0.9 });
  M.laminate = await pbr('laminate_floor_02', 2.0, { roughness: 1, rotation: 0 });
  M.laminateZ = await pbr('laminate_floor_02', 2.0, { rotation: PI / 2 });
  M.parquet = await pbr('herringbone_parquet', 1.6);
  M.greyTile = await pbr('grey_tiles', 1.2);
  M.bathTile = await pbr('floor_tiles_06', 0.9);
  M.wallTile = await pbr('long_white_tiles', 1.0, { color: 0xf7f7f5 });
  M.brick = await pbr('brick_wall_001', 2.0);
  M.roof = await pbr('roof_tiles_14', 1.6);
  M.grass = await pbr('leafy_grass', 3.0);
  M.pavers = await pbr('concrete_pavers_02', 2.0);
  M.marble = await pbr('marble_01', 1.5, { roughness: 0.6 });
  M.oak = await pbr('oak_veneer_01', 1.5);
  M.oakZ = await pbr('oak_veneer_01', 1.5, { rotation: PI / 2 });
  M.darkwood = await pbr('fine_grained_wood', 1.2);
  M.denim = await pbr('denim_fabric', 1.0, { color: 0xc4d0dc });
  M.linen = await pbr('denim_fabric', 0.7, { color: 0xf1ede6, noDiffuse: true });
  M.curtain = await pbr('denim_fabric', 0.9, { color: 0xe9e4da, noDiffuse: true, side: THREE.DoubleSide });
  M.curtainBlue = await pbr('denim_fabric', 0.9, { color: 0x9fb0c2, noDiffuse: true, side: THREE.DoubleSide });
  M.rugRed = await pbr('quatrefoil_jacquard_fabric', 1.0, { color: 0xcdbcb4 });
  M.rugGrey = await pbr('quatrefoil_jacquard_fabric', 0.8, { color: 0x9c9a94, noDiffuse: true });
  M.rugBlue = await pbr('quatrefoil_jacquard_fabric', 0.8, { color: 0x7d93ad, noDiffuse: true });
  M.towel = await pbr('denim_fabric', 0.5, { color: 0xf2f2ee, noDiffuse: true });
  M.towelBlue = await pbr('denim_fabric', 0.5, { color: 0x8fb0cc, noDiffuse: true });
  M.leather = await pbr('fabric_leather_02', 1.0, { color: 0x6b4a34 });

  M.trim = new THREE.MeshStandardMaterial({ color: 0xf6f3ec, roughness: 0.45 });
  M.trimPlaster = await pbr('beige_wall_001', 1.2, { color: grain(0xf6f3ec), roughness: 0.6, normalScale: 0.4 });   // big painted slabs (stair sides)
  M.door = new THREE.MeshStandardMaterial({ color: 0xf3efe6, roughness: 0.5 });
  M.doorDark = new THREE.MeshStandardMaterial({ color: 0x3b3f44, roughness: 0.55 });
  M.ceramic = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.14, metalness: 0, clearcoat: 0.6, clearcoatRoughness: 0.15 });
  M.chrome = new THREE.MeshStandardMaterial({ color: 0xe6e8ea, metalness: 1, roughness: 0.18, envMapIntensity: 1.6 });
  M.steel = new THREE.MeshStandardMaterial({ color: 0xd2d6d9, metalness: 0.7, roughness: 0.3, envMapIntensity: 1.6 });
  M.black = new THREE.MeshStandardMaterial({ color: 0x15171a, roughness: 0.5, metalness: 0.2 });
  M.blackGloss = new THREE.MeshPhysicalMaterial({ color: 0x0a0b0d, roughness: 0.12, metalness: 0.3, clearcoat: 0.8 });
  M.screen = new THREE.MeshPhysicalMaterial({ color: 0x06080c, roughness: 0.08, metalness: 0.5, clearcoat: 1, clearcoatRoughness: 0.05 });
  M.glass = new THREE.MeshPhysicalMaterial({ color: 0xdff2f7, roughness: 0.04, metalness: 0, transparent: true, opacity: 0.16, side: THREE.DoubleSide, envMapIntensity: 1.2, depthWrite: false });
  M.frosted = new THREE.MeshPhysicalMaterial({ color: 0xe6f0f2, roughness: 0.55, transparent: true, opacity: 0.5, side: THREE.DoubleSide });
  M.mirror = new THREE.MeshStandardMaterial({ color: 0xaeb6bb, metalness: 1, roughness: 0.22, envMapIntensity: 1.3 });
  M.whiteGloss = new THREE.MeshPhysicalMaterial({ color: 0xf2f2ee, roughness: 0.28, clearcoat: 0.4 });
  M.appliance = new THREE.MeshPhysicalMaterial({ color: 0xeeeeea, roughness: 0.32, clearcoat: 0.3 });
  M.cabinet = new THREE.MeshStandardMaterial({ color: 0xeceae3, roughness: 0.42 });
  M.cabinetGrey = new THREE.MeshStandardMaterial({ color: 0x7e8489, roughness: 0.45 });
  M.shade = new THREE.MeshStandardMaterial({ color: 0xf1e2c4, roughness: 0.9, side: THREE.DoubleSide, emissive: 0x8a6a3c, emissiveIntensity: 0.55 });
  M.bulb = new THREE.MeshStandardMaterial({ color: 0xfff6e0, emissive: 0xfff1cc, emissiveIntensity: 3.5 });
  M.downlight = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfff4e2, emissiveIntensity: 2.2 });
  M.plastic = new THREE.MeshStandardMaterial({ color: 0xe9e9e9, roughness: 0.6 });
  M.rail = new THREE.MeshStandardMaterial({ color: 0x2f3236, metalness: 0.7, roughness: 0.35 });
  M.pillowWhite = M.linen;
}

// ---------------------------------------------------------------------------------------------
// Architecture
// ---------------------------------------------------------------------------------------------
// A wall run along an axis.  spec = {axis:'x'|'z', at, from, to, level, ext, left, right, openings:[{c,w,sill,top,kind,hinge,swing}]}
// For axis 'x' the +normal ("left") side is +z (south); for axis 'z' the left side is -x (west).
const doorLeaves = [];
function wallRun(spec) {
  const level = spec.level;
  const parent = floors[level];
  const yb = 0;
  const isExt = !!spec.ext;
  const t = isExt ? EXT_T : INT_T;
  const height = isExt ? LEVEL_H : CEIL;          // exterior leaves run up through the slab edge
  const ops = [...(spec.openings || [])].sort((a, b) => a.c - b.c);
  const posAt = (u, off) => spec.axis === 'x' ? [u, spec.at + off] : [spec.at - off, u];  // off along +normal
  const rot = spec.axis === 'x' ? 0 : -PI / 2;
  const center = spec.axis === 'x' ? [0, 0] : [0, 0];
  // which side is inside for exterior walls: toward the house centre
  let insideSign = 1;
  if (isExt) {
    const mid = posAt((spec.from + spec.to) / 2, 0);
    const toCentre = spec.axis === 'x' ? -mid[1] : mid[0];   // +normal for 'x' is +z; for 'z' it is -x
    insideSign = toCentre > 0 ? 1 : -1;
  }
  const matFor = (side) => side > 0 ? (M[spec.left] || M.cream) : (M[spec.right] || M.cream);

  function piece(u0, u1, y0, y1, thick, off, mats, collide, baseboard) {
    const len = u1 - u0;
    if (len <= 0.001 || y1 - y0 <= 0.001) return null;
    const [px, pz] = posAt((u0 + u1) / 2, off);
    const g = boxGeo(len, y1 - y0, thick);
    const mesh = new THREE.Mesh(g, mats);
    mesh.position.set(px, yb + (y0 + y1) / 2, pz);
    mesh.rotation.y = rot;
    mesh.castShadow = mesh.receiveShadow = true;
    parent.add(mesh);
    register('WALL', mesh);
    if (collide) addCollider(mesh, level, 0);
    if (baseboard) {
      for (const side of baseboard) {
        const [bx, bz] = posAt((u0 + u1) / 2, off + side * (thick / 2 + 0.008));
        const bb = new THREE.Mesh(boxGeo(len, 0.1, 0.016), M.trim);
        bb.position.set(bx, yb + 0.05, bz);
        bb.rotation.y = rot;
        bb.castShadow = bb.receiveShadow = true;
        parent.add(bb);
        register('BASEBOARD', bb);
      }
    }
    return mesh;
  }
  // segments between openings
  const leaves = isExt
    ? [{ thick: 0.18, off: insideSign * 0.06, mats: [matFor(insideSign), matFor(insideSign), matFor(insideSign), matFor(insideSign), insideSign > 0 ? matFor(1) : M.brick, insideSign > 0 ? M.brick : matFor(-1)], h: CEIL, baseboard: spec.noBaseboard ? null : [insideSign] },
       { thick: 0.12, off: -insideSign * 0.09, mats: M.brick, h: height, baseboard: null }]
    : [{ thick: INT_T, off: 0, mats: [matFor(1), matFor(1), matFor(1), matFor(1), matFor(1), matFor(-1)], h: CEIL, baseboard: spec.noBaseboard ? null : [1, -1] }];
  let cursor = spec.from;
  for (const op of ops) {
    const a = op.c - op.w / 2, b = op.c + op.w / 2;
    for (const L of leaves) piece(cursor, a, 0, L.h, L.thick, L.off, L.mats, true, L.baseboard);
    const sill = op.sill ?? 0, top = op.top ?? 2.1;
    for (const L of leaves) {
      if (sill > 0) piece(a, b, 0, sill, L.thick, L.off, L.mats, true, null);
      piece(a, b, top, L.h, L.thick, L.off, L.mats, false, null);
    }
    if (op.kind === 'window') makeWindow(spec, op, level, t, insideSign);
    else makeDoorway(spec, op, level, t, insideSign);
    cursor = b;
  }
  for (const L of leaves) piece(cursor, spec.to, 0, L.h, L.thick, L.off, L.mats, true, L.baseboard);
}

function makeWindow(spec, op, level, t, insideSign) {
  const parent = floors[level];
  const [cx, cz] = spec.axis === 'x' ? [op.c, spec.at] : [spec.at, op.c];
  const g = group(parent, cx, 0, cz, spec.axis === 'x' ? 0 : -PI / 2);
  register('WINDOW', g);
  const w = op.w, h = op.top - op.sill, yc = (op.top + op.sill) / 2;
  const fr = 0.06, depth = t + 0.02;
  box(g, fr, h, depth, M.trim, -w / 2 + fr / 2, yc, 0, 'WINDOW_FRAME');
  box(g, fr, h, depth, M.trim, w / 2 - fr / 2, yc, 0, 'WINDOW_FRAME');
  box(g, w, fr, depth, M.trim, 0, op.top - fr / 2, 0, 'WINDOW_FRAME');
  box(g, w, fr, depth, M.trim, 0, op.sill + fr / 2, 0, 'WINDOW_FRAME');
  if (w > 1.3) box(g, 0.045, h, depth - 0.02, M.trim, 0, yc, 0, 'WINDOW_MULLION');
  box(g, w, 0.045, depth - 0.02, M.trim, 0, op.sill + h * 0.62, 0, 'WINDOW_MULLION');
  const glass = new THREE.Mesh(planeGeo(w - fr * 2, h - fr * 2), M.glass);
  glass.position.set(0, yc, 0);
  g.add(glass);
  register('WINDOW_GLASS', glass);
  // sills: interior board and exterior stone
  const inS = spec.ext ? insideSign : 1;
  const sgn = spec.axis === 'x' ? inS : inS;   // group local +z == wall +normal
  box(g, w + 0.16, 0.035, 0.11, M.trim, 0, op.sill - 0.0175 + 0.001, sgn * (t / 2 + 0.04), 'WINDOW_SILL');
  if (spec.ext) box(g, w + 0.1, 0.05, 0.12, M.cabinetGrey, 0, op.sill - 0.03, -sgn * (t / 2 + 0.05), 'WINDOW_SILL');
  // curtains inside
  if (op.curtain) {
    const rodY = op.top + 0.18;
    const rod = cyl(g, 0.014, 0.014, w + 0.6, M.rail, 0, rodY, sgn * (t / 2 + 0.11), 12, 'CURTAIN_ROD');
    rod.rotation.z = PI / 2;
    const cm = op.curtain === 'blue' ? M.curtainBlue : M.curtain;
    for (const s of [-1, 1]) {
      const c = new THREE.Mesh(curtainGeo(0.55, rodY - 0.05), cm);
      c.position.set(s * (w / 2 + 0.08), (rodY - 0.05) / 2 + 0.02, sgn * (t / 2 + 0.11));
      c.castShadow = c.receiveShadow = true;
      g.add(c);
      register('CURTAIN', c);
    }
  }
}

function makeDoorway(spec, op, level, t, insideSign) {
  const parent = floors[level];
  const [cx, cz] = spec.axis === 'x' ? [op.c, spec.at] : [spec.at, op.c];
  const g = group(parent, cx, 0, cz, spec.axis === 'x' ? 0 : -PI / 2);
  const w = op.w, h = op.top ?? 2.1;
  const jamb = 0.045, depth = t + 0.01;
  register(op.kind === 'open' ? 'DOORWAY' : 'DOOR_FRAME', g);
  // jambs + head
  box(g, jamb, h, depth, M.trim, -w / 2 + jamb / 2, h / 2, 0, 'DOOR_JAMB');
  box(g, jamb, h, depth, M.trim, w / 2 - jamb / 2, h / 2, 0, 'DOOR_JAMB');
  box(g, w, jamb, depth, M.trim, 0, h - jamb / 2, 0, 'DOOR_HEAD');
  // casings on both faces (inside only for exterior walls)
  const faces = spec.ext ? [insideSign] : [1, -1];
  for (const s of faces) {
    const zc = s * (t / 2 + 0.008);
    box(g, 0.075, h + 0.06, 0.016, M.trim, -w / 2 - 0.01, (h + 0.06) / 2, zc, 'DOOR_CASING');
    box(g, 0.075, h + 0.06, 0.016, M.trim, w / 2 + 0.01, (h + 0.06) / 2, zc, 'DOOR_CASING');
    box(g, w + 0.095, 0.075, 0.016, M.trim, 0, h + 0.06 - 0.0375, zc, 'DOOR_CASING');
  }
  if (op.kind === 'open') return;
  // door leaf hinged at one jamb, swung into the room on `swing` side
  const lw = w - jamb * 2 - 0.006, lh = h - jamb - 0.01;
  const hingeSide = op.hinge === 'hi' ? 1 : -1;   // +1 = hinge at the high-coordinate end
  const swing = op.swing ?? 1;
  const hinge = new THREE.Group();
  hinge.position.set(hingeSide * (w / 2 - jamb), 0, 0);
  g.add(hinge);
  const leaf = new THREE.Group();
  hinge.add(leaf);
  const dir = -hingeSide;        // leaf extends from the hinge toward the other jamb
  const glassDoor = op.kind === 'glassdoor';
  const frontDoor = op.kind === 'frontdoor';
  const mat = frontDoor ? M.doorDark : M.door;
  const slab = box(leaf, lw, lh, 0.042, mat, dir * lw / 2, lh / 2 + 0.01, 0, frontDoor ? 'FRONT_DOOR' : glassDoor ? 'BACK_DOOR' : 'DOOR');
  if (glassDoor) {
    box(leaf, lw - 0.24, lh - 0.5, 0.046, M.glass, dir * lw / 2, lh / 2 + 0.16, 0, 'DOOR_GLASS');
  } else {
    // two recessed panels
    for (const [py, ph] of [[lh * 0.7, lh * 0.42], [lh * 0.27, lh * 0.34]]) {
      for (const s of [1, -1]) {
        const p = new THREE.Mesh(boxGeo(lw - 0.2, ph, 0.012), mat);
        p.position.set(dir * lw / 2, py, s * 0.024);
        p.receiveShadow = true;
        leaf.add(p);
      }
    }
  }
  // handle
  for (const s of [1, -1]) {
    const hg = cyl(leaf, 0.028, 0.028, 0.012, M.chrome, dir * (lw - 0.07), 1.02, s * 0.03, 16);
    hg.rotation.x = PI / 2;
    const lever = box(leaf, 0.12, 0.018, 0.018, M.chrome, dir * (lw - 0.07) - dir * 0.05, 1.02, s * 0.052);
    lever.castShadow = false;
  }
  register('DOOR_HANDLE', slab);
  const angle = op.angle ?? (frontDoor ? FRONT_DOOR_ANGLE : glassDoor ? 0 : 1.75);
  // rotate so the leaf swings toward `swing` side (+normal = local +z)
  leaf.rotation.y = -dir * swing * angle;
  doorLeaves.push({ leaf, level, op });
  // collider from the leaf's world box
  slab.updateWorldMatrix(true, true);
  addCollider(slab, level, 0.02);
}

function floorPiece(level, x0, x1, z0, z1, mat, name = 'FLOOR', y = 0, thick = 0.02) {
  const m = new THREE.Mesh(boxGeo(x1 - x0, thick, z1 - z0), mat);
  m.position.set((x0 + x1) / 2, y - thick / 2, (z0 + z1) / 2);
  m.receiveShadow = true;
  m.castShadow = false;
  floors[level].add(m);
  register(name, m);
  return m;
}
function ceilingPiece(level, x0, x1, z0, z1, y = CEIL) {
  const m = new THREE.Mesh(boxGeo(x1 - x0, 0.02, z1 - z0), M.ceiling);
  m.position.set((x0 + x1) / 2, y + 0.01, (z0 + z1) / 2);
  m.receiveShadow = true;
  floors[level].add(m);
  register('CEILING', m);
  return m;
}

const ROOMS = [
  // level 0
  { id: 'living', label: 'Living room', level: 0, x0: -6.85, x1: -1.86, z0: -1.14, z1: 4.85, floor: 'laminate', light: [[-4.6, 1.6]], shadow: true },
  { id: 'study', label: 'Study', level: 0, x0: -6.85, x1: -4.26, z0: -4.85, z1: -1.26, floor: 'laminateZ', light: [[-5.55, -3.05]], shadow: true },
  { id: 'bath1', label: 'Bathroom', level: 0, x0: -4.14, x1: -1.86, z0: -4.85, z1: -2.66, floor: 'bathTile', light: [[-3.0, -3.75]], down: true },
  { id: 'laundry', label: 'Laundry', level: 0, x0: -4.14, x1: -1.86, z0: -2.54, z1: -1.26, floor: 'greyTile', light: [[-3.0, -1.9]], down: true },
  { id: 'hall', label: 'Hall', level: 0, x0: -1.74, x1: 1.74, z0: -4.85, z1: 4.85, floor: 'parquet', light: [[0.6, 3.2], [0.6, -3.2]], down: true },
  { id: 'kitchen', label: 'Kitchen', level: 0, x0: 1.86, x1: 6.85, z0: -4.85, z1: -0.6, floor: 'greyTile', light: [[4.4, -3.6]], shadow: true, down: true },
  { id: 'dining', label: 'Dining room', level: 0, x0: 1.86, x1: 6.85, z0: -0.6, z1: 4.85, floor: 'laminate', light: [], shadow: false },
  // level 1
  { id: 'master', label: 'Master bedroom', level: 1, x0: -6.85, x1: -1.86, z0: -1.14, z1: 4.85, floor: 'laminate', light: [[-5.0, 1.9]], shadow: true },
  { id: 'ensuite', label: 'En-suite', level: 1, x0: -6.85, x1: -4.46, z0: -4.85, z1: -1.26, floor: 'greyTile', light: [[-5.65, -3.05]], down: true },
  { id: 'dressing', label: 'Dressing room', level: 1, x0: -4.34, x1: -1.86, z0: -4.85, z1: -1.26, floor: 'laminateZ', light: [[-3.1, -3.05]], down: true },
  { id: 'landing', label: 'Upstairs landing', level: 1, x0: -1.74, x1: 1.74, z0: -4.85, z1: 4.85, floor: 'parquet', light: [[0.6, 3.2], [0.6, -3.2]], down: true },
  { id: 'kids', label: 'Kids room', level: 1, x0: 1.86, x1: 6.85, z0: -4.85, z1: -0.66, floor: 'laminate', light: [[4.4, -2.75]], shadow: true },
  { id: 'lounge', label: 'Family lounge', level: 1, x0: 1.86, x1: 6.85, z0: -0.54, z1: 4.85, floor: 'laminate', light: [[4.4, 2.15]], shadow: true },
];
function roomAt(x, z, level) {
  for (const r of ROOMS) if (r.level === level && x >= r.x0 - 0.1 && x <= r.x1 + 0.1 && z >= r.z0 - 0.1 && z <= r.z1 + 0.1) return r;
  return null;
}

function buildArchitecture() {
  // ---- floors & ceilings
  for (const r of ROOMS) {
    if (r.id === 'landing') {
      // landing floor minus the stairwell hole
      floorPiece(1, STAIR.x1, r.x1, r.z0, r.z1, M[r.floor]);
      floorPiece(1, r.x0, STAIR.x1, r.z0, STAIR.zTop, M[r.floor]);
      floorPiece(1, r.x0, STAIR.x1, STAIR.holeZ, r.z1, M[r.floor]);
      continue;
    }
    floorPiece(r.level, r.x0, r.x1, r.z0, r.z1, M[r.floor]);
  }
  // ground-floor ceiling (underside of the upper slab) with the stairwell opening
  ceilingPiece(0, -6.85, STAIR.x0, -4.85, 4.85);
  ceilingPiece(0, STAIR.x1, 6.85, -4.85, 4.85);
  ceilingPiece(0, STAIR.x0, STAIR.x1, -4.85, STAIR.zTop);
  ceilingPiece(0, STAIR.x0, STAIR.x1, STAIR.holeZ, 4.85);
  ceilingPiece(1, -6.85, 6.85, -4.85, 4.85);
  // slab edge (fascia) around the stairwell hole, seen from the stairs
  box(floors[0], STAIR.x1 - STAIR.x0, LEVEL_H - CEIL, 0.02, M.trim, (STAIR.x0 + STAIR.x1) / 2, (LEVEL_H + CEIL) / 2, STAIR.holeZ, 'STAIRWELL_EDGE');
  box(floors[0], STAIR.x1 - STAIR.x0, LEVEL_H - CEIL, 0.02, M.trim, (STAIR.x0 + STAIR.x1) / 2, (LEVEL_H + CEIL) / 2, STAIR.zTop, 'STAIRWELL_EDGE');
  box(floors[0], 0.02, LEVEL_H - CEIL, STAIR.holeZ - STAIR.zTop, M.trim, STAIR.x1, (LEVEL_H + CEIL) / 2, (STAIR.holeZ + STAIR.zTop) / 2, 'STAIRWELL_EDGE');
  box(floors[0], 0.02, LEVEL_H - CEIL, STAIR.holeZ - STAIR.zTop, M.trim, STAIR.x0, (LEVEL_H + CEIL) / 2, (STAIR.holeZ + STAIR.zTop) / 2, 'STAIRWELL_EDGE');

  // ---- walls, level 0
  const W = (o) => wallRun(o);
  // exterior south (z=5): left(+z) side is outside, right(-z) inside
  W({ axis: 'x', at: Z1, from: X0, to: -1.8, level: 0, ext: true, right: 'cream', openings: [{ c: -4.4, w: 2.4, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  W({ axis: 'x', at: Z1, from: -1.8, to: 1.8, level: 0, ext: true, right: 'cream', openings: [{ c: 0, w: 1.0, top: 2.1, kind: 'frontdoor', hinge: 'lo', swing: -1 }] });
  W({ axis: 'x', at: Z1, from: 1.8, to: X1, level: 0, ext: true, right: 'white', openings: [{ c: 4.4, w: 2.4, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  // exterior north (z=-5): inside is +z (left)
  W({ axis: 'x', at: Z0, from: X0, to: -4.2, level: 0, ext: true, left: 'sage', openings: [{ c: -5.6, w: 1.6, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  W({ axis: 'x', at: Z0, from: -4.2, to: -1.8, level: 0, ext: true, left: 'wallTile', noBaseboard: true, openings: [{ c: -3.0, w: 0.8, sill: 1.5, top: 2.2, kind: 'window' }] });
  W({ axis: 'x', at: Z0, from: -1.8, to: 1.8, level: 0, ext: true, left: 'cream', openings: [{ c: 0.7, w: 1.0, top: 2.1, kind: 'glassdoor', hinge: 'hi', swing: 1 }] });
  W({ axis: 'x', at: Z0, from: 1.8, to: X1, level: 0, ext: true, left: 'white', openings: [{ c: 4.4, w: 2.0, sill: 1.1, top: 2.2, kind: 'window' }] });
  // exterior west (x=-7): +normal(left) is -x = outside; inside is right
  W({ axis: 'z', at: X0, from: Z0, to: -1.2, level: 0, ext: true, right: 'sage', openings: [{ c: -3.2, w: 2.0, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  W({ axis: 'z', at: X0, from: -1.2, to: Z1, level: 0, ext: true, right: 'cream', openings: [{ c: 1.8, w: 2.4, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  // exterior east (x=7): inside is -x = left
  W({ axis: 'z', at: X1, from: Z0, to: -0.6, level: 0, ext: true, left: 'white', openings: [{ c: -2.8, w: 1.6, sill: 1.1, top: 2.2, kind: 'window' }] });
  W({ axis: 'z', at: X1, from: -0.6, to: Z1, level: 0, ext: true, left: 'white', openings: [{ c: 2.2, w: 2.4, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  // interior, level 0
  W({ axis: 'z', at: -1.8, from: Z0, to: -2.6, level: 0, left: 'wallTile', right: 'cream', openings: [{ c: -3.85, w: 0.9, kind: 'door', hinge: 'hi', swing: 1 }] });
  W({ axis: 'z', at: -1.8, from: -2.6, to: -1.2, level: 0, left: 'white', right: 'cream', openings: [{ c: -2.05, w: 0.9, kind: 'door', hinge: 'hi', swing: 1 }] });
  W({ axis: 'z', at: -1.8, from: -1.2, to: Z1, level: 0, left: 'cream', right: 'cream', openings: [{ c: 3.8, w: 2.0, top: 2.2, kind: 'open' }] });
  W({ axis: 'z', at: 1.8, from: Z0, to: Z1, level: 0, left: 'cream', right: 'white', openings: [{ c: -3.4, w: 2.0, top: 2.2, kind: 'open' }, { c: 3.8, w: 2.0, top: 2.2, kind: 'open' }] });
  W({ axis: 'x', at: -1.2, from: X0, to: -4.2, level: 0, left: 'cream', right: 'sage', openings: [{ c: -4.85, w: 0.9, kind: 'door', hinge: 'hi', swing: -1 }] });
  W({ axis: 'x', at: -1.2, from: -4.2, to: -1.8, level: 0, left: 'cream', right: 'white' });
  W({ axis: 'z', at: -4.2, from: Z0, to: -2.6, level: 0, left: 'sage', right: 'wallTile' });
  W({ axis: 'z', at: -4.2, from: -2.6, to: -1.2, level: 0, left: 'sage', right: 'white' });
  W({ axis: 'x', at: -2.6, from: -4.2, to: -1.8, level: 0, left: 'white', right: 'wallTile' });

  // ---- walls, level 1
  W({ axis: 'x', at: Z1, from: X0, to: -1.8, level: 1, ext: true, right: 'bluegrey', openings: [{ c: -4.4, w: 2.4, sill: 0.9, top: 2.2, kind: 'window', curtain: 'blue' }] });
  W({ axis: 'x', at: Z1, from: -1.8, to: 1.8, level: 1, ext: true, right: 'cream', openings: [{ c: 0, w: 1.2, sill: 1.0, top: 2.2, kind: 'window' }] });
  W({ axis: 'x', at: Z1, from: 1.8, to: X1, level: 1, ext: true, right: 'white', openings: [{ c: 4.4, w: 2.4, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  W({ axis: 'x', at: Z0, from: X0, to: -4.4, level: 1, ext: true, left: 'wallTile', noBaseboard: true, openings: [{ c: -5.7, w: 1.4, sill: 1.2, top: 2.2, kind: 'window' }] });
  W({ axis: 'x', at: Z0, from: -4.4, to: -1.8, level: 1, ext: true, left: 'white', openings: [{ c: -3.1, w: 1.4, sill: 1.0, top: 2.2, kind: 'window' }] });
  W({ axis: 'x', at: Z0, from: -1.8, to: 1.8, level: 1, ext: true, left: 'cream', openings: [{ c: 0.5, w: 1.4, sill: 1.0, top: 2.2, kind: 'window' }] });
  W({ axis: 'x', at: Z0, from: 1.8, to: X1, level: 1, ext: true, left: 'yellow', openings: [{ c: 4.4, w: 2.0, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  W({ axis: 'z', at: X0, from: Z0, to: -1.2, level: 1, ext: true, right: 'wallTile', noBaseboard: true, openings: [{ c: -3.0, w: 1.2, sill: 1.3, top: 2.2, kind: 'window' }] });
  W({ axis: 'z', at: X0, from: -1.2, to: Z1, level: 1, ext: true, right: 'bluegrey', openings: [{ c: 1.8, w: 2.4, sill: 0.9, top: 2.2, kind: 'window', curtain: 'blue' }] });
  W({ axis: 'z', at: X1, from: Z0, to: -0.6, level: 1, ext: true, left: 'yellow', openings: [{ c: -2.8, w: 1.6, sill: 0.9, top: 2.2, kind: 'window' }] });
  W({ axis: 'z', at: X1, from: -0.6, to: Z1, level: 1, ext: true, left: 'white', openings: [{ c: 2.2, w: 2.4, sill: 0.9, top: 2.2, kind: 'window', curtain: 'linen' }] });
  W({ axis: 'z', at: -1.8, from: Z0, to: -1.2, level: 1, left: 'white', right: 'cream', openings: [{ c: -3.25, w: 0.9, kind: 'door', hinge: 'lo', swing: 1 }] });
  W({ axis: 'z', at: -1.8, from: -1.2, to: Z1, level: 1, left: 'bluegrey', right: 'cream', openings: [{ c: 3.85, w: 0.9, kind: 'door', hinge: 'hi', swing: 1 }] });
  W({ axis: 'z', at: 1.8, from: Z0, to: -0.6, level: 1, left: 'cream', right: 'yellow', openings: [{ c: -1.95, w: 0.9, kind: 'door', hinge: 'lo', swing: -1 }] });
  W({ axis: 'z', at: 1.8, from: -0.6, to: Z1, level: 1, left: 'cream', right: 'white', openings: [{ c: 2.6, w: 2.0, top: 2.2, kind: 'open' }] });
  W({ axis: 'x', at: -1.2, from: X0, to: -4.4, level: 1, left: 'bluegrey', right: 'wallTile', openings: [{ c: -5.6, w: 0.9, kind: 'door', hinge: 'lo', swing: -1 }] });
  W({ axis: 'x', at: -1.2, from: -4.4, to: -1.8, level: 1, left: 'bluegrey', right: 'white' });
  W({ axis: 'z', at: -4.4, from: Z0, to: -1.2, level: 1, left: 'wallTile', right: 'white' });
  W({ axis: 'x', at: -0.6, from: 1.8, to: X1, level: 1, left: 'white', right: 'yellow' });

  buildStairs();
  buildRoof();
  buildExterior();
}

function buildStairs() {
  const g = group(floors[0], 0, 0, 0);
  g.name = 'STAIRCASE';
  const w = STAIR.x1 - STAIR.x0, cx = (STAIR.x0 + STAIR.x1) / 2;
  for (let i = 0; i < STAIR.treads; i++) {
    const zHi = STAIR.zBottom - i * STAIR.tread, zLo = zHi - STAIR.tread;
    const h = (i + 1) * STAIR.riser;
    // closed riser block (painted) + oak tread with nosing
    const blockMats = [M.trimPlaster, M.trimPlaster, M.trimPlaster, M.trimPlaster, M.trimPlaster, M.trimPlaster];
    const blk = new THREE.Mesh(boxGeo(w, h - 0.03, STAIR.tread), blockMats);
    blk.position.set(cx, (h - 0.03) / 2, (zHi + zLo) / 2);
    blk.castShadow = blk.receiveShadow = true;
    g.add(blk);
    register('STAIR_RISER', blk);
    box(g, w, 0.03, STAIR.tread + 0.03, M.oak, cx, h - 0.015, (zHi + zLo) / 2 + 0.015, 'STAIR_STEP');
  }
  // side stringer / rail on the open (east) side, newel + balusters + sloped handrail
  const slope = Math.atan2(STAIR.riser, STAIR.tread);
  const railLen = Math.hypot(STAIR.treads * STAIR.tread, STAIR.treads * STAIR.riser);
  const railMid = [STAIR.x1 - 0.03, (STAIR.treads * STAIR.riser) / 2 + 0.95, (STAIR.zBottom + STAIR.zTop) / 2];
  const rail = box(g, 0.05, 0.05, railLen + 0.3, M.oak, ...railMid, 'STAIR_HANDRAIL');
  rail.rotation.x = slope;
  for (let i = 0; i <= STAIR.treads; i += 1) {
    const z = STAIR.zBottom - (i + 0.5) * STAIR.tread;
    const yBase = Math.min(STAIR.treads, i + 1) * STAIR.riser;
    const yTop = (STAIR.treads * STAIR.riser) / 2 + 0.95 + Math.tan(slope) * (railMid[2] - z);
    const bh = Math.max(0.2, yTop - yBase - 0.025);
    box(g, 0.02, bh, 0.02, M.rail, STAIR.x1 - 0.03, yBase + bh / 2, z, 'STAIR_BALUSTER');
  }
  box(g, 0.09, 1.05, 0.09, M.oak, STAIR.x1 - 0.03, 0.525, STAIR.zBottom + 0.08, 'STAIR_NEWEL');
  // wall-side handrail on brackets
  const wr = box(g, 0.04, 0.05, railLen + 0.2, M.oak, STAIR.x0 + 0.06, railMid[1] - 0.05, railMid[2], 'STAIR_HANDRAIL');
  wr.rotation.x = slope;
  // colliders: east side of the stair (both floors) so you can only enter from bottom/top; the top end is
  // closed at ground level (the laundry-room door opens right next to it)
  colliderBox(STAIR.x1 - 0.06, STAIR.x1 + 0.01, STAIR.zTop - 0.02, STAIR.zBottom + 0.12, 2);
  colliderBox(STAIR.x0 - 0.02, STAIR.x1 + 0.01, STAIR.zTop - 0.08, STAIR.zTop + 0.02, 0);
  // upper-floor balustrade around the stairwell opening (east edge + south edge)
  const u = group(floors[1], 0, 0, 0);
  const postH = 0.95;
  const eastLen = STAIR.holeZ - STAIR.zTop;
  box(u, 0.05, 0.05, eastLen + 0.05, M.oak, STAIR.x1 + 0.02, postH, (STAIR.holeZ + STAIR.zTop) / 2, 'LANDING_HANDRAIL');
  for (let z = STAIR.zTop + 0.06; z < STAIR.holeZ; z += 0.13) box(u, 0.02, postH - 0.03, 0.02, M.rail, STAIR.x1 + 0.02, (postH - 0.03) / 2, z, 'LANDING_BALUSTER');
  const southLen = STAIR.x1 - STAIR.x0;
  box(u, southLen + 0.05, 0.05, 0.05, M.oak, (STAIR.x0 + STAIR.x1) / 2, postH, STAIR.holeZ + 0.02, 'LANDING_HANDRAIL');
  for (let x = STAIR.x0 + 0.08; x < STAIR.x1; x += 0.13) box(u, 0.02, postH - 0.03, 0.02, M.rail, x, (postH - 0.03) / 2, STAIR.holeZ + 0.02, 'LANDING_BALUSTER');
  box(u, 0.09, postH + 0.08, 0.09, M.oak, STAIR.x1 + 0.02, (postH + 0.08) / 2, STAIR.holeZ + 0.02, 'LANDING_NEWEL');
  box(u, 0.09, postH + 0.08, 0.09, M.oak, STAIR.x1 + 0.02, (postH + 0.08) / 2, STAIR.zTop - 0.02, 'LANDING_NEWEL');
  colliderBox(STAIR.x1 - 0.02, STAIR.x1 + 0.06, STAIR.zTop - 0.06, STAIR.holeZ + 0.06, 1);
  colliderBox(STAIR.x0 - 0.02, STAIR.x1 + 0.06, STAIR.holeZ - 0.02, STAIR.holeZ + 0.06, 1);
}

function buildRoof() {
  const g = group(exterior, 0, 0, 0);
  const eave = 0.55, rise = 2.6, half = (Z1 - Z0) / 2 + eave;   // 5.55
  const yEave = 2 * LEVEL_H;     // 6.0
  const slope = Math.atan2(rise, half);
  const len = Math.hypot(half, rise);
  const spanX = X1 - X0 + 2 * eave;
  for (const s of [1, -1]) {
    const m = new THREE.Mesh(boxGeo(spanX, 0.16, len + 0.1), M.roof);
    m.position.set(0, yEave + rise / 2 + 0.02, s * half / 2);
    m.rotation.x = -s * slope;
    m.castShadow = m.receiveShadow = true;
    g.add(m);
    register('ROOF', m);
    // eaves fascia board
    const f = box(g, spanX + 0.02, 0.2, 0.05, M.trim, 0, yEave - 0.05, s * (half + 0.02), 'FASCIA');
  }
  // gable end walls (triangles) and ridge cap
  for (const s of [1, -1]) {
    const shape = new THREE.Shape();
    shape.moveTo(-(Z1 - Z0) / 2, 0); shape.lineTo((Z1 - Z0) / 2, 0); shape.lineTo(0, rise + 0.05); shape.closePath();
    const geo = new THREE.ExtrudeGeometry(shape, { depth: 0.3, bevelEnabled: false });
    const uv = geo.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * 0.5, uv.getY(i) * 0.5);
    const gable = new THREE.Mesh(geo, M.brick);
    gable.rotation.y = PI / 2;
    gable.position.set(s * (X1 + 0.15) - (s > 0 ? 0.3 : 0), yEave - 0.02, 0);
    gable.castShadow = gable.receiveShadow = true;
    g.add(gable);
    register('GABLE', gable);
  }
  box(g, spanX + 0.02, 0.12, 0.34, M.cabinetGrey, 0, yEave + rise + 0.1, 0, 'RIDGE');
  // chimney
  box(g, 0.7, 2.4, 0.7, M.brick, 4.6, yEave + rise - 0.3, -2.2, 'CHIMNEY');
  // upper slab edge band and ground plinth (exterior)
  box(g, X1 - X0 + 0.3, 0.12, 0.05, M.cabinetGrey, 0, LEVEL_H - 0.06, Z1 + 0.16, 'BAND');
  box(g, X1 - X0 + 0.3, 0.12, 0.05, M.cabinetGrey, 0, LEVEL_H - 0.06, Z0 - 0.16, 'BAND');
  box(g, 0.05, 0.12, Z1 - Z0 + 0.3, M.cabinetGrey, X1 + 0.16, LEVEL_H - 0.06, 0, 'BAND');
  box(g, 0.05, 0.12, Z1 - Z0 + 0.3, M.cabinetGrey, X0 - 0.16, LEVEL_H - 0.06, 0, 'BAND');
}

function buildExterior() {
  const g = exterior;
  const ground = new THREE.Mesh(planeGeo(120, 120), M.grass);
  ground.rotation.x = -PI / 2;
  ground.position.y = -0.02;
  ground.receiveShadow = true;
  g.add(ground);
  register('GROUND', ground);
  // foundation plinth
  // top at -0.04: below the floor slabs (top 0) - a coplanar top face made the wooden floors z-fight (flicker)
  const plinth = box(g, X1 - X0 + 0.34, 0.21, Z1 - Z0 + 0.34, M.cabinetGrey, 0, -0.145, 0, 'PLINTH');
  // front path + step, back patio
  const path = new THREE.Mesh(planeGeo(1.6, 9), M.pavers);
  path.rotation.x = -PI / 2; path.position.set(0, 0.0, Z1 + 0.16 + 4.5); path.receiveShadow = true; g.add(path); register('PATH', path);
  box(g, 2.2, 0.16, 1.0, M.cabinetGrey, 0, -0.08, Z1 + 0.16 + 0.5, 'DOORSTEP');
  const patio = new THREE.Mesh(planeGeo(6, 3.5), M.pavers);
  patio.rotation.x = -PI / 2; patio.position.set(0.7, 0.0, Z0 - 0.16 - 1.75); patio.receiveShadow = true; g.add(patio); register('PATIO', patio);
  // simple hedges and lawn bushes so the windows look out on something
  const hedge = new THREE.MeshStandardMaterial({ color: 0x3f6b35, roughness: 1 });
  for (const [x, z, sx, sz] of [[-9.5, 0, 0.8, 12], [9.5, 0, 0.8, 12], [0, -9.5, 20, 0.8], [-5.5, 9.5, 8, 0.8], [5.5, 9.5, 8, 0.8]]) {
    rbox(g, sx, 1.1, sz, 0.2, hedge, x, 0.55, z, 'HEDGE');
  }
  for (const [x, z, r] of [[-8.3, 3.2, 0.7], [-8.1, -3.5, 0.55], [8.4, -2.4, 0.6], [8.2, 3.6, 0.75], [-3.2, 7.4, 0.5], [3.4, 7.6, 0.6], [-6.2, -7.2, 0.8], [5.8, -7.6, 0.7]]) {
    const b = new THREE.Mesh(new THREE.SphereGeometry(r, 18, 12), hedge);
    b.position.set(x, r * 0.75, z); b.scale.y = 0.8; b.castShadow = b.receiveShadow = true; g.add(b); register('BUSH', b);
  }
  // a couple of stylised trees far away (trunk + canopy) for the skyline
  const trunk = new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 1 });
  const canopy = new THREE.MeshStandardMaterial({ color: 0x4a7a3a, roughness: 1 });
  for (const [x, z, h] of [[-16, -12, 6], [17, -9, 7], [15, 12, 5.5], [-18, 10, 6.5], [-3, -18, 7], [8, 19, 6]]) {
    cyl(g, 0.2, 0.3, h * 0.45, trunk, x, h * 0.225, z, 10, 'TREE');
    for (const [dx, dy, dz, r] of [[0, 0, 0, 0.36], [0.28, -0.1, 0.1, 0.27], [-0.25, -0.05, -0.15, 0.29], [0.05, 0.22, -0.2, 0.24], [-0.1, -0.18, 0.25, 0.25]]) {
      const c = new THREE.Mesh(new THREE.SphereGeometry(h * r, 12, 9), canopy);
      c.position.set(x + dx * h, h * 0.62 + dy * h, z + dz * h); c.scale.set(1, 0.85, 1); c.castShadow = true; g.add(c);
    }
  }
}

// ---------------------------------------------------------------------------------------------
// Procedural furniture
// ---------------------------------------------------------------------------------------------
function placeGroup(g, { x, z, rot = 0, level = 0, y = 0, name, collide = true, pad = 0.02 }) {
  g.position.set(x, y, z);
  g.rotation.y = rot;
  floors[level].add(g);
  if (name) register(name, g);
  if (collide) addCollider(g, level, pad);
  return g;
}
function place(id, { x, z, rot = 0, level = 0, y = 0, name, collide = true, pad = 0.02, scale = 1 }) {
  const proto = protos[id];
  if (!proto) { console.warn('missing model', id); return null; }
  const obj = proto.clone();
  obj.scale.setScalar(scale);
  obj.position.set(x, y, z);
  obj.rotation.y = rot;
  floors[level].add(obj);
  register(name || id.toUpperCase(), obj);
  if (collide) addCollider(obj, level, pad);
  return obj;
}
const topOf = id => protos[id].userData.bbox.max.y;

function makeBed(w, l, single = false) {
  const g = new THREE.Group();
  const frameH = 0.28;
  box(g, w + 0.08, frameH, l + 0.06, M.oak, 0, frameH / 2, 0, 'BED_FRAME');
  rbox(g, w - 0.02, 0.22, l - 0.06, 0.05, M.linen, 0, frameH + 0.11, 0.0, 'MATTRESS');
  const duvet = rbox(g, w + 0.02, 0.14, l * 0.6, 0.05, M.denim, 0, frameH + 0.27, l * 0.18, 'DUVET');
  const pillows = single ? [0] : [-w / 4, w / 4];
  for (const px of pillows) {
    const p = rbox(g, single ? 0.62 : 0.6, 0.13, 0.4, 0.05, M.pillowWhite, px, frameH + 0.29, -l / 2 + 0.32, 'PILLOW');
    p.rotation.x = -0.15;
  }
  box(g, w + 0.08, 1.05, 0.06, M.oak, 0, 0.525, -l / 2 - 0.02, 'HEADBOARD');
  return g;
}
function makeTableLamp() {
  const g = new THREE.Group();
  cyl(g, 0.07, 0.09, 0.02, M.steel, 0, 0.01, 0, 20, 'LAMP_BASE');
  cyl(g, 0.012, 0.012, 0.34, M.steel, 0, 0.19, 0, 10);
  const shade = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.15, 0.2, 24, 1, true), M.shade);
  shade.position.y = 0.45; shade.castShadow = true; g.add(shade);
  const bulb = cyl(g, 0.02, 0.02, 0.04, M.bulb, 0, 0.4, 0, 10);
  bulb.castShadow = false;
  const light = new THREE.PointLight(0xffd9a6, 6, 4.5, 2);
  light.position.y = 0.42; g.add(light); lamps.push(light);
  register('TABLE_LAMP', g);
  return g;
}
function makeFloorLamp() {
  const g = new THREE.Group();
  cyl(g, 0.14, 0.16, 0.02, M.rail, 0, 0.01, 0, 24, 'LAMP_BASE');
  cyl(g, 0.014, 0.014, 1.45, M.rail, 0, 0.74, 0, 10);
  const shade = new THREE.Mesh(new THREE.CylinderGeometry(0.19, 0.22, 0.32, 28, 1, true), M.shade);
  shade.position.y = 1.55; shade.castShadow = true; g.add(shade);
  const bulb = cyl(g, 0.025, 0.025, 0.05, M.bulb, 0, 1.5, 0, 10);
  bulb.castShadow = false;
  const light = new THREE.PointLight(0xffd9a6, 10, 6, 2);
  light.position.y = 1.5; g.add(light); lamps.push(light);
  register('FLOOR_LAMP', g);
  return g;
}
function makeTV(width = 1.4) {
  const g = new THREE.Group();
  const h = width * 0.56;
  rbox(g, width, h, 0.035, 0.008, M.blackGloss, 0, 0.12 + h / 2, 0, 'TV');
  const screen = new THREE.Mesh(planeGeo(width - 0.03, h - 0.03), M.screen);
  screen.position.set(0, 0.12 + h / 2, 0.019); g.add(screen); register('TV_SCREEN', screen);
  box(g, width * 0.5, 0.02, 0.22, M.black, 0, 0.01, 0.0, 'TV_STAND');
  box(g, 0.08, 0.12, 0.04, M.black, 0, 0.07, 0, 'TV_STAND');
  return g;
}
function makeRug(w, l, mat) {
  const g = new THREE.Group();
  const r = new THREE.Mesh(new RoundedBoxGeometry(w, 0.014, l, 2, 0.006), mat);
  r.position.y = 0.007; r.receiveShadow = true; g.add(r);
  register('RUG', g);
  return g;
}
function makeWardrobe(w = 2.4, h = 2.3, d = 0.6) {
  const g = new THREE.Group();
  box(g, w, h, d, M.oak, 0, h / 2, 0, 'WARDROBE');
  // two sliding door panels on the front (+z)
  for (const [s, off] of [[-1, 0.012], [1, 0.03]]) {
    box(g, w / 2 - 0.01, h - 0.06, 0.02, s < 0 ? M.oakZ : M.cabinetGrey, s * w / 4, h / 2, d / 2 + off, 'WARDROBE_DOOR');
    box(g, 0.02, 0.9, 0.02, M.chrome, s * (w / 4) - s * (w / 4 - 0.08), h / 2, d / 2 + off + 0.015, 'WARDROBE_HANDLE');
  }
  box(g, w, 0.04, d + 0.06, M.oak, 0, h + 0.02, 0.0, 'WARDROBE_TOP');
  return g;
}
function makeDesk(w = 1.2, d = 0.6, h = 0.75) {
  const g = new THREE.Group();
  box(g, w, 0.035, d, M.oak, 0, h - 0.0175, 0, 'DESK');
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) cyl(g, 0.02, 0.02, h - 0.035, M.rail, sx * (w / 2 - 0.05), (h - 0.035) / 2, sz * (d / 2 - 0.05), 12, 'DESK_LEG');
  box(g, 0.42, 0.28, d - 0.08, M.oak, w / 2 - 0.24, h - 0.035 - 0.14, 0, 'DESK_DRAWER');
  return g;
}
function makeLaptop() {
  const g = new THREE.Group();
  rbox(g, 0.33, 0.018, 0.23, 0.005, M.cabinetGrey, 0, 0.009, 0, 'LAPTOP');
  const lid = new THREE.Group(); lid.position.set(0, 0.018, -0.115); lid.rotation.x = -1.85; g.add(lid);
  rbox(lid, 0.33, 0.21, 0.008, 0.004, M.cabinetGrey, 0, 0.105, 0);
  const scr = new THREE.Mesh(planeGeo(0.31, 0.19), new THREE.MeshStandardMaterial({ color: 0x1b2a3a, emissive: 0x2a4a6a, emissiveIntensity: 0.9, roughness: 0.3 }));
  scr.position.set(0, 0.105, 0.005); lid.add(scr);
  const kb = new THREE.Mesh(planeGeo(0.27, 0.1), M.black); kb.rotation.x = -PI / 2; kb.position.set(0, 0.0185, -0.02); g.add(kb);
  return g;
}
function makeBooks(n, width, height = 0.22) {
  const g = new THREE.Group();
  const colors = [0x8b3f3b, 0x355a72, 0xc08a3f, 0x4d704b, 0x7e5c8a, 0xd9cfb8, 0x2f3236, 0x9a6b4f];
  let x = -width / 2;
  const bw = width / n;
  for (let i = 0; i < n; i++) {
    const h = height * (0.75 + 0.25 * Math.abs(Math.sin(i * 1.7 + n)));
    const t = bw * 0.82;
    const b = box(g, t, h, 0.16 + 0.03 * Math.abs(Math.cos(i * 2.3)), new THREE.MeshStandardMaterial({ color: colors[(i * 3 + n) % colors.length], roughness: 0.85 }), x + bw / 2, h / 2, 0, 'BOOK');
    if (i % 5 === 3) b.rotation.z = 0.12;
    x += bw;
  }
  return g;
}
function makeWasher(dryer = false) {
  const g = new THREE.Group();
  rbox(g, 0.6, 0.85, 0.6, 0.01, M.appliance, 0, 0.425, 0, dryer ? 'DRYER' : 'WASHER');
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.025, 12, 32), M.plastic);
  ring.position.set(0, 0.4, 0.305); g.add(ring);
  const door = cyl(g, 0.15, 0.15, 0.02, M.blackGloss, 0, 0.4, 0.31, 32);
  door.rotation.x = PI / 2;
  box(g, 0.56, 0.1, 0.02, M.cabinetGrey, 0, 0.78, 0.305, 'WASHER_PANEL');
  cyl(g, 0.03, 0.03, 0.02, M.plastic, 0.2, 0.78, 0.318, 16).rotation.x = PI / 2;
  return g;
}
function makeToilet() {
  const g = new THREE.Group();
  const pts = [];
  for (let i = 0; i <= 10; i++) { const t = i / 10; pts.push(new THREE.Vector2(0.12 + 0.09 * Math.sin(t * PI * 0.9), t * 0.4)); }
  pts.push(new THREE.Vector2(0.19, 0.42), new THREE.Vector2(0.0, 0.42));
  const bowl = new THREE.Mesh(new THREE.LatheGeometry(pts, 32), M.ceramic);
  bowl.scale.z = 1.3; bowl.castShadow = bowl.receiveShadow = true; g.add(bowl);
  register('TOILET', g);
  rbox(g, 0.4, 0.4, 0.17, 0.02, M.ceramic, 0, 0.62, -0.28, 'TOILET_TANK');
  rbox(g, 0.42, 0.03, 0.19, 0.01, M.ceramic, 0, 0.835, -0.28);
  const seat = new THREE.Mesh(new THREE.TorusGeometry(0.155, 0.032, 10, 32), M.whiteGloss);
  seat.rotation.x = PI / 2; seat.scale.y = 1.3; seat.position.set(0, 0.44, 0.0); g.add(seat);
  const lid = new THREE.Mesh(new THREE.CylinderGeometry(0.19, 0.19, 0.02, 32), M.whiteGloss);
  lid.scale.z = 1.3; lid.position.set(0, 0.47, 0); g.add(lid);
  cyl(g, 0.02, 0.02, 0.06, M.chrome, 0.12, 0.855, -0.2, 12);
  return g;
}
function makeBathtub(L = 1.7, W = 0.75, H = 0.56) {
  const g = new THREE.Group();
  const outer = new THREE.Shape();
  const r = 0.12;
  outer.moveTo(-L / 2 + r, -W / 2); outer.lineTo(L / 2 - r, -W / 2); outer.quadraticCurveTo(L / 2, -W / 2, L / 2, -W / 2 + r);
  outer.lineTo(L / 2, W / 2 - r); outer.quadraticCurveTo(L / 2, W / 2, L / 2 - r, W / 2); outer.lineTo(-L / 2 + r, W / 2);
  outer.quadraticCurveTo(-L / 2, W / 2, -L / 2, W / 2 - r); outer.lineTo(-L / 2, -W / 2 + r); outer.quadraticCurveTo(-L / 2, -W / 2, -L / 2 + r, -W / 2);
  const hole = new THREE.Path();
  const l = L - 0.2, w = W - 0.2, rr = 0.16;
  hole.moveTo(-l / 2 + rr, -w / 2); hole.lineTo(l / 2 - rr, -w / 2); hole.quadraticCurveTo(l / 2, -w / 2, l / 2, -w / 2 + rr);
  hole.lineTo(l / 2, w / 2 - rr); hole.quadraticCurveTo(l / 2, w / 2, l / 2 - rr, w / 2); hole.lineTo(-l / 2 + rr, w / 2);
  hole.quadraticCurveTo(-l / 2, w / 2, -l / 2, w / 2 - rr); hole.lineTo(-l / 2, -w / 2 + rr); hole.quadraticCurveTo(-l / 2, -w / 2, -l / 2 + rr, -w / 2);
  outer.holes.push(hole);
  const shell = new THREE.Mesh(new THREE.ExtrudeGeometry(outer, { depth: H - 0.12, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.02, bevelSegments: 3 }), M.ceramic);
  shell.rotation.x = -PI / 2; shell.position.y = 0.12; shell.castShadow = shell.receiveShadow = true; g.add(shell);
  register('BATHTUB', g);
  rbox(g, L, 0.12, W, 0.02, M.ceramic, 0, 0.06, 0);
  box(g, l, 0.02, w, M.ceramic, 0, 0.13, 0);
  // taps
  cyl(g, 0.02, 0.02, 0.16, M.chrome, L / 2 - 0.14, H + 0.02, -0.1, 12);
  cyl(g, 0.02, 0.02, 0.16, M.chrome, L / 2 - 0.14, H + 0.02, 0.1, 12);
  const spout = cyl(g, 0.016, 0.016, 0.18, M.chrome, L / 2 - 0.2, H + 0.06, 0, 12);
  spout.rotation.z = PI / 2;
  return g;
}
function makeVanity(w = 0.8) {
  const g = new THREE.Group();
  box(g, w, 0.68, 0.46, M.cabinet, 0, 0.44, 0, 'VANITY');
  box(g, w - 0.08, 0.1, 0.4, M.cabinetGrey, 0, 0.05, -0.02);
  box(g, w + 0.04, 0.03, 0.5, M.marble, 0, 0.795, 0.02, 'VANITY_TOP');
  for (const s of [-1, 1]) box(g, 0.02, 0.25, 0.02, M.chrome, s * 0.1, 0.5, 0.235, 'VANITY_HANDLE');
  const pts = [];
  for (let i = 0; i <= 8; i++) { const t = i / 8; pts.push(new THREE.Vector2(0.06 + 0.15 * Math.sqrt(t), 0.66 + t * 0.14)); }
  pts.push(new THREE.Vector2(0.22, 0.815), new THREE.Vector2(0.0, 0.815));
  const basin = new THREE.Mesh(new THREE.LatheGeometry(pts, 32), M.ceramic);
  basin.scale.z = 0.8; basin.castShadow = basin.receiveShadow = true; g.add(basin); register('BASIN', basin);
  cyl(g, 0.016, 0.02, 0.16, M.chrome, 0, 0.89, -0.17, 12);
  const sp = cyl(g, 0.012, 0.012, 0.14, M.chrome, 0, 0.965, -0.1, 12); sp.rotation.x = PI / 2;
  // mirror on the wall behind
  box(g, w - 0.1, 0.9, 0.02, M.trim, 0, 1.6, -0.24, 'MIRROR_FRAME');
  const mir = new THREE.Mesh(planeGeo(w - 0.16, 0.84), M.mirror); mir.position.set(0, 1.6, -0.228); g.add(mir); register('MIRROR', mir);
  return g;
}
function makeShower() {
  const g = new THREE.Group();
  box(g, 0.9, 0.06, 0.9, M.ceramic, 0, 0.03, 0, 'SHOWER_TRAY');
  const gl1 = box(g, 0.02, 1.95, 0.9, M.glass, 0.45, 1.04, 0, 'SHOWER_GLASS');
  const gl2 = box(g, 0.9, 1.95, 0.02, M.glass, 0, 1.04, 0.45, 'SHOWER_GLASS');
  gl1.castShadow = gl2.castShadow = false;
  box(g, 0.03, 2.0, 0.03, M.chrome, 0.45, 1.06, 0.45, 'SHOWER_FRAME');
  box(g, 0.03, 0.03, 0.92, M.chrome, 0.45, 2.05, 0, 'SHOWER_FRAME');
  box(g, 0.92, 0.03, 0.03, M.chrome, 0, 2.05, 0.45, 'SHOWER_FRAME');
  cyl(g, 0.012, 0.012, 1.0, M.chrome, -0.44, 1.5, -0.44, 10);
  const arm = cyl(g, 0.012, 0.012, 0.35, M.chrome, -0.3, 2.05, -0.3, 10); arm.rotation.z = PI / 2; arm.rotation.y = PI / 4;
  const head = cyl(g, 0.1, 0.1, 0.02, M.chrome, -0.2, 2.03, -0.2, 24); register('SHOWER_HEAD', head);
  cyl(g, 0.035, 0.035, 0.04, M.chrome, -0.44, 1.1, -0.44, 16).rotation.z = PI / 2;
  return g;
}
function makeTowelRail(mat = M.towel) {
  const g = new THREE.Group();
  const rail = cyl(g, 0.012, 0.012, 0.6, M.chrome, 0, 1.0, 0.06, 10, 'TOWEL_RAIL'); rail.rotation.z = PI / 2;
  for (const s of [-1, 1]) { const b = cyl(g, 0.012, 0.012, 0.06, M.chrome, s * 0.28, 1.0, 0.03, 10); b.rotation.x = PI / 2; }
  rbox(g, 0.4, 0.5, 0.04, 0.01, mat, 0, 0.77, 0.09, 'TOWEL');
  return g;
}
function makeKitchenRun(len, opts = {}) {
  // base cabinets along +x, doors facing +z; origin at the centre of the run at floor level
  const g = new THREE.Group();
  const d = 0.6, h = 0.86;
  box(g, len, h, d, M.cabinet, 0, h / 2 + 0.02, 0, 'KITCHEN_CABINET');
  box(g, len, 0.1, d - 0.08, M.cabinetGrey, 0, 0.05, -0.04);
  const n = Math.max(1, Math.round(len / 0.6));
  const dw = len / n;
  for (let i = 0; i < n; i++) {
    const cx = -len / 2 + (i + 0.5) * dw;
    box(g, dw - 0.02, h - 0.12, 0.018, M.cabinet, cx, h / 2 + 0.06, d / 2 + 0.01, 'CABINET_DOOR');
    box(g, 0.14, 0.012, 0.012, M.chrome, cx, h - 0.1, d / 2 + 0.028, 'CABINET_HANDLE');
  }
  box(g, len + 0.02, 0.04, d + 0.03, M.marble, 0, h + 0.04, 0.015, 'COUNTERTOP');
  if (opts.upper) {
    const uh = 0.72, ud = 0.34;
    box(g, len, uh, ud, M.cabinet, 0, 1.5 + uh / 2, -d / 2 + ud / 2, 'UPPER_CABINET');
    for (let i = 0; i < n; i++) {
      const cx = -len / 2 + (i + 0.5) * dw;
      box(g, dw - 0.02, uh - 0.04, 0.018, M.cabinet, cx, 1.5 + uh / 2, -d / 2 + ud + 0.01, 'CABINET_DOOR');
      box(g, 0.012, 0.14, 0.012, M.chrome, cx + dw / 2 - 0.05, 1.5 + 0.12, -d / 2 + ud + 0.028, 'CABINET_HANDLE');
    }
  }
  if (opts.backsplash) box(g, len, 0.6, 0.012, M.wallTile, 0, 1.2, -d / 2 + 0.006, 'BACKSPLASH');
  if (opts.sink !== undefined) {
    const sx = opts.sink;
    rbox(g, 0.56, 0.02, 0.42, 0.01, M.steel, sx, h + 0.065, 0.0, 'SINK');
    rbox(g, 0.5, 0.17, 0.36, 0.02, M.steel, sx, h + 0.0, 0.0);
    const bowl = new THREE.Mesh(new RoundedBoxGeometry(0.46, 0.15, 0.32, 2, 0.02), new THREE.MeshStandardMaterial({ color: 0x3a3d40, metalness: 0.9, roughness: 0.4 }));
    bowl.position.set(sx, h + 0.0, 0); g.add(bowl);
    cyl(g, 0.018, 0.022, 0.3, M.chrome, sx, h + 0.2, -0.22, 12, 'TAP');
    const sp = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.012, 10, 20, PI), M.chrome);
    sp.position.set(sx, h + 0.36, -0.12); sp.rotation.y = PI / 2; g.add(sp);
  }
  return g;
}
function makeFridge() {
  const g = new THREE.Group();
  rbox(g, 0.9, 1.82, 0.7, 0.02, M.steel, 0, 0.93, 0, 'FRIDGE');
  box(g, 0.86, 0.012, 0.01, M.black, 0, 1.18, 0.351, 'FRIDGE_SEAM');
  box(g, 0.03, 0.5, 0.03, M.chrome, -0.36, 1.5, 0.37, 'FRIDGE_HANDLE');
  box(g, 0.03, 0.8, 0.03, M.chrome, -0.36, 0.7, 0.37, 'FRIDGE_HANDLE');
  return g;
}
function makeHood() {
  const g = new THREE.Group();
  box(g, 0.6, 0.12, 0.48, M.steel, 0, 0.06, 0, 'RANGE_HOOD');
  box(g, 0.28, 0.6, 0.28, M.steel, 0, 0.42, -0.1, 'RANGE_HOOD');
  const l = new THREE.PointLight(0xffe6c4, 2.5, 2.5, 2); l.position.set(0, -0.02, 0.05); g.add(l);
  return g;
}
function makeIsland(w = 2.0, d = 0.9) {
  const g = new THREE.Group();
  box(g, w, 0.86, d, M.darkwood, 0, 0.45, 0, 'KITCHEN_ISLAND');
  box(g, w + 0.1, 0.04, d + 0.4, M.marble, 0, 0.9, 0.15, 'COUNTERTOP');
  for (let i = 0; i < 3; i++) box(g, w / 3 - 0.03, 0.72, 0.016, M.darkwood, -w / 3 + i * w / 3, 0.47, -d / 2 - 0.01, 'CABINET_DOOR');
  return g;
}
function makeDownlight(parent, x, y, z, level, opts = {}) {
  const ring = cyl(parent, 0.055, 0.055, 0.012, M.trim, x, y - 0.006, z, 20, 'DOWNLIGHT');
  const disc = cyl(parent, 0.04, 0.04, 0.006, M.downlight, x, y - 0.012, z, 20);
  disc.castShadow = false;
  const s = new THREE.SpotLight(0xfff1dc, opts.intensity ?? 28, opts.distance ?? 9, opts.angle ?? 1.15, 0.65, 2);
  s.position.set(x, y - 0.02, z);
  s.target.position.set(x, y - 3, z);
  parent.add(s, s.target);
  if (opts.shadow) { s.castShadow = true; s.shadow.mapSize.set(768, 768); s.shadow.bias = -0.0004; s.shadow.normalBias = 0.02; s.shadow.camera.near = 0.2; s.shadow.camera.far = 8; }
  return s;
}
function makePendant(id, x, z, level, opts = {}) {
  const proto = protos[id];
  const bb = proto.userData.bbox;
  const o = place(id, { x, z, level, y: CEIL - bb.max.y - 0.01, name: 'CEILING_LAMP', collide: false });
  o.traverse(m => { if (m.isMesh) m.castShadow = false; });   // a fixture must not cast a disc of shadow under itself
  const l = new THREE.PointLight(0xffe4bd, opts.intensity ?? 18, opts.distance ?? 9, 2);
  l.position.set(x, CEIL - bb.max.y + bb.min.y + (opts.lightY ?? 0.35), z);
  floors[level].add(l);
  if (opts.shadow) { l.castShadow = true; l.shadow.mapSize.set(512, 512); l.shadow.bias = -0.002; }
  return o;
}
function makeSocket(parent, x, y, z, rot) {
  const s = box(parent, 0.085, 0.085, 0.012, M.trim, x, y, z, 'LIGHT_SWITCH');
  s.rotation.y = rot;
  return s;
}
function makePicture(id, { x, z, y = 1.55, rot = 0, level = 0 }) {
  // picture frames hang flat on a wall: model faces +z, so rot maps the wall normal
  const proto = protos[id];
  const bb = proto.userData.bbox;
  const obj = proto.clone();
  obj.position.set(x, y - (bb.max.y + bb.min.y) / 2, z);
  obj.rotation.y = rot;
  floors[level].add(obj);
  register('PICTURE', obj);
  return obj;
}
function hangOnWall(id, { x, z, y, rot, level = 0, name }) {
  const obj = protos[id].clone();
  const bb = protos[id].userData.bbox;
  obj.position.set(x, y - (bb.max.y + bb.min.y) / 2, z);
  obj.rotation.y = rot;
  floors[level].add(obj);
  register(name || id.toUpperCase(), obj);
  return obj;
}

// ---------------------------------------------------------------------------------------------
// Furnishing plan
// ---------------------------------------------------------------------------------------------
function furnish() {
  const F0 = floors[0], F1 = floors[1];
  const SOUTH = 0, NORTH = PI, EAST = PI / 2, WEST = -PI / 2;   // rotation so the model front faces that way

  // ===== living room (x -6.85..-1.86, z -1.14..4.85)
  const tvTop = topOf('modern_wooden_cabinet');
  place('modern_wooden_cabinet', { x: -3.2, z: -0.86, rot: SOUTH, name: 'TV_CONSOLE' });
  placeGroup(makeTV(1.45), { x: -3.2, z: -0.9, y: tvTop, rot: SOUTH, name: 'TV', collide: false });
  place('ceramic_vase_02', { x: -2.25, z: -0.86, y: tvTop, collide: false });
  place('standing_picture_frame_01', { x: -4.1, z: -0.84, y: tvTop, rot: 0.2, collide: false });
  place('sofa_02', { x: -3.2, z: 2.35, rot: NORTH, name: 'SOFA' });
  place('throw_pillows_01', { x: -3.2, z: 2.4, y: 0.39, rot: NORTH, name: 'PILLOW', collide: false, scale: 0.75 });   // seat cushion top ~0.40
  place('modern_coffee_table_01', { x: -3.2, z: 0.55, rot: 0, name: 'COFFEE_TABLE' });
  placeGroup(makeRug(2.8, 2.2, M.rugRed), { x: -3.2, z: 0.9, name: 'RUG', collide: false });
  // layout keeps every passage >= 0.6 m for a 0.22 m player radius (walkability check in README)
  place('modern_arm_chair_01', { x: -6.1, z: 0.9, rot: EAST - 0.2, name: 'ARMCHAIR' });
  place('modern_arm_chair_01', { x: -6.1, z: 2.6, rot: EAST + 0.3, name: 'ARMCHAIR' });
  place('Ottoman_01', { x: -5.2, z: 0.9, rot: EAST, name: 'OTTOMAN' });   // footstool of the first armchair
  const st = topOf('side_table_01');
  place('side_table_01', { x: -4.62, z: 2.35, name: 'SIDE_TABLE' });   // at the sofa's west end, in line with it
  placeGroup(makeTableLamp(), { x: -4.62, z: 2.35, y: st, name: 'TABLE_LAMP', collide: false });
  placeGroup(makeFloorLamp(), { x: -6.45, z: -0.75, name: 'FLOOR_LAMP' });
  place('potted_plant_02', { x: -6.35, z: 4.4, name: 'PLANT' });
  makePicture('fancy_picture_frame_01', { x: -6.85 + 0.02, z: -0.3, y: 1.6, rot: EAST });
  makePicture('hanging_picture_frame_02', { x: -2.5, z: 4.85 - 0.02, y: 1.6, rot: NORTH });
  hangOnWall('wall_clock', { x: -1.86 - 0.02, z: 0.6, y: 1.95, rot: WEST, name: 'CLOCK' });
  makePendant('modern_ceiling_lamp_01', -3.6, 1.6, 0, { intensity: 16 });
  makeSocket(F0, -1.86 - 0.006, 1.15, 2.55, WEST);

  // ===== hall (x -1.74..1.74, z -4.85..4.85)
  place('side_table_01', { x: 1.42, z: 4.35, name: 'CONSOLE_TABLE' });
  place('potted_plant_04', { x: 1.42, z: 4.35, y: st, name: 'PLANT', collide: false });
  placeGroup(makeRug(0.8, 2.6, M.rugGrey), { x: 0.55, z: 2.2, collide: false });
  makePicture('hanging_picture_frame_01', { x: 1.74 - 0.02, z: 0.3, y: 1.6, rot: WEST });
  makeSocket(F0, 1.74 - 0.006, 1.15, 4.7, WEST);

  // ===== study (x -6.85..-4.26, z -4.85..-1.26)
  const deskTop = topOf('metal_office_desk');
  place('metal_office_desk', { x: -5.55, z: -4.28, rot: SOUTH, name: 'DESK' });
  place('mid_century_lounge_chair', { x: -5.55, z: -3.35, rot: NORTH, name: 'OFFICE_CHAIR' });
  place('desk_lamp_arm_01', { x: -4.85, z: -4.45, y: deskTop, rot: -0.6, collide: false, name: 'DESK_LAMP' });
  placeGroup(makeLaptop(), { x: -5.65, z: -4.35, y: deskTop, rot: NORTH + 0.1, collide: false, name: 'LAPTOP' });
  place('steel_frame_shelves_01', { x: -4.26 - 0.27, z: -2.55, rot: WEST, name: 'BOOKSHELF' });   // clear of the door swing
  {
    const sh = protos['steel_frame_shelves_01'].userData.bbox;
    const levels = [0.36, 0.83, 1.3, 1.77];
    levels.forEach((ly, i) => placeGroup(makeBooks(7 + i, 0.8, 0.24), { x: -4.26 - 0.27, z: -2.55, y: ly, rot: WEST, collide: false }));
  }
  placeGroup(makeRug(1.8, 1.5, M.rugGrey), { x: -5.55, z: -3.0, collide: false });
  makePicture('hanging_picture_frame_03', { x: -4.26 - 0.02, z: -3.85, y: 1.6, rot: WEST });
  hangOnWall('wall_clock', { x: -6.1, z: -1.26 - 0.02, y: 1.95, rot: NORTH, name: 'CLOCK' });
  makePendant('modern_ceiling_lamp_01', -5.55, -3.05, 0, { intensity: 14 });

  // ===== bathroom, ground (x -4.14..-1.86, z -4.85..-2.66)
  placeGroup(makeToilet(), { x: -3.0, z: -4.85 + 0.36, rot: SOUTH, name: 'TOILET' });
  placeGroup(makeVanity(0.7), { x: -3.77, z: -4.85 + 0.25, rot: SOUTH, name: 'VANITY' });
  placeGroup(makeShower(), { x: -4.14 + 0.46, z: -2.66 - 0.46, rot: 0, name: 'SHOWER' });
  placeGroup(makeTowelRail(M.towelBlue), { x: -1.86 - 0.005, z: -3.0, rot: WEST, name: 'TOWEL_RAIL', collide: false });
  placeGroup(makeRug(0.6, 0.4, M.towel), { x: -3.0, z: -3.7, collide: false, name: 'BATH_MAT' });

  // ===== laundry (x -4.14..-1.86, z -2.54..-1.26)
  placeGroup(makeWasher(false), { x: -3.72, z: -2.54 + 0.32, rot: SOUTH, name: 'WASHER' });
  placeGroup(makeWasher(true), { x: -3.08, z: -2.54 + 0.32, rot: SOUTH, name: 'DRYER' });
  box(F0, 1.4, 0.03, 0.28, M.oak, -3.4, 1.55, -2.54 + 0.14, 'WALL_SHELF');
  [[-3.9, 0xe8e2c8, 0.07, 0.26], [-3.72, 0x4f86c0, 0.06, 0.22], [-3.55, 0xd94b3c, 0.055, 0.2], [-3.2, 0xf2f2ee, 0.09, 0.3], [-2.98, 0x7fb069, 0.05, 0.18]].forEach(([x, c, r, h]) => {
    const bottle = cyl(F0, r, r * 0.9, h, new THREE.MeshStandardMaterial({ color: c, roughness: 0.5 }), x, 1.565 + h / 2, -2.54 + 0.14, 16, 'BOTTLE');
    cyl(F0, r * 0.45, r * 0.45, 0.03, M.plastic, x, 1.565 + h + 0.015, -2.54 + 0.14, 12);
  });
  placeGroup(makeRug(1.0, 0.6, M.rugGrey), { x: -3.0, z: -1.7, collide: false });

  // ===== kitchen (x 1.86..6.85, z -4.85..-0.6)
  placeGroup(makeKitchenRun(3.85, { upper: false, backsplash: true, sink: 0.55 }), { x: 1.86 + 3.85 / 2, z: -4.85 + 0.3, rot: 0, name: 'KITCHEN_COUNTER' });
  // upper cabinets either side of the window (window x 3.4..5.4)
  placeGroup(makeKitchenRun(1.5, { upper: true }), { x: 2.61, z: -4.85 + 0.3, name: 'KITCHEN_COUNTER', collide: false }).children.forEach(c => { if (c.position.y < 1.4) c.visible = false; });
  placeGroup(makeKitchenRun(0.9, { upper: true }), { x: 6.85 - 0.45, z: -4.85 + 0.3, name: 'KITCHEN_COUNTER', collide: false }).children.forEach(c => { if (c.position.y < 1.4) c.visible = false; });
  place('electric_stove', { x: 5.98, z: -4.85 + 0.33, rot: SOUTH, name: 'STOVE' });
  placeGroup(makeKitchenRun(0.6, { backsplash: true }), { x: 6.85 - 0.3, z: -4.85 + 0.3, name: 'KITCHEN_COUNTER' });
  placeGroup(makeHood(), { x: 5.98, z: -4.85 + 0.33, y: 1.62, name: 'RANGE_HOOD', collide: false });
  placeGroup(makeFridge(), { x: 1.86 + 0.37, z: -1.35, rot: EAST, name: 'FRIDGE' });
  placeGroup(makeIsland(2.0, 0.9), { x: 4.4, z: -2.6, name: 'KITCHEN_ISLAND' });
  for (const x of [3.7, 4.4, 5.1]) place('bar_chair_round_01', { x, z: -1.75, rot: NORTH, name: 'BAR_STOOL' });
  place('wooden_cutting_board', { x: 3.75, z: -2.75, y: 0.92, rot: 0.3, collide: false });
  place('food_apple_01', { x: 4.55, z: -2.7, y: 0.92, collide: false, name: 'APPLE' });
  place('food_apple_01', { x: 4.68, z: -2.85, y: 0.92, rot: 1.2, collide: false, name: 'APPLE' });
  // the lower cabinets under the kitchen window are hidden (upper cabinets only), so props at counter height
  // there would float: the bottles go on the island's east end, the vase on the short counter by the stove
  place('wine_bottles_01', { x: 4.72, z: -2.45, y: 0.92, rot: 0, collide: false });   // model origin is at one end of the 0.68 m row
  place('ceramic_vase_02', { x: 6.6, z: -4.55, y: 0.92, collide: false });
  makePendant('modern_ceiling_lamp_01', 3.9, -2.6, 0, { intensity: 12, distance: 6 });
  makePendant('modern_ceiling_lamp_01', 4.9, -2.6, 0, { intensity: 12, distance: 6 });
  makeSocket(F0, 1.86 + 0.006, 1.15, -2.2, EAST);

  // ===== dining (x 1.86..6.85, z -0.6..4.85)
  const tableTop = topOf('round_wooden_table_01');
  place('round_wooden_table_01', { x: 4.4, z: 2.2, name: 'DINING_TABLE' });
  for (let i = 0; i < 4; i++) {
    const a = i * PI / 2 + PI / 4;
    const cx = 4.4 + Math.sin(a) * 1.0, cz = 2.2 + Math.cos(a) * 1.0;
    place('dining_chair_02', { x: cx, z: cz, rot: a + PI, name: 'DINING_CHAIR' });
  }
  place('ceramic_vase_02', { x: 4.4, z: 2.2, y: tableTop, collide: false, scale: 0.9 });
  place('wooden_display_shelves_01', { x: 6.85 - 0.2, z: 4.25, rot: WEST, name: 'SIDEBOARD' });
  // the row is 0.68 m long from its origin along local +x; the sideboard (rot WEST) runs along world x from 6.11 to 7.19
  // and is only 0.38 m deep, so the row must run along x too and start 0.34 m west of the sideboard's centre
  place('wine_bottles_01', { x: 6.65 - 0.34, z: 4.25, y: topOf('wooden_display_shelves_01'), rot: 0, collide: false });
  placeGroup(makeRug(2.9, 2.9, M.rugGrey), { x: 4.4, z: 2.2, collide: false });
  makePendant('Chandelier_01', 4.4, 2.2, 0, { intensity: 22, lightY: 0.2 });
  makePicture('hanging_picture_frame_02', { x: 1.86 + 0.02, z: 0.8, y: 1.6, rot: EAST });

  // ===== master bedroom (level 1; x -6.85..-1.86, z -1.14..4.85)
  placeGroup(makeBed(1.6, 2.0), { x: -3.25, z: -1.14 + 0.06 + 1.03, level: 1, name: 'BED' });
  place('throw_pillows_01', { x: -3.25, z: -0.5, y: 0.5, level: 1, rot: SOUTH, name: 'PILLOW', collide: false, scale: 0.7 });
  for (const x of [-4.37, -2.13]) {
    place('side_table_01', { x, z: -0.8, level: 1, name: 'NIGHTSTAND' });
    placeGroup(makeTableLamp(), { x, z: -0.8, y: st, level: 1, collide: false });
  }
  place('alarm_clock_01', { x: -2.0, z: -0.95, y: st, level: 1, rot: 0.3, collide: false, name: 'ALARM_CLOCK' });
  place('drawer_cabinet', { x: -1.86 - 0.27, z: 2.0, rot: WEST, level: 1, name: 'DRESSER' });
  place('Ottoman_01', { x: -3.25, z: 1.6, rot: EAST, level: 1, name: 'BENCH' });
  place('modern_arm_chair_01', { x: -5.9, z: 3.9, rot: EAST - 0.7, level: 1, name: 'ARMCHAIR' });
  place('potted_plant_02', { x: -6.35, z: -0.7, level: 1, name: 'PLANT' });
  placeGroup(makeRug(3.0, 3.2, M.rugBlue), { x: -3.25, z: 0.9, level: 1, collide: false });
  makePicture('hanging_picture_frame_01', { x: -3.25, z: -1.14 + 0.02, y: 1.85, rot: SOUTH, level: 1 });
  hangOnWall('ornate_mirror_01', { x: -1.86 - 0.02, z: 0.6, y: 1.5, rot: WEST, level: 1, name: 'MIRROR' });   // clear wall between nightstand and dresser (z 3.6 was the door opening)
  makePendant('modern_ceiling_lamp_01', -3.6, 1.9, 1, { intensity: 14 });
  makeSocket(F1, -1.86 - 0.006, 1.15, 3.2, WEST);

  // ===== en-suite (level 1; x -6.85..-4.46, z -4.85..-1.26)
  placeGroup(makeBathtub(1.7, 0.75), { x: -6.85 + 0.4, z: -3.2, rot: PI / 2, level: 1, name: 'BATHTUB' });
  placeGroup(makeToilet(), { x: -5.15, z: -4.85 + 0.36, rot: SOUTH, level: 1, name: 'TOILET' });
  placeGroup(makeVanity(0.9), { x: -4.46 - 0.25, z: -2.3, rot: WEST, level: 1, name: 'VANITY' });
  placeGroup(makeTowelRail(M.towel), { x: -4.82, z: -1.26 - 0.005, rot: NORTH, level: 1, collide: false, name: 'TOWEL_RAIL' });   // solid wall east of the door (x -5.7 was the door opening)
  placeGroup(makeRug(0.7, 0.45, M.towel), { x: -5.6, z: -3.2, level: 1, collide: false, name: 'BATH_MAT' });

  // ===== dressing room (level 1; x -4.34..-1.86, z -4.85..-1.26)
  placeGroup(makeWardrobe(2.4, 2.3, 0.6), { x: -4.34 + 0.31, z: -3.05, rot: EAST, level: 1, name: 'WARDROBE' });
  place('Shelf_01', { x: -1.86 - 0.14, z: -2.1, rot: WEST, level: 1, name: 'SHELF' });
  place('Ottoman_01', { x: -2.9, z: -4.45, level: 1, name: 'BENCH' });   // against the south wall (mid-room blocked the walkway)
  hangOnWall('ornate_mirror_01', { x: -3.0, z: -1.26 - 0.02, y: 1.5, rot: NORTH, level: 1, name: 'MIRROR' });
  placeGroup(makeRug(1.4, 1.0, M.rugGrey), { x: -3.0, z: -3.0, level: 1, collide: false });

  // ===== kids room (level 1; x 1.86..6.85, z -4.85..-0.66)
  placeGroup(makeBed(0.95, 2.0, true), { x: 6.85 - 0.06 - 0.5, z: -4.85 + 0.06 + 1.03, level: 1, name: 'BED' });
  placeGroup(makeDesk(1.2, 0.6, 0.75), { x: 4.0, z: -4.85 + 0.33, level: 1, name: 'DESK' });
  place('dining_chair_02', { x: 4.0, z: -3.8, rot: NORTH, level: 1, name: 'CHAIR' });
  place('alarm_clock_01', { x: 3.5, z: -4.6, y: 0.75, level: 1, rot: 0.2, collide: false, name: 'ALARM_CLOCK' });
  place('potted_plant_04', { x: 4.5, z: -4.6, y: 0.75, level: 1, collide: false, name: 'PLANT' });
  place('standing_picture_frame_01', { x: 3.85, z: -4.65, y: 0.75, level: 1, rot: -0.3, collide: false });
  place('Shelf_01', { x: 3.1, z: -0.66 - 0.14, rot: NORTH, level: 1, name: 'SHELF' });
  [0.36, 0.78, 1.2].forEach((ly, i) => placeGroup(makeBooks(5 + i, 0.72, 0.2), { x: 3.1, z: -0.66 - 0.16, y: ly, rot: NORTH, level: 1, collide: false }));
  placeGroup(makeRug(2.0, 1.6, M.rugBlue), { x: 4.1, z: -2.3, level: 1, collide: false });
  makePicture('hanging_picture_frame_01', { x: 1.86 + 0.02, z: -3.6, y: 1.6, rot: EAST, level: 1 });
  makePendant('modern_ceiling_lamp_01', 4.4, -2.75, 1, { intensity: 14 });

  // ===== lounge (level 1; x 1.86..6.85, z -0.54..4.85)
  place('sofa_03', { x: 4.4, z: -0.54 + 0.5, rot: SOUTH, level: 1, name: 'SOFA' });
  place('coffee_table_round_01', { x: 4.4, z: 1.55, level: 1, name: 'COFFEE_TABLE' });
  place('mid_century_lounge_chair', { x: 6.05, z: 1.2, rot: WEST - 0.5, level: 1, name: 'ARMCHAIR' });
  placeGroup(makeFloorLamp(), { x: 6.45, z: 0.0, level: 1, name: 'FLOOR_LAMP' });
  place('potted_plant_02', { x: 2.35, z: 4.35, level: 1, name: 'PLANT' });
  place('steel_frame_shelves_01', { x: 6.85 - 0.27, z: 4.2, rot: WEST, level: 1, name: 'BOOKSHELF' });
  [0.36, 0.83, 1.3, 1.77].forEach((ly, i) => placeGroup(makeBooks(6 + (i % 3), 0.8, 0.24), { x: 6.85 - 0.27, z: 4.2, y: ly, rot: WEST, level: 1, collide: false }));
  place('ceramic_vase_02', { x: 4.4, z: 1.55, y: topOf('coffee_table_round_01'), level: 1, collide: false, scale: 0.8 });
  placeGroup(makeRug(3.2, 2.4, M.rugRed), { x: 4.4, z: 1.4, level: 1, collide: false });
  makePicture('fancy_picture_frame_01', { x: 1.86 + 0.02, z: 0.4, y: 1.6, rot: EAST, level: 1 });
  hangOnWall('wall_clock', { x: 4.4, z: 4.85 - 0.02, y: 2.0, rot: NORTH, level: 1, name: 'CLOCK' });
  place('ceiling_fan', { x: 4.4, z: 2.15, y: CEIL - protos['ceiling_fan'].userData.bbox.max.y - 0.01, level: 1, name: 'CEILING_FAN', collide: false });
  {
    const l = new THREE.PointLight(0xffe4bd, 14, 9, 2); l.position.set(4.4, CEIL - 0.45, 2.15); F1.add(l);
  }

  // ===== landing (level 1)
  place('side_table_01', { x: 1.3, z: 4.35, level: 1, name: 'CONSOLE_TABLE' });
  place('potted_plant_04', { x: 1.3, z: 4.35, y: st, level: 1, collide: false, name: 'PLANT' });
  placeGroup(makeRug(0.8, 2.4, M.rugGrey), { x: 0.6, z: -2.0, level: 1, collide: false });
  makePicture('hanging_picture_frame_03', { x: 1.74 - 0.02, z: -3.9, y: 1.6, rot: WEST, level: 1 });

  // ===== ceiling downlights (rooms without pendant) and room spot lights
  for (const r of ROOMS) {
    const parent = floors[r.level];
    r.light.forEach(([lx, lz], i) => makeDownlight(parent, lx, CEIL, lz, r.level, { shadow: !!r.shadow && i === 0, intensity: r.down ? 22 : 26 }));
  }
}

// ---------------------------------------------------------------------------------------------
// Lighting / environment
// ---------------------------------------------------------------------------------------------
async function buildEnvironment() {
  const hdr = await new RGBELoader().loadAsync(`${BASE}/hdri/sky.hdr`);
  hdr.mapping = THREE.EquirectangularReflectionMapping;
  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();
  scene.environment = pmrem.fromEquirectangular(hdr).texture;
  scene.environmentIntensity = 0.45;
  scene.background = hdr;
  scene.backgroundIntensity = 1.0;
  // core.js already added a hemisphere light and a shadow-casting sun (positioned from the
  // scene bbox after the build); retune them to the standalone build's values
  for (const o of scene.children) {
    if (o.isHemisphereLight) { o.intensity = 0.4; o.color.set(0xdfeaf5); o.groundColor.set(0x6b5b45); }
    if (o.isDirectionalLight) {
      o.intensity = 4.2; o.color.set(0xfff0d8);
      o.shadow.bias = -0.00035; o.shadow.normalBias = 0.025;
    }
  }
}


// ---------------------------------------------------------------------------------------------
// Harness entry
// ---------------------------------------------------------------------------------------------
// Invisible ramp through the stair nosings: a capsule of radius 0.22-0.32 cannot climb 0.19 m
// risers by sliding, so the walking surface is the ramp. The line through every nosing
// (z = zBottom - i*tread, y = (i+1)*riser) meets y=0 one tread south of the first riser and
// y=LEVEL_H exactly at the top - the treads never poke above it. Same trick as most engines'
// stair colliders.
function addStairRamp() {
  const z0 = STAIR.zBottom + STAIR.tread, z1 = STAIR.zTop;
  const run = z0 - z1, len = Math.hypot(run, LEVEL_H);
  // top surface 4.5 cm above the nosing line: the capsule sinks ~1 cm into the ramp under
  // gravity and the 1.5 cm nosing overhangs would otherwise catch its bottom sphere (verified:
  // a ramp exactly through the nosings jams the capsule at the 6th step)
  // NOTE: the mesh must stay object-visible - three-mesh-bvh's StaticGeometryGenerator collects
  // meshes with traverseVisible(), so an invisible object would silently drop out of the bake;
  // the material is hidden instead (nothing is rendered)
  const m = new THREE.Mesh(new THREE.BoxGeometry(STAIR.x1 - STAIR.x0, 0.06, len), new THREE.MeshBasicMaterial({ visible: false }));
  m.position.set((STAIR.x0 + STAIR.x1) / 2, LEVEL_H / 2 - 0.03 + 0.045, (z0 + z1) / 2);
  m.rotation.x = Math.atan2(LEVEL_H, run);   // local +z (south end) goes down
  m.userData.tag = 'STAIR_RAMP';
  floors[0].add(m);
  return m;
}

/* buildHouse(ctx, sc): sc = {type:'house', id:'house', assets?:'/assets/house/pack'} */
export async function buildHouse(ctx, sc) {
  scene = ctx.scene; renderer = ctx.renderer;
  BASE = sc.assets || BASE;
  anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  scene.add(root);
  manifest = await (await fetch(`${BASE}/manifest.json`)).json();
  ctx.progress('house: sky & lights');
  await buildEnvironment();
  ctx.progress('house: materials');
  await buildMaterials();
  ctx.progress('house: architecture');
  buildArchitecture();
  ctx.progress('house: furniture');
  await Promise.all(Object.keys(manifest.models).map(id => loadModel(id)));
  furnish();
  for (const l of lamps) l.userData.base = l.intensity;
  addStairRamp();
  assignNames();

  // collision: every house mesh is baked (walls, floors, stairs+ramp, furniture, exterior)
  root.updateMatrixWorld(true);
  root.traverse(o => {
    if (!o.isMesh || o.userData.noCollide) return;
    // the BVH bake merges geometries: all must be indexed (Extrude/Shape geometries are not)
    if (!o.geometry.index) o.geometry = mergeVertices(o.geometry);
    // KHR_mesh_quantization furniture carries normalized int16 positions: the bake's
    // applyMatrix4 would write world coordinates back into the [-1,1] normalized range and
    // produce phantom triangles (verified: a stray edge at y=3 pinned the capsule on the stairs).
    // Hand the bake a plain Float32 copy of the positions (per mesh; the render geometry is
    // untouched for the shared clones).
    const pos = o.geometry.attributes.position;
    if (pos && (pos.normalized || !(pos.array instanceof Float32Array))) {
      const g = o.geometry.clone();
      const f = new Float32Array(pos.count * 3);
      for (let i = 0; i < pos.count; i++) { f[i * 3] = pos.getX(i); f[i * 3 + 1] = pos.getY(i); f[i * 3 + 2] = pos.getZ(i); }
      g.setAttribute('position', new THREE.BufferAttribute(f, 3));
      o.geometry = g;
    }
    ctx.worldMeshes.push(o);
  });

  // subtle lamp flicker (sim time)
  let t = 0;
  ctx.addUpdater('house:lamps', dt => {
    t += dt;
    for (let i = 0; i < lamps.length; i++) lamps[i].intensity = lamps[i].userData.base * (1 + Math.sin(t * 1.3 + i) * 0.03);
  });

  // anchor: the house footprint (not the 120 m lawn) so the sun shadow frustum stays tight
  const box = new THREE.Box3(new THREE.Vector3(X0 - 0.6, -0.3, Z0 - 0.6), new THREE.Vector3(X1 + 0.6, 9.2, Z1 + 0.6));
  const spawn = { pos: new THREE.Vector3(...SPAWN.pos), yawDeg: SPAWN.yawDeg };
  ctx.anchors[sc.id] = { box, floorPts: [{ p: spawn.pos.clone(), d: 0 }], floorY: 0, spawn, model: root };
  ctx.house = { root, floors, semantic, rooms: ROOMS, colliders, protos };
  // debug/verification handle (never enters prompts)
  window.__house = ctx.house;
}
