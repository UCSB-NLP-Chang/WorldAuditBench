// @ts-nocheck
// Wilderness bug catalogue (WL suite) + harness wiring for the benchmark build.  One mutation per case, selected
// with `?bug=wlXX-slug` (or the harness config's `bug`); same taxonomy as the SP / HS / WT / AF suites.  The world
// is chunk-streamed and instanced, so mutations are expressed as *watchers*: whenever an InstancedMesh holding the
// target placement appears (initial build or a LOD rebuild) the mutation is re-applied, and standalone copies
// ("detached" instances) survive chunk churn.  All carriers are picked by world position for the seed the
// configs fix (worldSeed 7), within ~35 m of the spawn.
import * as THREE from 'three';

const CAT = { geo: 'geometry-space', col: 'collision-physics', vis: 'visual-consistency', state: 'spatiotemporal-state', sem: 'semantics-logic' };

export function createBugRuntime(handles) {
  const { scene, world, actor: controller, camera } = handles;
  const terrain = world.terrain;
  const frameHooks = [];
  const watchers = [];
  const seen = new WeakSet();
  const extraColliders = [];
  const colliderFilters = [];
  const holes = [];
  let resets = 0;
  const spawn = { x: camera.position.x, z: camera.position.z };
  const t0 = performance.now();

  // --- colliders: air walls (extra cylinders) and ghost objects (filtered cylinders)
  const origNear = world.getCollidersNear.bind(world);
  world.getCollidersNear = (pos) => {
    let list = origNear(pos);
    for (const f of colliderFilters) list = list.filter(f);
    return extraColliders.length ? list.concat(extraColliders) : list;
  };
  // --- holes: the controller reads the ground through its private terrain field; swap in a proxy
  const proxyTerrain = {
    getMeshHeightAt: (x, z) => { for (const h of holes) if (Math.hypot(x - h.x, z - h.z) < h.r) return terrain.getMeshHeightAt(x, z) - 40; return terrain.getMeshHeightAt(x, z); },
    getHeightAt: (x, z) => terrain.getHeightAt(x, z),
    getNormalAt: (x, z, n) => terrain.getNormalAt(x, z, n),
  };
  controller.terrain = proxyTerrain;
  function respawn() { resets++; controller.spawnAt(spawn.x, spawn.z); }

  // --- instance watchers
  const M = new THREE.Matrix4(), P = new THREE.Vector3(), Q = new THREE.Quaternion(), S = new THREE.Vector3();
  function scanMesh(o) {
    if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
    const bb = o.geometry.boundingBox; o.updateWorldMatrix(true, false);
    for (let i = 0; i < o.count; i++) {
      o.getMatrixAt(i, M); const wm = M.clone().premultiply(o.matrixWorld); wm.decompose(P, Q, S);
      const h = (bb.max.y - bb.min.y) * S.y, w = Math.max(bb.max.x - bb.min.x, bb.max.z - bb.min.z) * Math.max(S.x, S.z);
      for (const wt of watchers) {
        if (!!wt.grass !== !!o.userData.isGrassTile) continue;
        if (Math.hypot(P.x - wt.x, P.z - wt.z) < wt.r && h >= (wt.minH || 0) && h <= (wt.maxH || 1e9) && w >= (wt.minW || 0)) wt.fn(o, i, M.clone(), P.clone(), { h, w, mat: o.material });
      }
    }
  }
  function scan() { scene.traverse((o) => { if (o.isInstancedMesh && !seen.has(o)) { seen.add(o); if (!o.userData.isGrassTile || watchers.some((w) => w.grass)) scanMesh(o); } }); }
  function watch(x, z, r, opts, fn) { watchers.push({ x, z, r, ...opts, fn }); scene.traverse((o) => { if (o.isInstancedMesh && seen.has(o) && (!o.userData.isGrassTile || opts.grass)) scanMeshFor(o, watchers[watchers.length - 1]); }); }
  function scanMeshFor(o, wt) { const keep = watchers.slice(); watchers.length = 0; watchers.push(wt); scanMesh(o); watchers.length = 0; watchers.push(...keep); }
  const zero = new THREE.Matrix4().makeScale(0, 0, 0);
  function hideInstance(mesh, i) { mesh.setMatrixAt(i, zero); mesh.instanceMatrix.needsUpdate = true; }
  function setInstance(mesh, i, m) { mesh.setMatrixAt(i, m); mesh.instanceMatrix.needsUpdate = true; }
  function cloneMaterial(mat) {
    const c = mat.clone();
    if (mat.onBeforeCompile) c.onBeforeCompile = mat.onBeforeCompile;
    if (mat.customProgramCacheKey) c.customProgramCacheKey = mat.customProgramCacheKey;
    c.needsUpdate = true; return c;
  }
  // standalone copy of an instance (kept across chunk rebuilds; the instance itself is zeroed every time it reappears)
  function detach(mesh, i, localM, material) {
    const wm = localM.clone().premultiply(mesh.matrixWorld);
    const solo = new THREE.Mesh(mesh.geometry, material || mesh.material);
    solo.matrixAutoUpdate = false; solo.matrix.copy(wm); solo.matrixWorld.copy(wm);
    solo.castShadow = mesh.castShadow; solo.receiveShadow = mesh.receiveShadow; solo.frustumCulled = false;
    scene.add(solo); return solo;
  }
  function terrainChunkAt(x, z) {
    let best = null;
    scene.traverse((o) => { if (best || !o.isMesh || o.isInstancedMesh || !o.geometry.attributes.aSplat) return; if (!o.geometry.boundingBox) o.geometry.computeBoundingBox(); const bb = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld); if (x >= bb.min.x && x <= bb.max.x && z >= bb.min.z && z <= bb.max.z) best = o; });
    return best;
  }
  const ctx = {
    THREE, scene, world, controller, camera, terrain, spawn, CAT,
    onFrame: (fn) => frameHooks.push(fn), watch, hideInstance, setInstance, detach, cloneMaterial, terrainChunkAt,
    addAirWall: (x0, z0, x1, z1, radius = 0.55) => { const n = Math.ceil(Math.hypot(x1 - x0, z1 - z0) / (radius * 1.6)); for (let k = 0; k <= n; k++) extraColliders.push({ x: x0 + (x1 - x0) * k / n, z: z0 + (z1 - z0) * k / n, radius }); },
    addCollider: (x, z, radius) => { const c = { x, z, radius }; extraColliders.push(c); return c; },
    removeCollidersNear: (x, z, r) => colliderFilters.push((c) => Math.hypot(c.x - x, c.z - z) > r),
    // terrain patch: drop the triangles of the rendered chunk inside a square (the analytic ground stays, so the walker
    // crosses the hole on invisible ground); re-applied whenever the chunk is rebuilt
    cutTerrainPatch: (x, z, half) => {
      const done = new WeakSet();
      frameHooks.push(() => {
        const chunk = ctx.terrainChunkAt(x, z); if (!chunk || done.has(chunk.geometry)) return;
        done.add(chunk.geometry);
        const g = chunk.geometry, pos = g.attributes.position, idx = g.index; if (!idx) return;
        const ox = chunk.position.x, oz = chunk.position.z; const arr = idx.array;
        const inside = (i) => Math.abs(pos.getX(i) + ox - x) < half && Math.abs(pos.getZ(i) + oz - z) < half;
        for (let t = 0; t < arr.length; t += 3) if (inside(arr[t]) && inside(arr[t + 1]) && inside(arr[t + 2])) { arr[t + 1] = arr[t]; arr[t + 2] = arr[t]; }
        idx.needsUpdate = true;
      });
    },
    // every grass tile whose centre is (cx, cz): scale each blade about its own base (re-applied on rebuilds)
    scaleGrassTile: (cx, cz, k) => {
      const done = new WeakSet();
      frameHooks.push(() => {
        scene.traverse((o) => {
          if (!o.isInstancedMesh || !o.userData.isGrassTile || done.has(o)) return;
          if (Math.abs(o.userData.grassCenterX - cx) > 0.5 || Math.abs(o.userData.grassCenterZ - cz) > 0.5) return;
          done.add(o);
          const S = new THREE.Matrix4().makeScale(k, k, k), M2 = new THREE.Matrix4();
          const n = o.userData.grassFullCount || o.count;
          for (let i = 0; i < n; i++) { o.getMatrixAt(i, M2); M2.multiply(S); o.setMatrixAt(i, M2); }
          o.instanceMatrix.needsUpdate = true; o.computeBoundingSphere();
        });
      });
    },
    addHole: (x, z, r) => holes.push({ x, z, r }),
    respawn, resets: () => resets,
    groundY: (x, z) => terrain.getMeshHeightAt(x, z),
  };
  // per-frame: watcher rescan (new chunk meshes) + behaviour hooks + hole respawn
  let falling = 0;
  handles.onBenchmarkFrame = () => {
    scan();
    const t = (performance.now() - t0) / 1000;
    for (const h of frameHooks) { try { h(t, camera); } catch (e) { console.warn('bug hook', e); frameHooks.splice(frameHooks.indexOf(h), 1); } }
    if (holes.length) {
      const p = camera.position; const inHole = holes.some((h) => Math.hypot(p.x - h.x, p.z - h.z) < h.r);
      if (inHole && p.y < terrain.getMeshHeightAt(p.x, p.z) - 3 && !falling) falling = performance.now();
      if (falling && performance.now() - falling > 1500) { falling = 0; respawn(); }
    }
  };
  return ctx;
}

// positions below are for worldSeed 7 (see tools/gen_fable_cases.py); each carrier is resolved by a watcher so the
// exact placement is taken from the live chunk data
const ROCK_A = { x: 5.0, z: 5.8 };        // 9.6 x 6 m boulder right next to the spawn
const ROCK_B = { x: 22.8, z: -8.9 };      // 8.7 x 7 m boulder up the slope to the north-east
const TREE_A = { x: -10.7, z: 6.2 };      // 23 m pine west of the spawn
const TREE_B = { x: -18.0, z: -10.7 };    // big tree north-west
const SHRUB_A = { x: 5.2, z: -14.7 };     // 2.5 m shrub north of the spawn
const SHRUB_B = { x: 18.9, z: -12.0 };    // shrub north-east
const SHRUB_C = { x: -12.5, z: 5.5 };     // shrub by the pine
const near = (a, b, r = 1.5) => Math.hypot(a.x - b.x, a.z - b.z) < r;
const rockOpts = { minH: 4, minW: 5 }, treeOpts = { minH: 10 }, shrubOpts = { minH: 1.5, maxH: 6 };

export const CATALOG = {
  // ---- geometry & space
  'wl01-float': (c) => {
    // the flat-ground boulder by the start, lifted 4 m (it sits 30% sunk, so ~2.5 m of air shows; review 2026-09-12:
    // the boulder on the 45-degree slope never looked airborne)
    // the boulder mesh is centred on its origin and mostly buried (only ~2 m of it shows): +7 m puts its lowest point ~3 m up
    c.watch(ROCK_A.x, ROCK_A.z, 2.5, rockOpts, (mesh, i, m) => { m.premultiply(new c.THREE.Matrix4().makeTranslation(0, 7.0, 0)); c.setInstance(mesh, i, m); });
    return { name: 'floating boulder', where: 'the big boulder right next to the start (turn round at the start: it is behind you, a few metres to the right) hovers about 3 m above the meadow with open air under it', at: [ROCK_A.x, c.groundY(ROCK_A.x, ROCK_A.z) + 6.0, ROCK_A.z], category: CAT.geo, extent_x: 3, extent_z: 3 };
  },
  'wl02-clip': (c) => {
    // the pine is tipped over 35 degrees AND sunk 3 m, so its trunk and lower branches go into the meadow and come out again
    // (review 2026-09-14: a merely lowered pine read as a small pine - trees on slopes sit partly buried anyway)
    c.watch(TREE_A.x, TREE_A.z, 2.5, treeOpts, (mesh, i, m, p) => {
      const tilt = new c.THREE.Matrix4().makeTranslation(p.x, p.y - 3.0, p.z).multiply(new c.THREE.Matrix4().makeRotationX(0.62)).multiply(new c.THREE.Matrix4().makeTranslation(-p.x, -p.y, -p.z));
      const W = mesh.matrixWorld;   // instance matrices are in the chunk group's frame: conjugate the world-space tilt
      c.setInstance(mesh, i, W.clone().invert().multiply(tilt).multiply(W).multiply(m));
    });
    return { name: 'sunken pine', where: 'the tall pine west of the start (about 12 m away) is tipped over at about 35 degrees and sunk into the ground - its trunk goes into the meadow and its lower branches stab through the grass, while every other tree stands upright on the ground', at: [TREE_A.x, c.groundY(TREE_A.x, TREE_A.z) + 4, TREE_A.z], category: CAT.geo };
  },
  'wl03-scale': (c) => {
    // one 24 m grass tile rendered at 4.5x: blades taller than a person, ending along straight tile edges (review
    // 2026-09-12: a big bush or tree passes as natural in this world; a sharply bounded patch of giant grass does not)
    c.scaleGrassTile(-12, 12, 4.5);
    return { name: 'giant grass patch', where: 'one square patch of the meadow south-west of the start is rendered at about four times normal scale - grass blades taller than a person, the patch ending abruptly along straight edges', at: [-6, c.groundY(-6, 6) + 1.5, 6], category: CAT.geo, extent_x: 10, extent_z: 10 };
  },
  // wl04-doublespawn retired 2026-09-16 (review round 3): with these low-poly boulders a doubled copy reads as one rock, and the copy has no collider.
  // ---- collision & physics
  'wl05-airwall': (c) => {
    c.addAirWall(-9, -12, 9, -12);
    return { name: 'invisible wall', where: 'an invisible barrier across the meadow about 12 m north of the start stops you although nothing is visible there', at: [0, c.groundY(0, -12) + 1, -12], category: CAT.col };
  },
  'wl06-hole': (c) => {
    c.addHole(9.0, -6.0, 2.4);
    return { name: 'hole in the ground', where: 'you fall straight through the solid-looking meadow at one spot north-east of the start and drop into darkness under the terrain, then respawn', at: [9.0, c.groundY(9, -6), -6.0], category: CAT.col };
  },
  'wl07-ghost': (c) => {
    c.removeCollidersNear(ROCK_A.x, ROCK_A.z, 6);
    return { name: 'no-collision boulder', where: 'the big boulder next to the start has no collision - you walk straight through it while other rocks and trees are solid', at: [ROCK_A.x, c.groundY(ROCK_A.x, ROCK_A.z) + 2.5, ROCK_A.z], category: CAT.col };
  },
  'wl08-jitter': (c) => {
    let tgt = null;
    c.watch(SHRUB_B.x, SHRUB_B.z, 2.0, shrubOpts, (mesh, i, m) => { tgt = { mesh, i, base: m.clone() }; });
    c.onFrame((t) => { if (!tgt) return; const m = tgt.base.clone().premultiply(new c.THREE.Matrix4().makeTranslation(Math.sin(t * 9) * 0.1, Math.sin(t * 13) * 0.03, Math.cos(t * 11) * 0.1)); c.setInstance(tgt.mesh, tgt.i, m); });
    return { name: 'trembling shrub', where: 'a bush up the slope north-east of the start (about 20 m away, just below the big boulder on that slope) shakes / vibrates rapidly in place (physics jitter) instead of swaying gently like the others', at: [SHRUB_B.x, c.groundY(SHRUB_B.x, SHRUB_B.z) + 1.2, SHRUB_B.z], category: CAT.col };
  },
  // ---- visual consistency
  'wl09-magenta': (c) => {
    // the boulder on the north-east slope (review 2026-09-12: the boulder next to the start was too easy)
    let solo = null;
    c.watch(ROCK_B.x, ROCK_B.z, 2.5, rockOpts, (mesh, i, m) => { if (!solo) solo = c.detach(mesh, i, m, new c.THREE.MeshBasicMaterial({ color: 0xff00ff })); c.hideInstance(mesh, i); });
    return { name: 'missing-texture boulder', where: 'the big boulder up the slope north-east of the start (about 25 m away) renders as flat bright MAGENTA (missing texture placeholder)', at: [ROCK_B.x, c.groundY(ROCK_B.x, ROCK_B.z) + 3, ROCK_B.z], category: CAT.vis };
  },
  'wl10-backcull': (c) => {
    let solo = null; const p = { x: ROCK_B.x, z: ROCK_B.z };
    c.watch(ROCK_B.x, ROCK_B.z, 2.5, rockOpts, (mesh, i, m) => { if (!solo) solo = c.detach(mesh, i, m); c.hideInstance(mesh, i); });
    c.onFrame((t, cam) => { if (solo) solo.visible = (cam.position.z - p.z) > 0; });
    return { name: 'boulder invisible from behind', where: 'the big boulder up the slope north-east of the start (about 25 m away) is visible from the start side (south) but vanishes completely when viewed from its north (uphill) side', at: [ROCK_B.x, c.groundY(ROCK_B.x, ROCK_B.z) + 3, ROCK_B.z], category: CAT.vis };
  },
  'wl11-xray': (c) => {
    let solo = null;
    c.watch(ROCK_B.x, ROCK_B.z, 2.5, rockOpts, (mesh, i, m, p, info) => { if (!solo) { const mat = c.cloneMaterial(info.mat); mat.depthTest = false; solo = c.detach(mesh, i, m, mat); solo.renderOrder = 999; } c.hideInstance(mesh, i); });
    return { name: 'x-ray boulder', where: 'the big boulder up the slope north-east of the start (about 25 m away) renders through everything in front of it - it stays visible through trees, bushes and the hillside itself', at: [ROCK_B.x, c.groundY(ROCK_B.x, ROCK_B.z) + 3, ROCK_B.z], category: CAT.vis };
  },
  'wl14-lodpop': (c) => {
    const proxies = []; const targets = [];
    c.watch(TREE_A.x, TREE_A.z, 4.0, treeOpts, (mesh, i, m, p, info) => {
      targets.push({ mesh, i, m: m.clone() });
      if (!proxies.some((q) => Math.hypot(q.position.x - p.x, q.position.z - p.z) < 1)) {
        const cone = new c.THREE.Mesh(new c.THREE.ConeGeometry(info.w * 0.4, info.h, 6), new c.THREE.MeshStandardMaterial({ color: 0x3f6a34, flatShading: true }));
        cone.position.set(p.x, p.y + info.h / 2, p.z); cone.visible = false; c.scene.add(cone); proxies.push(cone);
      }
    });
    c.onFrame((t, cam) => { const far = Math.hypot(cam.position.x - TREE_A.x, cam.position.z - TREE_A.z) > 16; for (const q of targets) far ? c.hideInstance(q.mesh, q.i) : c.setInstance(q.mesh, q.i, q.m); for (const q of proxies) q.visible = far; });
    return { name: 'tree LOD pop', where: 'the tall pine west of the start (about 12 m away) shows as a crude flat-shaded green cone whenever you are more than ~16 m from it, and pops into a detailed tree only when you come closer', at: [TREE_A.x, c.groundY(TREE_A.x, TREE_A.z) + 8, TREE_A.z], category: CAT.vis };
  },
  // ---- spatiotemporal & state
  'wl12-unload': (c) => {
    // the big boulder right next to the start unloads once you have walked away from it (review 2026-09-16: the tree
    // 20 m up the north-west slope could not be found; the start boulder is in view the moment you turn round)
    const targets = []; let gone = false;
    c.watch(ROCK_A.x, ROCK_A.z, 2.5, rockOpts, (mesh, i, m) => { targets.push({ mesh, i }); if (gone) c.hideInstance(mesh, i); });
    c.onFrame((t, cam) => { const d = Math.hypot(cam.position.x - ROCK_A.x, cam.position.z - ROCK_A.z); if (!gone && d > 16) { gone = true; for (const q of targets) c.hideInstance(q.mesh, q.i); c.removeCollidersNear(ROCK_A.x, ROCK_A.z, 6); } });
    return { name: 'unloaded boulder', where: 'the big boulder right next to the start (behind you on the right at the start) is unloaded once you have walked more than about 15 m away from it - when you come back to the start it is gone, nothing but grass where it stood', at: [ROCK_A.x, c.groundY(ROCK_A.x, ROCK_A.z) + 2.5, ROCK_A.z], category: CAT.state, extent_x: 3, extent_z: 3 };
  },
  // wl13-statereset retired 2026-09-16 (review round 4): a leave-and-return position reset was judged too hard to notice in this world.
  // ---- semantics & world logic
  'wl15-spawnpile': (c) => {
    let done = false; const px = -4.0, pz = 9.0, py = c.groundY(-4.0, 9.0);
    // review 2026-09-14: copies 0.9 m apart read as a natural rock cluster; now jammed into each other in a tight heap
    c.watch(ROCK_A.x, ROCK_A.z, 2.5, rockOpts, (mesh, i, m) => { if (done) return; done = true; for (let k = 0; k < 9; k++) { const s = 0.3 + (k % 3) * 0.05; const mm = new c.THREE.Matrix4().compose(new c.THREE.Vector3(px + (k % 3) * 0.55, py - 0.3 + Math.floor(k / 3) * 0.6, pz + (k % 2) * 0.45), new c.THREE.Quaternion().setFromEuler(new c.THREE.Euler(0, k * 0.8, 0)), new c.THREE.Vector3(s, s, s)); c.detach(mesh, i, mm.premultiply(mesh.matrixWorld.clone().invert())); } });
    c.addCollider(px + 0.9, pz + 0.35, 1.7);   // the heap is solid (review: piled rocks had no collision)
    return { name: 'boulder pile', where: 'nine identical small boulders are jammed into one another in one tight heap on the open grass south-west of the start, near the water (failed spawns)', at: [px + 0.6, py + 0.8, pz + 0.2], category: CAT.sem, extent_x: 1.5, extent_z: 1.2 };
  },
  'wl16-terrainhole': (c) => {
    // a 7 m square of the rendered terrain is missing east of the start (the void shows through); the analytic ground
    // still carries the walker across it on invisible ground (review 2026-09-12: the 0.6 m tile seam was invisible)
    c.cutTerrainPatch(14, 8, 3.5);
    c.watch(14, 8, 3.6, { grass: true }, (mesh, i) => c.hideInstance(mesh, i));
    return { name: 'missing terrain patch', where: 'a square patch of the ground east of the start is MISSING - a hole in the terrain mesh shows the void / the far hills through it, yet you can still walk across the gap on invisible ground', at: [14, c.groundY(14, 8), 8], category: CAT.vis, extent_x: 3.5, extent_z: 3.5 };
  },
  'wl17-upsidedown': (c) => {
    // the big round-crowned tree north-west of the start stands on its crown: rotated 180 degrees about its base and
    // lifted by its height, so the crown rests on the ground and the bare trunk points into the sky (review 2026-09-12:
    // floating grass was invisible; a flipped pine still looked like a pine, a flipped broadleaf tree does not)
    const H = 19.3;
    c.watch(TREE_B.x, TREE_B.z, 3.0, treeOpts, (mesh, i, m, p) => {
      const flip = new c.THREE.Matrix4().makeTranslation(p.x, p.y + H, p.z).multiply(new c.THREE.Matrix4().makeRotationX(Math.PI)).multiply(new c.THREE.Matrix4().makeTranslation(-p.x, -p.y, -p.z));
      const W = mesh.matrixWorld;   // instance matrices are in the chunk group's frame: conjugate the world-space flip
      c.setInstance(mesh, i, W.clone().invert().multiply(flip).multiply(W).multiply(m));
    });
    return { name: 'upside-down tree', where: 'the big round-crowned tree north-west of the start (about 20 m away, up the slope) is UPSIDE DOWN - its leafy crown rests on the ground and its bare trunk sticks straight up out of the top of the crown into the sky', at: [TREE_B.x, c.groundY(TREE_B.x, TREE_B.z) + 9, TREE_B.z], category: CAT.sem };
  },
};

export function applyBug(id, ctx) {
  const fn = CATALOG[id];
  if (!fn) return null;
  const ans = fn(ctx);
  return { id, ...ans };
}

// review overlay hooks (src/common/bug_picker.js): stand 6 m from the answer looking at it; a beam marks it
export function installReviewHooks(handles) {
  const { camera, actor: controller, scene } = handles;
  (window as any).__bugGoto = (at) => {
    const ang = 200 * Math.PI / 180, cx = at[0] + Math.sin(ang) * 6, cz = at[2] + Math.cos(ang) * 6;
    handles.dismissOverlay(); handles.setHeadless(true); handles.teleport(cx, null, cz);
    const p = camera.position; controller.yaw = Math.atan2(-(at[0] - p.x), -(at[2] - p.z));
    controller.pitch = Math.max(-1.4, Math.min(1.4, Math.atan2(at[1] - p.y, Math.hypot(at[0] - p.x, at[2] - p.z))));
  };
  let beacon: any = null;
  (window as any).__bugBeacon = (at) => {
    if (beacon) { beacon.visible = !beacon.visible; return beacon.visible; }
    beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 16, 8), new THREE.MeshBasicMaterial({ color: 0xffd166 }));
    beacon.position.set(at[0], at[1] + 8, at[2]); scene.add(beacon); return true;
  };
}

// harness contract (shared classic script src/common/harness_page.js, injected by build.py)
export function installHarnessAdapter(handles, ctx, config, bugAnswer, query) {
  const { camera, actor: controller } = handles;
  handles.dismissOverlay(); handles.setHud(false); handles.setHeadless(true);
  return window.__installHarness({
    renderer: handles.renderer, camera,
    getPos: () => camera.position.toArray(),
    getYaw: () => controller.yaw, getPitch: () => controller.pitch,
    setView: (yaw, pitch) => { controller.yaw = yaw; controller.pitch = Math.max(-1.4, Math.min(1.4, pitch)); },
    keyDown: (code) => document.dispatchEvent(new KeyboardEvent('keydown', { code, key: code, bubbles: true })),
    keyUp: (code) => document.dispatchEvent(new KeyboardEvent('keyup', { code, key: code, bubbles: true })),
    speed: 5.6, spawn: { pos: [ctx.spawn.x, 0, ctx.spawn.z], yawDeg: 0 },
    teleport: (x, y, z) => handles.teleport(x, null, z),
    clamp: (x, z) => handles.teleport(x, null, z),
    resetCount: () => ctx.resets(),
    config, bugAnswer, film: window.__harnessFilmFromQuery(query),
    meta: { renderer: 'webgl (wilderness page)', three: THREE.REVISION, seed: handles.seed },
  });
}
