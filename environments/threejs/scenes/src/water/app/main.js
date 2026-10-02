// Entry: WebGL pipeline of the upstream "Beautiful Water" ocean + a realistic reef habitat and a
// first-person diver.  Exposes window.BenchmarkWorld with the same contract as the previous build.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createAdaptiveQuality, inspectGpu, shouldUseAntialias } from '../upstream/core/adaptive-quality.js';
import { readRendererFrameDiagnostics } from '../upstream/core/renderer-diagnostics.js';
import { createBuoy } from '../upstream/scene/buoy.js';
import { seabedHeight } from '../upstream/scene/environment.js';
import { sampleOceanSurface } from '../upstream/scene/waves.js';
import { createSky } from '../upstream/scene/sky.js';
import { createOcean } from '../upstream/scene/ocean.js';
import { createUnderwaterRays } from '../upstream/scene/underwater-rays.js';
import { createLoadingController } from '../upstream/ui/loading.js';
import { setRenderer, loadAllModels } from './assets.js';
import { createSeabed } from './seabed.js';
import { createReef } from './reef.js';
import { createFish } from './fish.js';
import { applyBug, CATALOG } from './bugs.js';
import { installHarness } from './harness.js';
import { createDiveController } from './dive.js';
import { shared } from './caustics.js';

const canvas = document.querySelector('#ocean-canvas');
const app = document.querySelector('#app');
const query = new URLSearchParams(window.location.search);
const harnessMode = query.has('harness');
const loading = createLoadingController(app);
loading.setStage(0.08, 'Starting WebGL');

const antialias = shouldUseAntialias({ width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio });
const renderer = new THREE.WebGLRenderer({ canvas, antialias, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: harnessMode });
// harness config (environments/threejs/runtime/configs/<name>.json served by the bridge): bug id, spawn, targets
const harnessCfg = harnessMode && query.get('config') ? await (await fetch(`/environments/threejs/runtime/configs/${query.get('config')}.json`)).json().catch(() => null) : null;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.9;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.shadowMap.autoUpdate = false;
setRenderer(renderer);

const gpu = inspectGpu(renderer, { deviceMemory: navigator.deviceMemory, hardwareConcurrency: navigator.hardwareConcurrency });
const adaptiveQuality = createAdaptiveQuality({
  width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio,
  gpuClass: gpu.gpuClass, rendererName: gpu.renderer, lockedPixelRatio: null, gpuTimingEnabled: false, targetFrameRate: 60,
});
const quality = adaptiveQuality.getState();

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x063c48, 0.00001);
scene.background = new THREE.Color(0x063c48);
const camera = new THREE.PerspectiveCamera(51, 1, 0.08, 520);
camera.position.set(7.8, 3.65, 10.8);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0.54, 0);
controls.enableDamping = !harnessMode;
controls.dampingFactor = 0.055;
controls.enablePan = false;
controls.minDistance = 2.7;
controls.maxDistance = 46;
controls.minPolarAngle = 0.055;
controls.maxPolarAngle = Math.PI - 0.055;
controls.update();
controls.addEventListener('start', () => app.classList.add('is-orbiting'));
controls.addEventListener('end', () => app.classList.remove('is-orbiting'));

const sunDirection = new THREE.Vector3(-0.58, 0.10, -0.81).normalize();
const surfaceSegments = gpu.gpuClass === 'discrete' ? 300 : 210;
await loading.paint(0.16, 'Building ocean surface');
const sky = createSky(scene, sunDirection);
const ocean = createOcean({ renderer, scene, camera, sunDirection, sky, sun: sky.sun, captureResolution: quality.captureResolution, surfaceSegments });
ocean.uniforms.uWaterDepth.value = 6.0;

await loading.paint(0.28, 'Decoding reef assets');
await loadAllModels((f, id) => loading.setStage(0.28 + f * 0.22, 'Decoding ' + id));
await loading.paint(0.52, 'Shaping the seabed');
const seabed = await createSeabed(scene, sunDirection, { shadowMapResolution: quality.shadowMapResolution });
await loading.paint(0.6, 'Growing the reef');
const reef = await createReef(scene);
const fishSchools = createFish(scene, { headFlip: query.has('headflip'), debug: query.has('fishdebug') });   // v3: no flip (fish swam tail-first)
const buoy = createBuoy(scene, sunDirection, { rendererMode: 'webgl' });
buoy.mesh.traverse((o) => {
  if (o.isMesh && o.material && o.material.metalness > 0.4) { o.material.metalness = 0.15; o.material.roughness = 0.6; o.material.color.setHex(0x2a3338); }
});
const underwaterRays = createUnderwaterRays(sunDirection);
// exhaled bubbles rising from the diver
const bubbleCount = 48;
const bubbleGeo = new THREE.BufferGeometry();
const bubblePos = new Float32Array(bubbleCount * 3);
const bubbleAge = new Float32Array(bubbleCount).map(() => Math.random() * 3);
bubbleGeo.setAttribute('position', new THREE.BufferAttribute(bubblePos, 3));
const bubbleTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 32; const x = c.getContext('2d'); const g = x.createRadialGradient(16, 16, 4, 16, 16, 15); g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(0.75, 'rgba(255,255,255,0.15)'); g.addColorStop(0.9, 'rgba(255,255,255,0.9)'); g.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = g; x.fillRect(0, 0, 32, 32); const t = new THREE.CanvasTexture(c); return t; })();
const bubbles = new THREE.Points(bubbleGeo, new THREE.PointsMaterial({ map: bubbleTex, size: 0.045, transparent: true, opacity: 0.7, depthWrite: false, sizeAttenuation: true }));
bubbles.frustumCulled = false; bubbles.renderOrder = 5; bubbles.visible = false;
scene.add(bubbles);
let lastBubbleTime = 0;
function updateBubbles(elapsed) {
  const dt = Math.min(0.1, Math.max(0, elapsed - lastBubbleTime)); lastBubbleTime = elapsed;
  const show = diver.isActive() && cameraIsUnderwater;
  bubbles.visible = show;
  if (!show) return;
  const p = bubbleGeo.attributes.position;
  for (let i = 0; i < bubbleCount; i++) {
    bubbleAge[i] += dt;
    const surface = sampleOceanSurface(p.getX(i), p.getZ(i), elapsed).height - 0.05;
    if (bubbleAge[i] > 3.2 || p.getY(i) > surface) {
      bubbleAge[i] = (i % 8) * 0.05;
      const yaw = diver.getState().rotation.yaw;
      p.setXYZ(i, camera.position.x + (Math.random() - 0.5) * 0.2 - Math.sin(yaw) * 0.9, camera.position.y - 0.45, camera.position.z + (Math.random() - 0.5) * 0.2 - Math.cos(yaw) * 0.9);
    } else {
      p.setXYZ(i, p.getX(i) + Math.sin(elapsed * 6 + i) * 0.004, p.getY(i) + (0.45 + (i % 5) * 0.06) * dt, p.getZ(i) + Math.cos(elapsed * 5 + i * 1.3) * 0.004);
    }
  }
  p.needsUpdate = true;
}
const underwaterWorld = [...seabed.underwaterObjects, ...reef.underwaterObjects, ...fishSchools.underwaterObjects, ...buoy.underwaterObjects];

const diver = createDiveController({ camera, domElement: renderer.domElement, controls, app, seabedHeight, sampleOceanSurface, harnessMode, bounds: 27 });
// benchmark convention: start in first person (the diver) instead of the orbit "观察模式"; keys work at once,
// mouse look starts on the first click on the canvas (pointer lock needs a user gesture)
if (!harnessMode) { diver.headless = true; diver.reset(); diver.activate(false); }

// v3: rocks are solid for the diver (sphere colliders from their bounds)
const rocks = []; reef.group.traverse((o) => { if (o.name === 'ROCK') rocks.push(o); });
const corals = []; reef.group.traverse((o) => { if (/^CORAL_/.test(o.name)) corals.push(o); });
function colliderFor(rock) {
  const bb = new THREE.Box3().setFromObject(rock); const c = bb.getCenter(new THREE.Vector3()); const sz = bb.getSize(new THREE.Vector3());
  // ellipsoid from the world bounds (0.78 x half extents: a rounded fit that never blocks open water)
  return { x: c.x, y: c.y, z: c.z, rx: 0.78 * sz.x / 2, ry: 0.85 * sz.y / 2, rz: 0.78 * sz.z / 2, obj: rock };
}
rocks.forEach((r) => diver.colliders.push(colliderFor(r)));

// bug injection (?bug=wtXX): mutation + judge answer; behaviour bugs register per-frame hooks
const bugHooks = [];
const bugCtx = {
  THREE, scene, reef: reef.group, rocks, corals, schools: fishSchools.schools, diver, seabedHeight,
  addCollider: (c) => diver.colliders.push(c),
  removeColliderFor: (obj) => { const i = diver.colliders.findIndex((c) => c.obj === obj); if (i >= 0) diver.colliders.splice(i, 1); },
  refreshCollider: (obj) => { const i = diver.colliders.findIndex((c) => c.obj === obj); if (i >= 0) diver.colliders[i] = colliderFor(obj); },
  onFrame: (fn) => bugHooks.push(fn),
};
const bugId = query.get('bug') || (harnessCfg && harnessCfg.bug) || null;
const bugAnswer = bugId ? applyBug(bugId, bugCtx) : null;
if (bugId && !bugAnswer) console.warn('unknown bug id', bugId, 'known:', Object.keys(CATALOG));

window.BenchmarkWorld = {
  version: 'beautiful-water-reef-v3',
  ready: false,
  THREE, scene, camera, renderer, controls,
  player: diver,
  reef: reef.group,
  sunDirection,
  addObject(object) { scene.add(object); return object; },
  removeObject(object) { scene.remove(object); return object; },
  getState() { return { ...diver.getState(), underwater: underwaterMix > 0.5, fps: Math.round(fpsValue) }; },
  teleport(x, y, z) { camera.position.set(x, y, z); return diver.getState(); },
  setView(yaw, pitch) { diver.setView(yaw, pitch); },
  activateDiver(useLock = false) { diver.headless = !useLock; diver.activate(useLock); },
  bug: bugAnswer,
  bugCatalog: Object.keys(CATALOG),
};

function applyRenderQuality() {
  const q = adaptiveQuality.getState();
  renderer.setPixelRatio(q.pixelRatio);
  renderer.setSize(q.width, q.height, false);
  ocean.setCaptureResolution(q.captureResolution);
  seabed.setShadowMapResolution(q.shadowMapResolution);
  renderer.shadowMap.needsUpdate = true;
  underwaterRays.resize(q.drawingBufferWidth, q.drawingBufferHeight);
  camera.aspect = q.width / q.height;
  camera.updateProjectionMatrix();
}
function resize() {
  adaptiveQuality.resize(window.innerWidth, window.innerHeight, window.devicePixelRatio);
  applyRenderQuality();
}
window.addEventListener('resize', resize, { passive: true });
resize();

const timer = new THREE.Timer();
timer.connect(document);
let underwaterMix = 0;
let cameraIsUnderwater = false;
let renderedFrames = 0;
let fpsValue = 0, fpsAcc = 0, fpsN = 0, lastElapsed = 0;

function updateFrameState(elapsed) {
  diver.update(elapsed);
  if (!diver.isActive()) {
    if (!harnessMode) controls.target.set(buoy.mesh.position.x, buoy.mesh.position.y + 0.62, buoy.mesh.position.z);
    controls.update();
    const targetFloor = seabedHeight(controls.target.x, controls.target.z) + 0.22;
    controls.target.y = Math.max(controls.target.y, targetFloor);
    const cameraFloor = seabedHeight(camera.position.x, camera.position.z) + 0.3;
    if (camera.position.y < cameraFloor) { camera.position.y = cameraFloor; controls.update(); }
  }
  const cameraSurface = sampleOceanSurface(camera.position.x, camera.position.z, elapsed);
  const underwaterTarget = camera.position.y < cameraSurface.height ? 1 : 0;
  cameraIsUnderwater = underwaterTarget > 0.5;
  underwaterMix = THREE.MathUtils.lerp(underwaterMix, underwaterTarget, 0.12);
  if (Math.abs(underwaterMix - underwaterTarget) < 0.003) underwaterMix = underwaterTarget;

  shared.uTime.value = elapsed;
  shared.uUnderwater.value = underwaterMix;
  ocean.update(elapsed, underwaterMix);
  sky.update(elapsed, underwaterMix, camera);
  seabed.update(elapsed, underwaterMix);
  fishSchools.update(elapsed, underwaterMix, camera);
  for (const h of bugHooks) h(elapsed, camera);
  buoy.update(elapsed, underwaterMix);
  if (cameraIsUnderwater) buoy.captureHiddenObjects.forEach((o) => { o.visible = false; });
  underwaterRays.update(elapsed, underwaterMix, camera);
  updateBubbles(elapsed);
  scene.fog.density = THREE.MathUtils.lerp(0.0017, 0.03, underwaterMix);
  renderer.toneMappingExposure = THREE.MathUtils.lerp(0.9, 1.0, underwaterMix);
  app.classList.toggle('is-underwater', underwaterMix > 0.5);
}

function renderOceanCaptures(pass = 'both') {
  underwaterWorld.forEach((o) => { o.visible = true; });
  if (underwaterMix < 0.65) {
    if (pass === 'reflection') ocean.renderReflectionCapture(buoy.captureHiddenObjects);
    else if (pass === 'refraction') ocean.renderRefractionCapture(buoy.captureHiddenObjects);
    else ocean.renderCaptures(buoy.captureHiddenObjects);
  }
  if (!cameraIsUnderwater) underwaterWorld.forEach((o) => { o.visible = false; });
}
function renderScene() {
  renderer.render(scene, camera);
  underwaterRays.render(renderer);
}
function renderFrame(elapsed) {
  if (renderedFrames % 2 === 0) renderer.shadowMap.needsUpdate = true;
  updateFrameState(elapsed);
  renderOceanCaptures();
  renderScene();
  renderedFrames += 1;
}

await loading.paint(0.72, 'Compiling water and reflections');
await Promise.all([renderer.compileAsync(scene, camera), ocean.compileCaptures(buoy.captureHiddenObjects)]);
updateFrameState(0);
renderer.shadowMap.needsUpdate = true;
await loading.paint(0.84, 'Warming reflection');
renderOceanCaptures('reflection');
await loading.paint(0.9, 'Warming refraction');
renderOceanCaptures('refraction');
await loading.paint(0.96, 'Opening water');
renderScene();
await loading.reveal();
window.BenchmarkWorld.ready = true;
if (!harnessMode) {   // review overlay hooks (src/common/bug_picker.js): hover 3 m from the answer looking at it; a beam marks it
  window.__bugGoto = (at) => {
    const ang = 200 * Math.PI / 180, cx = at[0] + Math.sin(ang) * 3.2, cz = at[2] + Math.cos(ang) * 3.2;
    diver.headless = true; diver.activate(false); camera.position.set(cx, Math.max(seabedHeight(cx, cz) + 0.8, at[1] + 0.6), cz);
    const dx = at[0] - cx, dz = at[2] - cz; diver.setView(Math.atan2(-dx, -dz), Math.max(-1.3, Math.min(1.3, Math.atan2(at[1] - camera.position.y, Math.hypot(dx, dz)))));
  };
  let beacon = null;
  window.__bugBeacon = (at) => {
    if (beacon) { beacon.visible = !beacon.visible; return beacon.visible; }
    beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 8, 8), new THREE.MeshBasicMaterial({ color: 0xffd166 }));
    beacon.position.set(at[0], at[1] + 3, at[2]); scene.add(beacon); return true;
  };
}
if (harnessMode) {
  const film = query.get('obs') === 'film' ? { dt: +(query.get('filmDt') || 0.5), maxFrames: +(query.get('filmMax') || 8), w: 480, h: 300 } : null;
  installHarness({ renderer, camera, diver, config: harnessCfg || { name: query.get('config') || 'reef' }, bugAnswer, film });
}

renderer.setAnimationLoop(() => {
  if (document.hidden) return;
  timer.update();
  const elapsed = timer.getElapsed();
  const dt = elapsed - lastElapsed; lastElapsed = elapsed;
  fpsAcc += dt; fpsN++; if (fpsAcc >= 1) { fpsValue = fpsN / fpsAcc; fpsAcc = 0; fpsN = 0; }
  renderFrame(elapsed);
});
