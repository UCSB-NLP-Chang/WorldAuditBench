/* environments/threejs/runtime/core.js - scene-agnostic rendering/physics/interaction/agent API. No UI.
 *
 * Entry: initEnv({ configUrl, seed, agentMode, fx })
 *   fx (optional, provided by human.html): { toast(msg), fade(), prompt(txt), hud(state), progress(msg) }
 *
 * Two deliberate departures from the prototype (reference/buggy-world.html):
 *  1. Virtual clock simT: all timing (door delays, animations, interact frame
 *     sampling, wait) accumulates clamped dt instead of wall time, so behavior
 *     does not drift under slow rendering.
 *  2. Agent forward/back are distance-targeted (per-frame displacement
 *     integration, early return on stall) instead of wall-clock sleeps -
 *     blocked semantics decouple from render speed.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { MeshBVH, StaticGeometryGenerator } from 'three-mesh-bvh';
import { buildSceneEntry, buildObject, finalizeColliders } from './scenes.js';
import { applyBugs } from './bugs.js';

export const EYE = 1.7, GRAVITY = 28, JUMP = 10, SPEED = 5.2;
// capsule radius: config.player.radius may override (house suite uses 0.22 - a 0.32 capsule
// cannot pass 0.5-0.6 m gaps between furniture, which reads as a fake "invisible wall")
export let RADIUS = 0.32;

/* ── seeded RNG (mulberry32) ── */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export async function initEnv(opts = {}) {
  const fx = opts.fx || {};
  const progress = m => { fx.progress?.(m); };
  const agentMode = !!opts.agentMode;

  progress('loading config...');
  const cfgResp = await fetch(opts.configUrl);
  if (!cfgResp.ok) throw new Error(`config fetch failed: ${opts.configUrl} ${cfgResp.status}`);
  const config = await cfgResp.json();
  const seed = (opts.seed ?? config.seed ?? 1) >>> 0;
  if (config.player?.radius) RADIUS = config.player.radius;
  // optional playable-area clamp {minX,maxX,minZ,maxZ} (house: keep the agent indoors)
  const bounds = config.bounds || null;
  const rng = mulberry32(seed);

  /* -- renderer basics -- */
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  document.body.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x9db8d4);
  const camera = new THREE.PerspectiveCamera(72, innerWidth / innerHeight, 0.05, 600);
  camera.rotation.order = 'YXZ';
  scene.add(camera);   // allow camera children (corrupted_frame tint overlay etc.)
  scene.add(new THREE.HemisphereLight(0xc4d8ee, 0x35302a, 1.3));
  const sun = new THREE.DirectionalLight(0xffeedd, 3);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0008;
  scene.add(sun, sun.target);
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;

  let rendererStr = 'unknown';
  try {
    const gl = renderer.getContext();
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    rendererStr = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
  } catch (e) { /* keep unknown */ }

  /* -- materials -- */
  const MAT = {
    wood: new THREE.MeshStandardMaterial({ color: 0x8a5a33, roughness: .75 }),
    woodDark: new THREE.MeshStandardMaterial({ color: 0x5b3a1e, roughness: .8 }),
    iron: new THREE.MeshStandardMaterial({ color: 0x2c2f34, metalness: .85, roughness: .4 }),
    stone: new THREE.MeshStandardMaterial({ color: 0x8d8578, roughness: .95 }),
    dark: new THREE.MeshStandardMaterial({ color: 0x0b0c0e, roughness: 1 }),
    gem: new THREE.MeshStandardMaterial({ color: 0x35e0ff, emissive: 0x1899bb, emissiveIntensity: 1.2, roughness: .15, metalness: .3 }),
  };

  /* -- sim clock (declared before world build: ctx.after/simT usable during build) -- */
  let simT = 0;
  const simWaiters = [];   // {at, res}
  let agentOn = false;
  let ready = false;

  /* -- world state -- */
  const worldMeshes = [];   // static meshes in the BVH
  const extras = [];        // {box, activeFn, label, hcolor} invisible/dynamic AABB colliders
  const interactables = []; // {meshes:[], prompt(), use()}
  const portalList = [];
  const updaters = [];      // per-frame updaters (sim-time step)
  // Observation v2: fixed sim-dt film strip (PLAN-temporal-obs.md). null = off (v1 single-frame)
  const film = opts.film ? {
    dt: opts.film.dt ?? 0.3, maxFrames: opts.film.maxFrames ?? 8,
    w: opts.film.w ?? 480, h: opts.film.h ?? 300,
  } : null;

  const ctx = {
    THREE, scene, camera, renderer, MAT, config, rng, agentMode,
    worldMeshes, extras, interactables, updaters,
    doors: new Map(), levers: new Map(), gems: new Map(), chests: new Map(),
    portals: new Map(), portalList,
    occluders: [],            // non-BVH meshes that occlude the interaction ray (door panels/gate bars/solid objects)
    noOcclusionFor: new Set(), // ownerIds exempted by the interact_through_wall bug
    targets: {}, anchors: {},
    gemsCollected: 0, totalGems: 0,
    simT: () => simT,
    after: (sec, fn) => { simWaiters.push({ at: simT + sec, res: fn }); },
    fx, progress,
    loader: null, // assigned below
  };

  ctx.addUpdater = function (id, fn) { updaters.push({ id, fn, frozen: false }); };
  /* bug-manifestation event log: ground truth for exposure-tier scoring (never in prompts) */
  ctx.bugEvents = [];
  ctx.logEvent = (type, extra = {}) => { ctx.bugEvents.push({ t: +simT.toFixed(2), type, ...extra }); };
  ctx.freezeUpdaters = function (id) {
    let n = 0;
    for (const u of updaters) if (u.id === id) { u.frozen = true; n++; }
    return n;
  };
  ctx.box = function (w, h, d, mat, x, y, z, parent = scene, shadow = true) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    m.castShadow = m.receiveShadow = shadow;
    parent.add(m);
    return m;
  };
  ctx.aabbOf = function (o) { o.updateWorldMatrix(true, true); return new THREE.Box3().setFromObject(o); };
  ctx.addSolid = function (obj, label, activeFn = () => true, hcolor = 0x556677) {
    const e = { box: ctx.aabbOf(obj), activeFn, label, hcolor };
    extras.push(e);
    return e;
  };
  ctx.addSolidBox = function (box, label, activeFn = () => true, hcolor = 0x556677) {
    const e = { box, activeFn, label, hcolor };
    extras.push(e);
    return e;
  };

  /* standable-floor scan (grid raycast + normal + headroom test) */
  ctx.floorPoints = function (model, bbox) {
    const pts = [], rc = new THREE.Raycaster();
    const down = new THREE.Vector3(0, -1, 0), up = new THREE.Vector3(0, 1, 0);
    const c = bbox.getCenter(new THREE.Vector3()), N = 9;
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
      const x = THREE.MathUtils.lerp(bbox.min.x + .8, bbox.max.x - .8, i / (N - 1));
      const z = THREE.MathUtils.lerp(bbox.min.z + .8, bbox.max.z - .8, j / (N - 1));
      rc.set(new THREE.Vector3(x, bbox.max.y - .05, z), down);
      for (const h of rc.intersectObject(model, true)) {
        const n = h.face.normal.clone().transformDirection(h.object.matrixWorld);
        if (n.y < .65) continue;
        rc.set(h.point.clone().add(new THREE.Vector3(0, .2, 0)), up);
        const head = rc.intersectObject(model, true)[0];
        if (head && head.distance < 2.0) continue;
        pts.push({ p: h.point.clone(), d: Math.hypot(h.point.x - c.x, h.point.z - c.z) });
        break;
      }
    }
    pts.sort((a, b) => a.d - b.d);
    return pts;
  };

  /* Position DSL:
     [x,y,z]                                   absolute coordinates
     {scene, local:[x,z], dy}                  procedural-scene local coords (corridor/vault)
     {scene, floor:i|'highest', dx,dz,dy}      gltf-scene standable points
     {scene, spawnOffset:[dx,dz], dy, snap}    offset from spawn (snap: raycast down to floor) */
  ctx.resolvePos = function (spec) {
    if (Array.isArray(spec)) return new THREE.Vector3(...spec);
    const a = ctx.anchors[spec.scene];
    if (!a) throw new Error(`resolvePos: unknown scene '${spec.scene}'`);
    let p;
    if (spec.local) {
      p = a.local(spec.local[0], spec.local[1]);
    } else if (spec.floor !== undefined) {
      const pts = a.floorPts;
      if (!pts?.length) throw new Error(`scene '${spec.scene}' has no floorPts`);
      const src = spec.floor === 'highest'
        ? [...pts].sort((x, y) => y.p.y - x.p.y)[0]
        : pts[Math.min(spec.floor, pts.length - 1)];
      p = src.p.clone();
      p.x += spec.dx || 0; p.z += spec.dz || 0;
    } else if (spec.spawnOffset) {
      p = a.spawn.pos.clone();
      p.x += spec.spawnOffset[0]; p.z += spec.spawnOffset[1];
      if (spec.snap) {
        const rc = new THREE.Raycaster(new THREE.Vector3(p.x, p.y + 2, p.z), new THREE.Vector3(0, -1, 0));
        const hit = rc.intersectObjects(worldMeshes, false)[0];
        if (hit) p.y = hit.point.y;
      }
    } else throw new Error(`resolvePos: bad spec ${JSON.stringify(spec)}`);
    p.y += spec.dy || 0;
    return p;
  };
  ctx.registerTarget = (id, pos) => { ctx.targets[id] = [+pos.x.toFixed(2), +pos.y.toFixed(2), +pos.z.toFixed(2)]; };

  /* ── glTF loader ── */
  const draco = new DRACOLoader().setDecoderPath('/assets/vendor/draco/');
  ctx.loader = new GLTFLoader().setDRACOLoader(draco);

  /* -- BVH collision -- */
  let bvhGeom = null;
  function buildBVH() {
    scene.updateMatrixWorld(true);
    const gen = new StaticGeometryGenerator(worldMeshes);
    gen.attributes = ['position'];
    bvhGeom = gen.generate();
    bvhGeom.boundsTree = new MeshBVH(bvhGeom);
  }
  const seg = new THREE.Line3(new THREE.Vector3(0, RADIUS, 0), new THREE.Vector3(0, EYE, 0));
  const vel = new THREE.Vector3();
  let onFloor = false, flying = false;
  const _box = new THREE.Box3(), _t = new THREE.Vector3(), _c = new THREE.Vector3(),
    _s = new THREE.Line3(), _v = new THREE.Vector3();
  ctx.collisionHoles = [];   // Box3 regions where baked-BVH contacts are ignored (floor_hole bug)
  function collideBVH() {
    if (!bvhGeom) return;
    _s.copy(seg);
    _box.makeEmpty(); _box.expandByPoint(_s.start); _box.expandByPoint(_s.end);
    _box.min.addScalar(-RADIUS); _box.max.addScalar(RADIUS);
    bvhGeom.boundsTree.shapecast({
      intersectsBounds: b => b.intersectsBox(_box),
      intersectsTriangle: tri => {
        const d = tri.closestPointToSegment(_s, _t, _c);
        if (d < RADIUS) {
          if (ctx.collisionHoles.length && ctx.collisionHoles.some(h => h.containsPoint(_t))) return;
          const dir = _c.sub(_t).normalize();
          // debug hook (harness verification only): window.__dbgPush = [] records every push of a frame
          if (window.__dbgPush) window.__dbgPush.push({ d: +d.toFixed(4), push: dir.clone().multiplyScalar(RADIUS - d).toArray().map(v => +v.toFixed(4)), tri: [tri.a.toArray(), tri.b.toArray(), tri.c.toArray()].map(a => a.map(v => +v.toFixed(3))), seg: [_s.start.toArray().map(v => +v.toFixed(3)), _s.end.toArray().map(v => +v.toFixed(3))] });
          _s.start.addScaledVector(dir, RADIUS - d);
          _s.end.addScaledVector(dir, RADIUS - d);
        }
      }
    });
    seg.copy(_s);
  }
  function collideBox(b) {
    let grounded = false;
    for (let it = 0; it < 2; it++) for (const t of [0, .5, 1]) {
      seg.at(t, _v);
      const q = _v.clone().clamp(b.min, b.max);
      const d = _v.clone().sub(q), L = d.length();
      if (L > 1e-9 && L < RADIUS) {
        d.multiplyScalar((RADIUS - L) / L);
        seg.start.add(d); seg.end.add(d);
        if (d.y > .001 && d.y / d.length() > .6) grounded = true;
      } else if (L <= 1e-9) {
        const pen = [
          { a: 'x', v: _v.x - b.min.x + RADIUS, s: -1 }, { a: 'x', v: b.max.x - _v.x + RADIUS, s: 1 },
          { a: 'y', v: _v.y - b.min.y + RADIUS, s: -1 }, { a: 'y', v: b.max.y - _v.y + RADIUS, s: 1 },
          { a: 'z', v: _v.z - b.min.z + RADIUS, s: -1 }, { a: 'z', v: b.max.z - _v.z + RADIUS, s: 1 },
        ].sort((p, q) => p.v - q.v)[0];
        const push = new THREE.Vector3(); push[pen.a] = pen.v * pen.s;
        seg.start.add(push); seg.end.add(push);
        if (pen.a === 'y' && pen.s === 1) grounded = true;
      }
    }
    return grounded;
  }

  /* -- movement -- */
  const keys = {};                 // human input (written by human.html)
  ctx.keys = keys;
  let spawnPos = new THREE.Vector3(0, 0, 0), spawnYaw = 0;
  let worldBox = new THREE.Box3();
  let respawnedFlag = false, teleportedFlag = false;
  let moveReq = null;              // {sign, remaining, stall, deadline, resolve}

  function respawn() {
    if (ready) ctx.logEvent('respawn', { from: seg.end.toArray().map(v => +v.toFixed(2)) });
    seg.start.set(spawnPos.x, spawnPos.y + RADIUS + .05, spawnPos.z);
    seg.end.set(spawnPos.x, spawnPos.y + EYE + .05, spawnPos.z);
    vel.set(0, 0, 0);
    camera.position.copy(seg.end);
    camera.rotation.set(0, spawnYaw, 0);
    respawnedFlag = true;
  }
  ctx.respawn = respawn;
  ctx.setFlying = f => { flying = f; vel.set(0, 0, 0); };
  ctx.isFlying = () => flying;
  // review helper (human entry / bug picker): put the player at (x, floorY, z) looking along yaw (radians, 0 = -z)
  ctx.teleportTo = (x, y, z, yaw) => {
    seg.start.set(x, y + RADIUS + .05, z); seg.end.set(x, y + EYE + .05, z); vel.set(0, 0, 0);
    camera.position.copy(seg.end); if (yaw !== undefined) { camera.rotation.set(0, yaw, 0); }
  };
  ctx.playerPos = () => seg.end.clone();

  const dirv = new THREE.Vector3();
  function fwd() { camera.getWorldDirection(dirv); dirv.y = 0; return dirv.normalize(); }
  function side() { camera.getWorldDirection(dirv); dirv.y = 0; dirv.normalize().cross(camera.up); return dirv; }

  function stepPlayer(dt) {
    const boost = (keys['ShiftLeft'] || keys['ShiftRight']) ? 2.1 : 1;
    if (flying) {  // human-only
      const s = SPEED * 3 * boost * dt, mv = new THREE.Vector3();
      if (keys['KeyW']) mv.add(camera.getWorldDirection(dirv).clone());
      if (keys['KeyS']) mv.sub(camera.getWorldDirection(dirv).clone());
      if (keys['KeyA']) mv.sub(side().clone());
      if (keys['KeyD']) mv.add(side().clone());
      if (keys['Space']) mv.y += 1;
      if (mv.lengthSq()) mv.normalize().multiplyScalar(s);
      seg.start.add(mv); seg.end.add(mv);
      camera.position.copy(seg.end);
      return;
    }
    const wish = new THREE.Vector3();
    let speed = SPEED;
    if (moveReq) {
      wish.copy(fwd()).multiplyScalar(moveReq.sign);
      speed = Math.min(SPEED, moveReq.speedCap ?? SPEED);  // final-frame speed cap -> exact stop at target distance
    } else {
      if (keys['KeyW']) wish.add(fwd().clone());
      if (keys['KeyS']) wish.sub(fwd().clone());
      if (keys['KeyA']) wish.sub(side().clone());
      if (keys['KeyD']) wish.add(side().clone());
    }
    if (wish.lengthSq()) wish.normalize().multiplyScalar(speed * boost * (onFloor ? 1 : .55));
    if (onFloor && keys['Space'] && !moveReq) vel.y = JUMP;
    vel.y -= GRAVITY * dt;

    const before = seg.end.clone();
    seg.start.addScaledVector(wish, dt).addScaledVector(vel, dt);
    seg.end.addScaledVector(wish, dt).addScaledVector(vel, dt);
    collideBVH();
    let boxGround = false;
    for (const ex of extras) if (ex.activeFn()) boxGround = collideBox(ex.box) || boxGround;

    const delta = seg.end.clone().sub(before);
    const corr = delta.clone().addScaledVector(vel, -dt).addScaledVector(wish, -dt);
    onFloor = boxGround || corr.y > Math.max(1e-4, Math.abs(dt * vel.y) * .25);
    if (onFloor && vel.y < 0) vel.y = 0;
    else if (corr.y < -1e-4 && vel.y > 0) vel.y = 0;   // hit the ceiling
    vel.x = 0; vel.z = 0;                              // vel carries only the vertical component (PLAN pitfall #9)
    if (bounds) {
      const cx = Math.min(Math.max(seg.end.x, bounds.minX), bounds.maxX);
      const cz = Math.min(Math.max(seg.end.z, bounds.minZ), bounds.maxZ);
      if (cx !== seg.end.x || cz !== seg.end.z) {
        const dx = cx - seg.end.x, dz = cz - seg.end.z;
        seg.start.x += dx; seg.start.z += dz; seg.end.x += dx; seg.end.z += dz;
        // boundary notice only where the world suggests an exit (config.notice zones, e.g. the house doors);
        // an enclosed scene without zones never nags
        const zones = config.notice || [];
        if (zones.some(zn => Math.hypot(seg.end.x - zn.x, seg.end.z - zn.z) < (zn.r || 0.8))) boundaryNotice();
      }
    }
    camera.position.copy(seg.end);
    if (seg.end.y < worldBox.min.y - 20) respawn();
  }

  /* -- crosshair interaction -- */
  const aimRay = new THREE.Raycaster(); aimRay.far = 3.6;
  let aimedInter = null;
  const interMeshMap = new Map();
  function refreshInterMap() {
    interMeshMap.clear();
    for (const it of interactables) for (const m of it.meshes) interMeshMap.set(m, it);
  }
  const _occP = new THREE.Vector3();
  function updateAim() {
    const n = interactables.reduce((a, i) => a + i.meshes.length, 0);
    if (interMeshMap.size !== n) refreshInterMap();
    aimRay.setFromCamera({ x: 0, y: 0 }, camera);
    const hit = aimRay.intersectObjects([...interMeshMap.keys()].filter(m => m.visible), false)[0];
    let inter = hit ? interMeshMap.get(hit.object) : null;
    // Interaction-ray occlusion: targets behind solid walls/doors/gates/objects are unreachable (interact_through_wall bug can exempt)
    if (inter && !ctx.noOcclusionFor.has(inter.ownerId)) {
      let occD = 1e9;
      const w = aimRay.intersectObjects(worldMeshes, false)[0];
      if (w) occD = w.distance;
      const others = ctx.occluders.filter(m => m.visible && !inter.meshes.includes(m));
      const o = aimRay.intersectObjects(others, false)[0];
      if (o && o.distance < occD) occD = o.distance;
      for (const ex of extras) {
        if (!ex.activeFn()) continue;
        const own = ex.label && ex.label.includes(':') ? ex.label.split(':')[1] : null;
        if (own && inter.ownerId && (own === inter.ownerId || own.startsWith(inter.ownerId + '_'))) continue;
        if (aimRay.ray.intersectBox(ex.box, _occP)) {
          const dd = _occP.distanceTo(aimRay.ray.origin);
          if (dd < occD) occD = dd;
        }
      }
      if (occD < hit.distance - 0.05) inter = null;
    }
    aimedInter = inter;
    fx.prompt?.(aimedInter ? aimedInter.prompt() : '');
    return aimedInter;
  }
  ctx.useAimed = () => { updateAim(); if (aimedInter) { aimedInter.use(); return true; } return false; };

  /* -- portals -- */
  function teleportNow(from) {
    const to = ctx.portals.get(from.partnerId);
    if (!to) return;
    fx.fade?.();
    const p = to.center.clone().addScaledVector(to.exitDir, 1.4);
    seg.start.set(p.x, p.y + RADIUS + .05, p.z);
    seg.end.set(p.x, p.y + EYE + .05, p.z);
    vel.set(0, 0, 0);
    camera.position.copy(seg.end);
    camera.rotation.y = Math.atan2(-to.exitDir.x, -to.exitDir.z) + Math.PI;  // matches the prototype
    to.armed = false;   // disarm the destination portal until the player steps away
    teleportedFlag = true;
  }

  /* -- door/gate updates (unified records, sim-clock timing) -- */
  function updateDoors(dt) {
    for (const d of ctx.doors.values()) {
      if (simT >= d.pendingAt) {
        const was = d.effOpen;
        d.effOpen = d.wantOpen; d.pendingAt = Infinity;
        if (d.effOpen && !was) d.openedAt = simT;
      }
      // bug: door_autoclose - closes by itself a few seconds after opening
      if (d.autoCloseMs && d.effOpen && simT - (d.openedAt ?? simT) > d.autoCloseMs / 1000) {
        d.wantOpen = false; d.effOpen = false;
      }
      let visTarget = d.behavior === 'phantom' ? 0 : (d.effOpen ? 1 : 0);
      if (d.interruptT !== undefined) visTarget = Math.min(visTarget, d.interruptT);  // bug: interrupted animation
      const speed = (d.kind === 'hinged' ? 0.6 : 1.1) / (d.speedFactor ?? 1);         // bug: accelerated animation
      d.t += Math.sign(visTarget - d.t) * Math.min(dt / speed, Math.abs(visTarget - d.t));
      if (d.kind === 'hinged') {
        for (const p of d.panels) p.group.rotation.y = p.sign * d.t * 1.5;
      } else {
        d.group.position.y = d.baseY + d.t * d.height * 0.92;
      }
    }
    for (const lv of ctx.levers.values())
      lv.arm.rotation.z = THREE.MathUtils.lerp(lv.arm.rotation.z, lv.pulled ? -.6 : .6, Math.min(1, dt * 10));
  }

  function updateWorld(dt) {
    updateDoors(dt);
    for (const u of updaters) {
      if (typeof u === 'function') u(dt);          // back-compat with bare-function updaters
      else if (!u.frozen) u.fn(dt);
    }
    // portal triggers
    const feet = seg.start;
    for (const p of portalList) {
      p.ring.rotation.z += dt * .8;
      const d = Math.hypot(feet.x - p.center.x, feet.z - p.center.z);
      const dy = Math.abs(feet.y - p.center.y);
      if (!p.armed) { if (d > p.radius + .6) p.armed = true; continue; }
      if (d < p.radius && dy < 1.4) { p.armed = false; teleportNow(p); }
    }
  }

  /* ============ world build (config-driven) ============ */
  for (const sc of config.scenes) {
    progress(`building scene ${sc.id}...`);
    await buildSceneEntry(ctx, sc);
  }
  progress('placing objects...');
  for (const ob of (config.objects || [])) buildObject(ctx, ob);
  progress('injecting bugs...');
  applyBugs(ctx, config.bugs || []);
  // bugs may have mutated object transforms -> register solid AABB colliders only now
  finalizeColliders(ctx);
  // named target points beyond objects (used by the harness for success checks)
  for (const [id, spec] of Object.entries(config.targets || {}))
    ctx.registerTarget(id, ctx.resolvePos(spec));

  /* spawn */
  const spawnCfg = config.spawn || { scene: config.scenes[0].id };
  const sa = ctx.anchors[spawnCfg.scene];
  if (spawnCfg.pos) spawnPos.copy(ctx.resolvePos(spawnCfg.pos));
  else spawnPos.copy(sa.spawn.pos);
  spawnYaw = (spawnCfg.yawDeg ?? sa.spawn.yawDeg ?? 0) * Math.PI / 180;

  /* lighting: sun and shadow frustum sized from the first scene's bbox (as in the prototype) */
  const a0 = ctx.anchors[config.scenes[0].id];
  const sC = a0.box.getCenter(new THREE.Vector3());
  sun.position.set(sC.x - 12, a0.box.max.y + 25, sC.z + 8);
  sun.target.position.copy(sC);
  const r = Math.max(...a0.box.getSize(new THREE.Vector3()).toArray()) / 2 + 6;
  Object.assign(sun.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: .1, far: 120 });
  sun.shadow.camera.updateProjectionMatrix();

  progress('building collision (BVH)...');
  await new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res)));
  buildBVH();
  worldBox = new THREE.Box3().setFromObject(scene);
  respawn();
  respawnedFlag = false;

  /* ============ main loop (sim clock) ============ */
  const clock = new THREE.Clock();
  const humanActive = () => !agentMode && document.pointerLockElement === document.body;

  /* Turn-based world: in agent mode sim time flows ONLY inside an action's execution
     window (advancing=true). While the policy deliberates the world is frozen - rendering
     continues but simT, physics, updaters and waiters do not advance. */
  let advancing = false;
  renderer.setAnimationLoop(() => {
    const dtRaw = Math.min(.05, clock.getDelta());
    if (ready && ((agentOn && advancing) || humanActive())) {
      simT += dtRaw;
      const startPos = seg.end.clone();
      if (moveReq)
        moveReq.speedCap = Math.min(SPEED, Math.max(moveReq.remaining, 0) / Math.max(dtRaw, 1e-4));
      const N = 3, dt = dtRaw / N;
      for (let i = 0; i < N; i++) stepPlayer(dt);
      if (moveReq) {
        const prog = Math.hypot(seg.end.x - startPos.x, seg.end.z - startPos.z);
        moveReq.remaining -= prog;
        moveReq.stall = prog < 0.004 ? moveReq.stall + 1 : 0;
        // no stall early-return in film mode: the evidence of blockage is pushing forward while the view stays frozen
        const stalled = !moveReq.noStallAbort && moveReq.stall >= 10;
        if (moveReq.remaining <= 0.01 || stalled || simT > moveReq.deadline) {
          const r = moveReq; moveReq = null; r.resolve();
        }
      }
      updateWorld(dtRaw);
      if (!agentMode) updateAim();
      fx.hud?.(_state());
      for (let i = simWaiters.length - 1; i >= 0; i--)
        if (simT >= simWaiters[i].at) simWaiters.splice(i, 1)[0].res();
    }
    renderer.render(scene, camera);
  });
  addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });

  /* ============ agent API ============ */
  const flags = [];
  const simSleep = sec => new Promise(res => simWaiters.push({ at: simT + sec, res }));
  const nextFrames = (n = 2) => new Promise(res => {
    const step = k => k <= 0 ? res() : requestAnimationFrame(() => step(k - 1));
    step(n);
  });
  // boundary notice (1.5 sim-seconds): the human page shows a DOM overlay (fx.boundary); the agent only sees the
  // canvas, so the same notice is composited into the captured frames while it is showing
  let noticeUntil = -1;
  function boundaryNotice() { noticeUntil = simT + 1.5; fx.boundary?.(); }
  const noticeOn = () => simT < noticeUntil;
  function stampNotice(g, w, h) {
    const bh = Math.round(h * 0.17);
    g.fillStyle = 'rgba(58,4,10,0.88)'; g.fillRect(0, 0, w, bh);
    g.fillStyle = '#ff5d62'; g.font = `bold ${Math.round(h * 0.07)}px sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('EDGE OF THE EXPLORABLE AREA', w / 2, bh * 0.36);
    g.fillStyle = '#ffecec'; g.font = `${Math.round(h * 0.045)}px sans-serif`;
    g.fillText('Turn around and keep exploring inside', w / 2, bh * 0.74);
  }
  let fullCanvas = null;
  function fullFrame() {
    const c = renderer.domElement;
    if (!noticeOn()) return c.toDataURL('image/jpeg', 0.85);
    if (!fullCanvas) fullCanvas = document.createElement('canvas');
    fullCanvas.width = c.width; fullCanvas.height = c.height;
    const g = fullCanvas.getContext('2d'); g.drawImage(c, 0, 0); stampNotice(g, fullCanvas.width, fullCanvas.height);
    return fullCanvas.toDataURL('image/jpeg', 0.85);
  }
  async function grabFrame() {
    await nextFrames(2);
    return fullFrame();
  }
  let smallCanvas = null;
  function smallFrame() {   // low-res film frame: synchronous capture of the current view
    if (!smallCanvas) {
      smallCanvas = document.createElement('canvas');
      smallCanvas.width = film.w; smallCanvas.height = film.h;
    }
    const g = smallCanvas.getContext('2d'); g.drawImage(renderer.domElement, 0, 0, film.w, film.h);
    if (noticeOn()) stampNotice(g, film.w, film.h);
    return smallCanvas.toDataURL('image/jpeg', 0.7);
  }
  function _state() {
    return {
      pos: seg.end.toArray().map(v => +v.toFixed(2)),
      yaw: +((THREE.MathUtils.euclideanModulo(camera.rotation.y, Math.PI * 2)) * 180 / Math.PI).toFixed(1),
      pitch: +(camera.rotation.x * 180 / Math.PI).toFixed(1),
      gems: ctx.gemsCollected, flags: flags.length,
    };
  }

  window.__ctx = ctx;   // debug handle for harness verification scripts only
  window.__env = {
    get ready() { return ready; },
    meta: { config: config.name || opts.configUrl, renderer: rendererStr, agentMode, three: THREE.REVISION, seed },
    enable() { agentOn = true; fx.agentEnabled?.(); },
    state: _state,
    targets() { return { ...ctx.targets }; },
    flags() { return flags.slice(); },
    /* privileged probe: harness verification only, never enters prompts */
    probe() {
      const doors = {};
      for (const [id, d] of ctx.doors) doors[id] = { want: d.wantOpen, eff: d.effOpen, t: +d.t.toFixed(3) };
      const levers = {};
      for (const [id, l] of ctx.levers) levers[id] = l.pulled;
      const chests = {};
      for (const [id, c] of ctx.chests) chests[id] = c.open;
      return {
        simT: +simT.toFixed(3), onFloor, doors, levers, chests,
        gems: { collected: ctx.gemsCollected, total: ctx.totalGems },
        pos: seg.end.toArray().map(v => +v.toFixed(3)),
        bugEvents: ctx.bugEvents.slice(),
      };
    },
    /* Continuous drive (VLA explorer): hold keys + mouse deltas for one fixed sim step.
       a = {keys:['KeyW',...], mouseDx, mouseDy, click}. Same pause principle: sim time
       flows only inside the tick. Mouse sensitivity matches human mode (rad = px/600). */
    async tick(a = {}, dtMs = 50) {
      if (!agentOn) throw new Error('call enable() first');
      const before = seg.end.clone();
      respawnedFlag = false; teleportedFlag = false;
      for (const k of Object.keys(keys)) keys[k] = false;
      for (const k of (a.keys || [])) keys[k] = true;
      camera.rotation.y -= (a.mouseDx || 0) / 600;
      camera.rotation.x = Math.max(-Math.PI / 2, Math.min(Math.PI / 2,
        camera.rotation.x - (a.mouseDy || 0) / 600));
      if (a.click) { updateAim(); ctx.useAimed(); }
      advancing = true;
      await simSleep(dtMs / 1000);
      advancing = false;
      for (const k of Object.keys(keys)) keys[k] = false;   // no holds leak into the paused world
      return {
        frame: fullFrame(),
        moved: +seg.end.distanceTo(before).toFixed(3),
        respawned: respawnedFlag,
        nEvents: ctx.bugEvents.length,
        ..._state(),
      };
    },
    /* Actions: {action:'forward'|'back',dist} {action:'turn',deg(+right)} {action:'look',deg(+down)}
             {action:'interact'} {action:'wait',ms} {action:'flag',note} */
    async act(a) {
      if (!agentOn) throw new Error('call enable() first');
      const before = seg.end.clone();
      const t0 = simT;
      // Fixed-tick decisions (agent/vlm/ harness): maxSec cuts the action short, holdSec keeps sim
      // time running (agent idle) until that much has elapsed since the action started.
      const maxSec = a.maxSec > 0 ? +a.maxSec : null;
      const holdSec = a.holdSec > 0 ? +a.holdSec : null;
      const capped = s => (maxSec != null ? Math.min(s, maxSec) : s);
      advancing = true;
      respawnedFlag = false; teleportedFlag = false;
      const frames = [], frameT = [];
      const filmFrames = [];
      let filming = false;
      const startFilm = (stride) => {     // sample low-res frames at fixed dt until stopFilm or cap
        if (!film) return;
        filming = true;
        (async () => {
          while (filming && filmFrames.length < film.maxFrames) {
            filmFrames.push({ t: +(simT - t0).toFixed(2), url: smallFrame() });
            await simSleep(stride);
          }
        })();
      };
      const stopFilm = () => { filming = false; };
      let interacted = false;
      const snap = async () => { const f = await grabFrame(); frames.push(f); frameT.push(+(simT - t0).toFixed(3)); };

      if (a.action === 'forward' || a.action === 'back') {
        const dist = Math.min(Math.max(a.dist ?? 1.5, .3), 4);
        startFilm(film ? film.dt : 0);
        await new Promise(resolve => {
          moveReq = { sign: a.action === 'forward' ? 1 : -1, remaining: dist, stall: 0,
                      noStallAbort: !!film,
                      deadline: maxSec != null ? Math.min(simT + dist / SPEED * 4 + 1, t0 + maxSec)
                                               : simT + dist / SPEED * 4 + 1, resolve };
        });
        stopFilm();
      } else if (a.action === 'turn') {
        camera.rotation.y -= (a.deg ?? 45) * Math.PI / 180;
        await simSleep(capped(Math.abs(a.deg ?? 45) / 120));   // natural duration at 120 deg/s
      } else if (a.action === 'look') {
        camera.rotation.x = Math.max(-1.3, Math.min(1.3, camera.rotation.x - (a.deg ?? 20) * Math.PI / 180));
        await simSleep(capped(Math.abs(a.deg ?? 20) / 120));
      } else if (a.action === 'interact') {
        interacted = ctx.useAimed();
        startFilm(film ? Math.max(film.dt, 2.8 / (film.maxFrames - 1)) : 0);
        if (maxSec == null) {
          await snap();               // t≈0
          await simSleep(0.7); await snap();   // t~0.7
          await simSleep(2.1);        // final frame t~2.8, late enough to reveal delayed mechanisms
        } else {
          // time-capped (tick decisions): no intermediate snapshots - each costs a couple of sim
          // frames and would overshoot the tick; the mechanism keeps running in later ticks
          await simSleep(capped(2.8));
        }
        stopFilm();
      } else if (a.action === 'wait') {
        const sec = capped(Math.min(a.ms ?? 1000, 5000) / 1000);
        startFilm(film ? Math.max(film.dt, sec / (film.maxFrames - 1)) : 0);
        await simSleep(sec);
        stopFilm();
      } else if (a.action === 'flag') {
        flags.push({ pos: seg.end.toArray().map(v => +v.toFixed(2)), note: a.note || '', simT: +simT.toFixed(2) });
      }
      // hold: the decision tick lasts holdSec regardless of how long the action itself took
      if (holdSec != null)
        while (simT - t0 < holdSec - 1e-6) await simSleep(Math.min(0.05, holdSec - (simT - t0)));
      // settle: keep sim advancing until the player lands or respawns (e.g. walked onto a
      // collision hole and is mid-fall) - never freeze the world with the player airborne
      const settleT = simT + 6;
      while (!onFloor && !respawnedFlag && simT < settleT) await simSleep(0.12);
      advancing = false;
      await snap();
      return {
        frames, frameT, interacted,
        film: filmFrames,
        moved: +seg.end.distanceTo(before).toFixed(2),
        teleported: teleportedFlag, respawned: respawnedFlag,
        simElapsed: +(simT - t0).toFixed(3),
        ..._state(),
      };
    },
  };

  ready = true;
  progress('');
  return ctx;
}
