// Decodes the embedded pack (base64 / gzip) into three.js textures and glTF models.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const PACK = window.__PACK;
const RT = window.__RT;
const texLoader = new THREE.TextureLoader();
const gltfLoader = new GLTFLoader();
let anisotropy = 4;

export function setRenderer(renderer) {
  anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
}

async function blobUrl(b64, type, gunzip = false) {
  let buf = await RT.bytes(b64);
  if (gunzip) buf = await RT.gunzip(buf);
  return URL.createObjectURL(new Blob([buf], { type }));
}

export async function loadTexture(b64, srgb) {
  const t = await texLoader.loadAsync(await blobUrl(b64, 'image/webp'));
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = anisotropy;
  t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  return t;
}

const texCache = {};
export async function texSet(id) {
  if (texCache[id]) return texCache[id];
  const e = PACK.textures[id];
  const [diff, nor, arm] = await Promise.all([
    e.diff ? loadTexture(e.diff, true) : null,
    e.nor ? loadTexture(e.nor, false) : null,
    e.arm ? loadTexture(e.arm, false) : null,
  ]);
  return (texCache[id] = { diff, nor, arm });
}

// PBR material whose maps tile every `tile` metres (geometry UVs are in metres)
export async function pbr(id, tile, opts = {}) {
  const s = await texSet(id);
  const rep = 1 / tile;
  const m = new THREE.MeshStandardMaterial({
    color: opts.color ?? 0xffffff,
    roughness: opts.roughness ?? 1,
    metalness: opts.metalness ?? 0,
    side: opts.side ?? THREE.FrontSide,
  });
  const maps = [];
  if (s.diff && !opts.noDiffuse) { m.map = s.diff.clone(); maps.push(m.map); }
  if (s.nor) { m.normalMap = s.nor.clone(); m.normalScale = new THREE.Vector2(opts.normalScale ?? 1, opts.normalScale ?? 1); maps.push(m.normalMap); }
  if (s.arm) { m.aoMap = s.arm.clone(); m.roughnessMap = m.aoMap; m.metalnessMap = m.aoMap; maps.push(m.aoMap); m.aoMapIntensity = opts.ao ?? 1; }
  for (const t of maps) { t.repeat.set(rep, rep); t.rotation = opts.rotation ?? 0; t.needsUpdate = true; }
  return m;
}

export const models = {};
export async function loadModel(id) {
  const e = PACK.models[id];
  const buf = await RT.gunzip(await RT.bytes(e.glb));
  const gltf = await gltfLoader.parseAsync(buf, '');
  const obj = gltf.scene;
  obj.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = o.receiveShadow = true;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats) if (m.map) m.map.anisotropy = anisotropy;
    }
  });
  obj.userData.bbox = new THREE.Box3(new THREE.Vector3(e.bbox[0], e.bbox[1], e.bbox[2]), new THREE.Vector3(e.bbox[3], e.bbox[4], e.bbox[5]));
  models[id] = obj;
  return obj;
}

export async function loadAllModels(onProgress) {
  const ids = Object.keys(PACK.models);
  let done = 0;
  await Promise.all(ids.map((id) => loadModel(id).then(() => { done++; onProgress?.(done / ids.length, id); })));
  return models;
}

// First mesh of a loaded model with its world transform baked in (for instancing).
export function bakedGeometry(id) {
  const root = models[id];
  root.updateMatrixWorld(true);
  let found = null;
  root.traverse((o) => { if (o.isMesh && !found) found = o; });
  const src = found.geometry;
  const geo = new THREE.BufferGeometry();
  for (const name of Object.keys(src.attributes)) {
    const a = src.attributes[name];
    const arr = new Float32Array(a.count * a.itemSize);
    for (let i = 0; i < a.count; i++) for (let k = 0; k < a.itemSize; k++) arr[i * a.itemSize + k] = a.getComponent(i, k);
    geo.setAttribute(name, new THREE.BufferAttribute(arr, a.itemSize));
  }
  if (src.index) geo.setIndex(src.index.clone());
  geo.applyMatrix4(found.matrixWorld);   // includes the quantization scale/offset node
  return { geometry: geo, material: found.material };
}
