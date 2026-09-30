#!/usr/bin/env python3
"""Derive env/house/house.js (harness scene module) from app.js (standalone walkthrough).

The house geometry/furnishing code is shared verbatim; this script swaps the standalone
preamble (renderer, player, DOM), the embedded-pack asset loaders and the boot/controls tail
for the harness versions (see the header comment written into house.js). Re-run after editing
app.js:  .venv/bin/python candidate_environments/src/house/make_harness_module.py
"""
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
src = (HERE / "app.js").read_text()

i_reg = src.index("const colliders = [];")
header = r'''/* env/house/house.js - "Family House" scene for the harness (scene type "house").
 * GENERATED from candidate_environments/src/house/app.js by make_harness_module.py - edit there.
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
__CONSTANTS__
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

'''
# the metre constants (CEIL, LEVEL_H, EXT_T, INT_T, X0.., STAIR incl. holeZ) are copied verbatim
# from app.js so the two builds can never drift apart
c0 = src.index("const CEIL = 2.7;")
c1 = src.index("\n", src.index("STAIR.holeZ = ")) + 1
header = header.replace("__CONSTANTS__\n", src[c0:c1] + "const FRONT_DOOR_ANGLE = 0;   // harness scene: the front door stays shut (the standalone walkthrough opens it)\n")
body = src[i_reg:]

old = """const colliders = [];   // {box: Box3 (world), floor: 0|1|2(both)}
const semantic = {};
let itemCount = 0;
const lamps = [];       // flickering point lights

function register(name, obj) {
  obj.name = name;
  (semantic[name] || (semantic[name] = [])).push(obj);
  itemCount++;
  return obj;
}"""
new = """const colliders = [];   // {box: Box3 (world), floor: 0|1|2(both)} - kept as metadata only (physics = BVH)
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
}"""
assert old in body
body = body.replace(old, new)

i0 = body.index("const texLoader = new THREE.TextureLoader();")
i1 = body.index("function boxGeo(w, h, d, uvScale = 1) {")
assets = """const texLoader = new THREE.TextureLoader();
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

"""
body = body[:i0] + assets + body[i1:]

i0 = body.index("async function buildEnvironment() {")
i1 = body.index("// Player controls")
i1 = body.rfind("// ----", 0, i1)
env = """async function buildEnvironment() {
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

"""
body = body[:i0] + env + body[i1:]

tail = '''
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
'''
cut = body.index("// ---------------------------------------------------------------------------------------------\n// Player controls")
out = header + body[:cut] + tail
dest = REPO / "env" / "house" / "house.js"
dest.write_text(out)
left = [tok for tok in ["PACK.", "RT.", "canvas", "floorLabel", "itemsLabel", "roomLabel", "player.", "blobUrl("] if re.search(re.escape(tok), out)]
print(f"wrote {dest} ({out.count(chr(10))} lines)", "leftovers:", left)
