/*
 * Sketchbook Airfield — polish layer (runs on top of the unmodified upstream bundle).
 *
 * The bundle is patched by build.py to expose `window.THREE` (r113), `window.CANNON` and the GLTFLoader
 * class it uses (`window.__SB_GLTFLoader`).  Once the world and the player character exist this script:
 *   1. fixes the colour pipeline (sRGB output, saner sun / sky intensities, light haze),
 *   2. swaps the flat placeholder textures of the big surfaces for Poly Haven PBR sets
 *      (MeshStandardMaterial with normal / roughness / AO maps, cascaded-shadow patched),
 *   3. scatters static props (crates, barrels, barriers, lamps, a chain-link fence …) with cannon.js
 *      box colliders so the player and the vehicles cannot drive through them,
 *   4. tints the car, adds camera / HUD helpers and a BenchmarkWorld API for the harness.
 * Everything is additive: the upstream game loop, physics and controls are untouched.
 */
(() => {
  'use strict';
  const PACK = window.__SKETCH_PACK__ || { models: {}, textures: {} };
  const PROPS = window.__SKETCH_PROPS__ || [];
  const T = window.THREE, C = window.CANNON, GLTFLoader = window.__SB_GLTFLoader;
  const log = (...a) => console.log('[sketch-polish]', ...a);
  const state = { ready: false, stage: 'waiting', props: 0, materials: 0, errors: [] };

  // ------------------------------------------------------------------ settings
  const LIGHT = { sun: 1.45, hemiMax: 0.55, hemiMin: 0.22, exposure: 0.95, fog: { color: 0xdbe3ec, near: 140, far: 900 } };
  // material name in world.glb -> Poly Haven set, texture repeat per UV unit, optional tint
  const SURFACES = {
    concrete:       { tex: 'concrete_floor_worn_001', repeat: [1.7, 1.7] },   // apron, 1 UV unit ~ 5 m
    plaster:        { tex: 'concrete_wall_008', repeat: [1.5, 1.5], color: 0xe2dccf },
    wall_rough:     { tex: 'concrete_wall_006', repeat: [4, 4] },
    wall_segmented: { tex: 'concrete_slab_wall', repeat: [3, 2.6] },          // 6 m retaining walls
    roof:           { tex: 'aerial_grass_rock', repeat: [0.34, 0.34] },       // plateau above the walls
    dirt_road:      { tex: 'gravel_road', repeat: [8.7, 3.3] },
  };
  // materials that keep their own painted texture (lines, stripes, signs) but become PBR
  const KEEP = { race_track: 0.85, runway: 0.9, helipad: 0.7, barrier: 0.9, side_barrier: 0.9, arrow_down: 0.6,
                 s1: 0.9, s2: 0.9, s3: 0.9, s4: 0.9, s5: 0.9, s6: 0.9 };
  const CAR_PAINT = 0xa8271f;
  const FIRST_PERSON_DEFAULT = true;   // benchmark convention: all environments start in first person
  const EYE_RAISE = 1.05;              // first person: lift the camera from the Boxman's 0.6 m eye line to ~1.65 m above the ground (the map is 1:1 metres)
  const VEHICLE_RADIUS = 4.5;          // third-person distance while driving / flying

  // ------------------------------------------------------------------ helpers
  const b64ToBytes = (s) => { const bin = atob(s); const out = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i); return out; };
  async function gunzip(bytes) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Response(stream).arrayBuffer();
  }
  const loadImage = (b64, mime) => new Promise((res, rej) => { const img = new Image(); img.onload = () => res(img); img.onerror = rej; img.src = `data:${mime};base64,${b64}`; });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const world = () => window.sketchbookWorld;
  const player = () => { const w = world(); return w && w.characters && w.characters[0]; };
  const isVisible = (o) => { for (let q = o; q; q = q.parent) if (!q.visible) return false; return true; };

  async function textureSet(id, repeat) {
    const t = PACK.textures[id];
    if (!t) throw new Error('texture set missing: ' + id);
    const maps = {};
    for (const k of ['diff', 'nor', 'arm']) {
      if (!t[k]) continue;
      const tex = new T.Texture(await loadImage(t[k], 'image/jpeg'));
      tex.wrapS = tex.wrapT = T.RepeatWrapping;
      tex.repeat.set(repeat[0], repeat[1]);
      tex.anisotropy = 8;
      if (k === 'diff') tex.encoding = T.sRGBEncoding;
      tex.needsUpdate = true;
      maps[k] = tex;
    }
    return maps;
  }

  function csmPatch(m) { try { world().sky.csm.setupMaterial(m); } catch (e) { state.errors.push('csm: ' + e.message); } m.needsUpdate = true; return m; }

  // ------------------------------------------------------------------ 1. colour / light
  function applyLighting() {
    const w = world(), r = w.renderer, sky = w.sky;
    r.outputEncoding = T.sRGBEncoding;
    r.toneMapping = T.ACESFilmicToneMapping;
    r.toneMappingExposure = LIGHT.exposure;
    sky.maxHemiIntensity = LIGHT.hemiMax; sky.minHemiIntensity = LIGHT.hemiMin; sky.refreshHemiIntensity();
    sky.csm.lightIntensity = LIGHT.sun;
    (sky.csm.lights || []).forEach((l) => { l.intensity = LIGHT.sun; });
    // subtle atmospheric haze so the 300 m apron and the far walls read as distant
    w.graphicsWorld.fog = new T.Fog(LIGHT.fog.color, LIGHT.fog.near, LIGHT.fog.far);
    // a slightly deeper sky (Preetham params)
    const u = sky.skyMaterial && sky.skyMaterial.uniforms;
    if (u) { u.turbidity.value = 3.2; u.rayleigh.value = 1.35; u.mieCoefficient.value = 0.006; }
    w.graphicsWorld.traverse((o) => { if (o.isMesh) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => { m.needsUpdate = true; }); });
  }

  // ------------------------------------------------------------------ 2. PBR surfaces
  async function applyMaterials() {
    const w = world();
    const skip = new Set();
    w.characters.forEach((c) => c.traverse((o) => skip.add(o)));
    w.vehicles.forEach((v) => v.traverse((o) => skip.add(o)));
    const byName = {};
    w.graphicsWorld.traverse((o) => {
      if (!o.isMesh || skip.has(o) || !isVisible(o)) return;
      const m = Array.isArray(o.material) ? o.material[0] : o.material;
      if (!m || m.type !== 'MeshPhongMaterial') return;
      (byName[m.name] = byName[m.name] || []).push(o);
    });
    const normalDetail = await textureSet('plastered_wall_04', [6, 6]);
    for (const [name, meshes] of Object.entries(byName)) {
      const spec = SURFACES[name];
      let mat;
      if (spec) {
        const maps = await textureSet(spec.tex, spec.repeat);
        mat = new T.MeshStandardMaterial({ name: name + '_pbr', map: maps.diff, normalMap: maps.nor, roughnessMap: maps.arm, aoMap: maps.arm,
          roughness: 1.0, metalness: 0.0, color: spec.color !== undefined ? spec.color : 0xffffff });
        mat.normalScale.set(0.8, 0.8);
      } else if (KEEP[name] !== undefined) {
        const old = meshes[0].material;
        mat = new T.MeshStandardMaterial({ name: name + '_pbr', map: old.map, roughness: KEEP[name], metalness: 0.0, transparent: old.transparent });
        if (/^s[1-6]$/.test(name)) { mat.normalMap = normalDetail.nor; mat.normalScale.set(0.35, 0.35); }
      } else continue;
      csmPatch(mat);
      for (const mesh of meshes) {
        const g = mesh.geometry;
        if (g.attributes.uv && !g.attributes.uv2) g.setAttribute('uv2', g.attributes.uv);
        mesh.material = mat;
      }
      state.materials++;
    }
    // vehicles: keep the baked textures but give the car a paint colour and less plastic-looking bodies
    w.vehicles.forEach((v) => {
      v.traverse((o) => {
        if (!o.isMesh || !o.material || !o.material.map) return;
        if (o.name === 'body' && o.material.name === 'Car') {
          const paint = o.material.clone(); paint.color.setHex(CAR_PAINT); paint.shininess = 60; paint.specular.setHex(0x444444);
          paint.reflectivity = 0.35; paint.combine = T.MixOperation;
          o.material = carPaint = csmPatch(paint);
        }
      });
    });
  }

  // ------------------------------------------------------------------ 3. props + colliders
  const modelCache = {};
  const propMaterials = new Set();
  // nodes to drop from a kit before use (the hydrant model ships two variants side by side)
  const NODE_DROP = { fire_hydrant: /aged/ };
  let latticeTex = null;
  function chainLinkAlpha() {
    // diamond lattice used as alphaMap for the fence wire: white = wire, black = hole
    if (latticeTex) return latticeTex;
    const n = 64, c = document.createElement('canvas'); c.width = c.height = n;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, n, n);
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 3.2; ctx.lineCap = 'round';
    ctx.beginPath();
    for (const [x0, y0, x1, y1] of [[-n, 0, n, 2 * n], [0, -n, 2 * n, n], [-n, n, n, -n], [0, 2 * n, 2 * n, 0]]) { ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); }
    ctx.stroke();
    latticeTex = new T.Texture(c); latticeTex.wrapS = latticeTex.wrapT = T.RepeatWrapping; latticeTex.anisotropy = 8; latticeTex.needsUpdate = true;
    return latticeTex;
  }
  function makeWireMaterial(mesh) {
    // cells ~5 cm: repeat derived from the plane size vs its UV range
    const g = mesh.geometry; g.computeBoundingBox();
    const size = g.boundingBox.getSize(new T.Vector3());
    const uv = g.attributes.uv; let umin = 1e9, umax = -1e9, vmin = 1e9, vmax = -1e9;
    for (let i = 0; i < uv.count; i++) { const u = uv.getX(i), v = uv.getY(i); umin = Math.min(umin, u); umax = Math.max(umax, u); vmin = Math.min(vmin, v); vmax = Math.max(vmax, v); }
    const w = Math.max(size.x, size.z), h = size.y;
    const tex = chainLinkAlpha().clone(); tex.needsUpdate = true;
    tex.repeat.set((w / 0.055) / Math.max(umax - umin, 1e-3), (h / 0.055) / Math.max(vmax - vmin, 1e-3));
    const m = new T.MeshStandardMaterial({ name: 'chainlink_wire', color: 0x9aa0a6, metalness: 0.75, roughness: 0.4,
      alphaMap: tex, alphaTest: 0.35, side: T.DoubleSide });
    return m;
  }
  let carPaint = null;
  const propGroup = new T.Group(); propGroup.name = 'polish_props';
  let groundMeshes = null;
  const ray = new T.Raycaster(); const DOWN = new T.Vector3(0, -1, 0);
  function groundY(x, z) {
    ray.set(new T.Vector3(x, 250, z), DOWN);
    // lowest walkable surface (apron / pads / pits), ignoring ramp decks and overpasses above it
    const hits = ray.intersectObjects(groundMeshes, false).filter((h) => h.point.y >= 9.5);
    return hits.length ? hits[hits.length - 1].point.y : 14.8;
  }
  async function loadModel(id) {
    if (modelCache[id]) return modelCache[id];
    // chainlink_panel = the plain 2 m module of the modular fence kit
    const src = id === 'chainlink_panel' ? 'modular_chainlink_fence' : id;
    const entry = PACK.models[src];
    if (!entry) throw new Error('model missing: ' + src);
    const buf = await gunzip(b64ToBytes(entry.glb));
    const gltf = await new Promise((res, rej) => new GLTFLoader().parse(buf, '', res, rej));
    let root = gltf.scene;
    if (id === 'chainlink_panel') { const node = root.getObjectByName('modular_chainlink_fence'); node.position.set(0, 0, 0); root = node; }
    if (NODE_DROP[id]) { const drop = []; root.traverse((o) => { if (NODE_DROP[id].test(o.name)) drop.push(o); }); drop.forEach((o) => o.parent && o.parent.remove(o)); }
    root.traverse((o) => {   // Poly Haven's fence wire is exported without alpha -> procedural lattice
      if (o.isMesh && o.material && /wire/.test(o.material.name)) o.material = makeWireMaterial(o);
    });
    root.updateMatrixWorld(true);
    const box = new T.Box3().setFromObject(root);
    const c = box.getCenter(new T.Vector3()); const size = box.getSize(new T.Vector3());
    const proto = new T.Group();
    root.position.set(root.position.x - c.x, root.position.y - box.min.y, root.position.z - c.z);
    proto.add(root);
    root.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true; o.receiveShadow = true;
      (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => {
        if (m.userData.csm) return;
        m.userData.csm = true;
        propMaterials.add(m);
        csmPatch(m);
      });
    });
    // where the prop actually touches the ground (centroid of the lowest vertices, relative to the box centre): a lamp's
    // bounding box is centred under its arm, its pole is not
    const base = new T.Vector3(); let nb = 0; const v = new T.Vector3(); proto.updateMatrixWorld(true);
    proto.traverse((o) => { if (!o.isMesh) return; const pos = o.geometry.attributes.position; for (let i = 0; i < pos.count; i += 3) { v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld); if (v.y < 0.25) { base.x += v.x; base.z += v.z; nb++; } } });
    if (nb) base.multiplyScalar(1 / nb);
    return (modelCache[id] = { proto, half: [size.x / 2, size.y / 2, size.z / 2], base: [base.x, base.z] });
  }
  function addStaticBox(x, y, z, yawDeg, half) {
    const body = new C.Body({ mass: 0 });
    body.addShape(new C.Box(new C.Vec3(half[0], half[1], half[2])));
    body.position.set(x, y + half[1], z);
    body.quaternion.setFromAxisAngle(new C.Vec3(0, 1, 0), yawDeg * Math.PI / 180);
    world().physicsWorld.addBody(body);
    return body;
  }
  // finer collision per prop family: round props get a cylinder of their footprint, posts a slim cylinder at the base
  // (a lamp's bounding box would block the whole area under its arm); boxy props keep their box.
  const ROUND = /^(barrel_03|propane_tank|fire_hydrant|metal_jerrycan_green|industrial_pastic_container)$/;
  const POST = /^(street_lamp_01)$/;
  function addStaticShape(model, x, y, z, yawDeg, half, base = [0, 0]) {
    if (POST.test(model)) {
      const body = new C.Body({ mass: 0 });
      const r = 0.16, h = half[1] * 2; const a = yawDeg * Math.PI / 180;
      x += base[0] * Math.cos(a) + base[1] * Math.sin(a); z += -base[0] * Math.sin(a) + base[1] * Math.cos(a);   // pole base, rotated with the prop
      const cyl = new C.Cylinder(r, r, h, 12); const q = new C.Quaternion(); q.setFromAxisAngle(new C.Vec3(1, 0, 0), Math.PI / 2);   // cannon cylinders lie along z
      body.addShape(cyl, new C.Vec3(0, 0, 0), q); body.position.set(x, y + half[1], z); world().physicsWorld.addBody(body); return body;
    }
    if (ROUND.test(model)) {
      const body = new C.Body({ mass: 0 });
      const r = Math.min(half[0], half[2]) * (model === 'fire_hydrant' ? 0.75 : 1.0), h = half[1] * 2;
      const cyl = new C.Cylinder(r, r, h, 14); const q = new C.Quaternion(); q.setFromAxisAngle(new C.Vec3(1, 0, 0), Math.PI / 2);
      body.addShape(cyl, new C.Vec3(0, 0, 0), q); body.position.set(x, y + half[1], z); world().physicsWorld.addBody(body); return body;
    }
    return addStaticBox(x, y, z, yawDeg, half);
  }
  async function placeProps() {
    const w = world();
    const skip = new Set();
    w.characters.forEach((c) => c.traverse((o) => skip.add(o)));
    w.vehicles.forEach((v) => v.traverse((o) => skip.add(o)));
    groundMeshes = [];
    w.graphicsWorld.traverse((o) => {
      if (!o.isMesh || skip.has(o) || !isVisible(o)) return;
      const m = Array.isArray(o.material) ? o.material[0] : o.material;
      if (!m || m.type === 'ShaderMaterial') return;   // sky dome, ocean
      groundMeshes.push(o);
    });
    w.graphicsWorld.add(propGroup);
    const ids = [...new Set(PROPS.map((p) => p.m))];
    await Promise.all(ids.map((id) => loadModel(id).catch((e) => { state.errors.push(id + ': ' + e.message); })));
    for (const p of PROPS) {
      const model = modelCache[p.m];
      if (!model) continue;
      const y = groundY(p.x, p.z);
      const inst = model.proto.clone();
      inst.position.set(p.x, y, p.z);
      inst.rotation.y = (p.yaw || 0) * Math.PI / 180;
      inst.name = p.m + '#' + state.props;
      inst.userData.prop = p;
      propGroup.add(inst);
      inst.userData.body = addStaticShape(p.m, p.x, y, p.z, p.yaw || 0, model.half, model.base);
      state.props++;
    }
  }

  // ------------------------------------------------------------------ 3b. environment reflections
  function buildEnvironment() {
    const w = world();
    const cubeCam = new T.CubeCamera(0.5, 1500, 256);
    cubeCam.position.set(0, 18, -5);
    w.sky.position.copy(cubeCam.position); w.sky.refreshSunPosition();
    const hidden = [];
    w.characters.forEach((c) => { hidden.push(c); c.visible = false; });
    cubeCam.update(w.renderer, w.graphicsWorld);
    hidden.forEach((c) => { c.visible = true; });
    const cubeTex = cubeCam.renderTarget.texture;
    let pmremTex = null;
    try { const gen = new T.PMREMGenerator(w.renderer); pmremTex = gen.fromCubemap(cubeTex).texture; gen.dispose(); }
    catch (e) { state.errors.push('pmrem: ' + e.message); }
    propMaterials.forEach((m) => { m.envMap = pmremTex || cubeTex; m.envMapIntensity = 0.9; m.needsUpdate = true; });
    if (carPaint) { carPaint.envMap = cubeTex; carPaint.needsUpdate = true; }
    state.envMap = !!pmremTex;
  }

  // ------------------------------------------------------------------ 4. HUD / camera / API
  function setHud(on) {
    for (const sel of ['#ui-container', '#dat-gui-container', '.dg', '#statsBox', '#offline-status', '#benchmark-boundary-badge']) {
      document.querySelectorAll(sel).forEach((el) => { el.style.display = on ? '' : 'none'; });
    }
  }
  function dismissModal() {
    const btn = document.querySelector('.swal2-confirm');
    if (btn) { btn.click(); return true; }
    return false;
  }
  let thirdPersonRadius = null;
  let wantFirstPerson = false;
  function applyCamera(on) {
    const w = world(), ch = player();
    if (!ch) return;
    if (on) {
      if (thirdPersonRadius === null) thirdPersonRadius = w.cameraOperator.radius;
      w.cameraOperator.setRadius(0.12, true);
      ch.tiltContainer.visible = false;
    } else {
      w.cameraOperator.setRadius(thirdPersonRadius || 1.6, true);
      thirdPersonRadius = null;
      ch.tiltContainer.visible = true;
    }
  }
  function setFirstPerson(on) { wantFirstPerson = !!on; applyCamera(wantFirstPerson && !inVehicle()); }
  // the camera operator writes the camera position every frame; in first person on foot we add the eye raise afterwards
  let eyeHooked = false;
  function hookEye() {
    const w = world(); if (!w || eyeHooked || !w.cameraOperator) return;
    const op = w.cameraOperator, orig = op.update.bind(op);
    op.update = function (dt) { orig(dt); if (thirdPersonRadius !== null && !inVehicle()) w.camera.position.y += EYE_RAISE; };
    eyeHooked = true;
  }
  const inVehicle = () => { const ch = player(); return !!(ch && ch.controlledObject); };
  // parked vehicles are static bodies: a walker bumping into a 50 kg car chassis used to shove it around (review 2026-09-12);
  // the enter-vehicle key is unbound in the bundle (build.py), so nothing ever drives them in the benchmark
  function parkVehicles() {
    const w = world(); if (!w || !w.vehicles) return;
    w.vehicles.forEach((v) => {
      const b = v.collision; if (!b) return;
      b.velocity.set(0, 0, 0); b.angularVelocity.set(0, 0, 0);
      b.mass = 0; b.type = C.Body.STATIC; b.updateMassProperties();
    });
  }
  function unparkVehicle(v, mass) {   // bug af18: one parked car gets a light dynamic chassis again
    const b = v.collision; b.type = C.Body.DYNAMIC; b.mass = mass; b.updateMassProperties(); b.linearDamping = 0.02; b.angularDamping = 0.2; b.wakeUp();
  }
  let wasInVehicle = false;
  const frameHooks = [];                 // bug behaviour hooks: fn(tSeconds, camera)
  const frameT0 = performance.now();
  const SPAWN_DEFAULT = [0.0, 15.4, -14.0];   // harness spawn: open tarmac just north of the stone gate the game starts in
  function cameraWatch() {
    if (frameHooks.length) { const w = world(); const tt = (performance.now() - frameT0) / 1000; for (const h of frameHooks) { try { h(tt, w.camera); } catch (err) { state.errors.push('hook: ' + err.message); frameHooks.splice(frameHooks.indexOf(h), 1); } } }
    // keep first person on foot, switch to a third-person chase view while driving / flying
    const ch = player();
    if (ch) {
      const v = inVehicle();
      if (v !== wasInVehicle) {
        wasInVehicle = v;
        if (wantFirstPerson) {
          if (v) { ch.tiltContainer.visible = true; world().cameraOperator.setRadius(VEHICLE_RADIUS, true); thirdPersonRadius = 1.6; }
          else applyCamera(true);
        }
      }
    }
    requestAnimationFrame(cameraWatch);
  }
  document.addEventListener('keydown', (e) => { if (e.code === 'KeyV' && !e.repeat && !inVehicle()) setFirstPerson(!wantFirstPerson); });
  const upstreamAPI = window.BenchmarkWorld || {};
  window.BenchmarkWorld = {
    ...upstreamAPI,
    version: 'sketchbook-airfield-polish-v2',
    get ready() { return state.ready; },
    get status() { return { ...state }; },
    get world() { return world(); },
    get scene() { const w = world(); return w && w.graphicsWorld; },
    get camera() { const w = world(); return w && w.camera; },
    get renderer() { const w = world(); return w && w.renderer; },
    get player() { return player(); },
    props: propGroup,
    // teleport(x, y, z): y may be null to stand on the surface at (x, z)
    teleport(x, y, z) {
      const ch = player();
      if (!ch) return false;
      if (y === undefined || y === null) y = (groundMeshes ? groundY(x, z) : 14.8) + 0.6;
      ch.setPosition(x, y, z);
      ch.resetVelocity();
      return true;
    },
    setOrientation(dx, dz) { const ch = player(); if (ch) ch.setOrientation(new T.Vector3(dx, 0, dz), true); },
    setView(theta, phi) { const c = world().cameraOperator; c.theta = theta; if (phi !== undefined) c.phi = phi; },
    setDistance(r) { world().cameraOperator.setRadius(r, true); },
    setFirstPerson,
    setHud,
    dismissModal,
    setTimeScale(s) { world().timeScaleTarget = s; },
    getState() {
      const w = world(), ch = player();
      if (!ch) return { ready: false };
      const c = w.cameraOperator;
      const receiver = w.inputManager && w.inputManager.inputReceiver;
      return { position: ch.position.toArray(), theta: c.theta, phi: c.phi, radius: c.radius,
               controlling: receiver === ch ? 'character' : (receiver && receiver.rayCastVehicle ? 'vehicle' : 'camera'),
               speed: ch.velocity ? ch.velocity.length() : 0, firstPerson: thirdPersonRadius !== null, ready: state.ready };
    },
  };

  // ------------------------------------------------------------------ run
  async function main() {
    if (!T || !C || !GLTFLoader) { state.errors.push('bundle globals missing'); log('bundle globals missing — polish layer disabled'); return; }
    for (let i = 0; i < 1200; i++) {        // wait for world.glb + the character (boxman.glb)
      const w = world();
      if (w && w.characters && w.characters.length && w.sky && w.sky.csm) break;
      await sleep(250);
    }
    if (!player()) { state.errors.push('character never appeared'); return; }
    await sleep(300);
    try { state.stage = 'lighting'; applyLighting(); } catch (e) { state.errors.push('lighting: ' + e.message); }
    try { state.stage = 'materials'; await applyMaterials(); } catch (e) { state.errors.push('materials: ' + e.message); }
    try { state.stage = 'props'; await placeProps(); } catch (e) { state.errors.push('props: ' + e.message); }
    try { state.stage = 'environment'; buildEnvironment(); } catch (e) { state.errors.push('environment: ' + e.message); }
    hookEye();
    parkVehicles();
    if (FIRST_PERSON_DEFAULT) { setFirstPerson(true); }
    cameraWatch();
    // ---- bug injection (?bug=afXX-slug or the harness config's bug) + judge answer
    const q = new URLSearchParams(location.search);
    const harnessOn = q.has('harness');
    let hcfg = null;
    if (harnessOn && q.get('config')) { try { hcfg = await (await fetch('/environments/threejs/runtime/configs/' + q.get('config') + '.json')).json(); } catch (err) { hcfg = null; } }
    const bugId = q.get('bug') || (hcfg && hcfg.bug) || null;
    const bugCtx = {
      T, C, world, character: player, props: propGroup.children, groundY, addStaticBox, unparkVehicle,
      syncBody(o, k) {
        const b = o.userData.body; if (!b) return; const sh = b.shapes[0];
        const half = sh.halfExtents || new C.Vec3(sh.radiusTop, sh.height / 2, sh.radiusTop);
        if (k) {
          if (sh.halfExtents) { sh.halfExtents.scale(k, sh.halfExtents); sh.updateConvexPolyhedronRepresentation(); }
          else { const cyl = new C.Cylinder(sh.radiusTop * k, sh.radiusBottom * k, sh.height * k, 14); b.shapes[0] = cyl; b.shapeOffsets[0] = new C.Vec3(); }
          half.scale(k, half); b.updateBoundingRadius();
        }
        b.position.set(o.position.x, o.position.y + half.y, o.position.z);
        if (sh.halfExtents) b.quaternion.setFromAxisAngle(new C.Vec3(0, 1, 0), o.rotation.y);
        b.aabbNeedsUpdate = true;
      },
      removeBody(o) { const b = o.userData.body; if (b) { world().physicsWorld.removeBody(b); o.userData.body = null; } },
      onFrame(fn) { frameHooks.push(fn); },
      respawn() { state.resets = (state.resets || 0) + 1; const sp = (hcfg && hcfg.spawn && hcfg.spawn.pos) || SPAWN_DEFAULT; window.BenchmarkWorld.teleport(sp[0], sp[1], sp[2]); },
    };
    let bugAnswer = null;
    if (bugId && window.__AF_BUGS) {
      try { bugAnswer = window.__AF_BUGS.apply(bugId, bugCtx); if (!bugAnswer) state.errors.push('unknown bug ' + bugId); }
      catch (err) { state.errors.push('bug ' + bugId + ': ' + err.message); }
    }
    window.BenchmarkWorld.bug = bugAnswer;
    window.BenchmarkWorld.bugCatalog = window.__AF_BUGS ? window.__AF_BUGS.ids : [];
    // review overlay hooks (src/common/bug_picker.js): stand 4.5 m from the answer looking at it; a beam marks it
    window.__bugGoto = (at) => {
      const ang = 200 * Math.PI / 180, cx = at[0] + Math.sin(ang) * 4.5, cz = at[2] + Math.cos(ang) * 4.5;
      dismissModal(); setFirstPerson(true); window.BenchmarkWorld.teleport(cx, groundY(cx, cz) + 0.6, cz);
      const c = world().cameraOperator; c.theta = Math.atan2(-(at[0] - cx), -(at[2] - cz)) * 180 / Math.PI;
      c.phi = Math.max(-80, Math.min(80, -Math.atan2(at[1] - (groundY(cx, cz) + 1.65), Math.hypot(at[0] - cx, at[2] - cz)) * 180 / Math.PI));
    };
    let beacon = null;
    window.__bugBeacon = (at) => {
      if (beacon) { beacon.visible = !beacon.visible; return beacon.visible; }
      beacon = new T.Mesh(new T.CylinderGeometry(0.08, 0.08, 12, 8), new T.MeshBasicMaterial({ color: 0xffd166 }));
      beacon.position.set(at[0], at[1] + 6, at[2]); world().graphicsWorld.add(beacon); return true;
    };
    state.stage = 'done'; state.ready = true;
    // ---- harness contract (?harness=1&config=<name>): same window.__env API as environments/threejs/runtime/core.js
    if (harnessOn && window.__installHarness) {
      dismissModal(); setHud(false); setFirstPerson(true);
      const cop = () => world().cameraOperator;
      window.__installHarness({
        renderer: world().renderer, camera: world().camera,
        getPos: () => player().position.toArray(),
        getYaw: () => cop().theta * Math.PI / 180,
        getPitch: () => -cop().phi * Math.PI / 180,
        setView: (yaw, pitch) => { cop().theta = yaw * 180 / Math.PI; cop().phi = Math.max(-80, Math.min(80, -pitch * 180 / Math.PI)); },
        keyDown: (code) => document.dispatchEvent(new KeyboardEvent('keydown', { code, key: code, bubbles: true })),
        keyUp: (code) => document.dispatchEvent(new KeyboardEvent('keyup', { code, key: code, bubbles: true })),
        speed: 1.6, spawn: { pos: SPAWN_DEFAULT, yawDeg: 0 },   // yaw 0 = facing -z (north along the strip)
        teleport: (x, y, z) => window.BenchmarkWorld.teleport(x, y, z),
        resetCount: () => state.resets || 0,
        config: hcfg || { name: q.get('config') || 'airfield' }, bugAnswer, film: window.__harnessFilmFromQuery(q),
        meta: { renderer: 'webgl (airfield page)', three: T.REVISION },
      });
    }
    const status = document.getElementById('offline-status');
    if (status) status.style.display = 'none';
    if (/benchmark|noui/.test(location.hash + location.search)) { dismissModal(); setHud(false); }   // noui: the review site's clean view
    // the review site (?bug=&noui=1) starts where the harness starts: on the open tarmac just north of the stone gate,
    // facing north - the case rubrics give every direction from there (QA 2026-09-15: reviewers used to start at the
    // game's native spawn 3.5 m south of the gate, so "from the start" pointed the wrong way)
    if (/noui/.test(location.search)) { setFirstPerson(true); window.BenchmarkWorld.teleport(SPAWN_DEFAULT[0], SPAWN_DEFAULT[1], SPAWN_DEFAULT[2]); window.BenchmarkWorld.setView(0, 12); }
    log('ready', JSON.stringify(state));
  }
  main().catch((e) => { state.errors.push(String(e)); log('failed', e); });
})();
