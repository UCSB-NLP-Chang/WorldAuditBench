// Mistwood Cottage bug catalogue (CT suite): one injected mutation per case, selected with `?bug=ctXX-slug`
// (or the harness config's `bug`).  Same taxonomy as the SP / HS / WT / AF / WL suites.  The upstream scene is a
// few merged meshes, so carriers are *detached* first: a connected component of `EnvironmentMerged` / `NoPhysics`
// (a tree, a bench, a lamp post) is copied into its own mesh (geometry recentred on the component, so position /
// rotation / scale act about the object) and the original triangles are collapsed.  The environment's trimesh
// physics is rebuilt once after the static mutations, so collision follows collapsed geometry (ghost tree,
// relocated post); the benchmark build also removes the rope fences here (they made walking miserable).
import * as THREE from 'three';

const CAT = { geo: 'geometry-space', col: 'collision-physics', vis: 'visual-consistency', state: 'spatiotemporal-state', sem: 'semantics-logic' };

// ---- connected components of an indexed merged mesh (vertices welded by position)
function components(mesh) {
  if (mesh.userData.__components) return mesh.userData.__components;
  const g = mesh.geometry, pos = g.attributes.position, n = pos.count, idx = g.index ? g.index.array : null;
  const parent = new Int32Array(n); for (let i = 0; i < n; i++) parent[i] = i;
  const find = (a) => { while (parent[a] !== a) { parent[a] = parent[parent[a]]; a = parent[a]; } return a; };
  const union = (a, b) => { a = find(a); b = find(b); if (a !== b) parent[a] = b; };
  const key = new Map();
  for (let i = 0; i < n; i++) { const k = Math.round(pos.getX(i) * 200) + ',' + Math.round(pos.getY(i) * 200) + ',' + Math.round(pos.getZ(i) * 200); const j = key.get(k); if (j === undefined) key.set(k, i); else union(i, j); }
  const tri = idx ? idx.length / 3 : n / 3;
  for (let t = 0; t < tri; t++) { const a = idx ? idx[3 * t] : 3 * t, b = idx ? idx[3 * t + 1] : 3 * t + 1, c = idx ? idx[3 * t + 2] : 3 * t + 2; union(a, b); union(b, c); }
  mesh.updateWorldMatrix(true, false);
  const v = new THREE.Vector3(), comps = new Map();
  for (let i = 0; i < n; i++) {
    const r = find(i); let c = comps.get(r); if (!c) { c = { root: r, n: 0, box: new THREE.Box3(), verts: [] }; comps.set(r, c); }
    v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(mesh.matrixWorld); c.n++; c.box.expandByPoint(v); c.verts.push(i);
  }
  const list = [...comps.values()].map((c) => ({ ...c, center: c.box.getCenter(new THREE.Vector3()), size: c.box.getSize(new THREE.Vector3()) }));
  mesh.userData.__components = list;
  return list;
}
function pickComponent(mesh, x, z, minN = 60, maxDist = 1.5) {
  let best = null, bd = 1e9;
  for (const c of components(mesh)) { if (c.n < minN || c.collapsed) continue; const d = Math.hypot(c.center.x - x, c.center.z - z); if (d < bd) { bd = d; best = c; } }
  if (!best || bd > maxDist) throw new Error(`no component near ${x},${z} (nearest ${bd.toFixed(2)})`);
  return best;
}
// collapse a component's triangles to a point (the original disappears from rendering and, after the physics
// rebuild, from collision)
function collapse(mesh, comp) {
  const pos = mesh.geometry.attributes.position;
  const lc = comp.center.clone().applyMatrix4(mesh.matrixWorld.clone().invert());
  comp.verts.forEach((k) => pos.setXYZ(k, lc.x, lc.y, lc.z));
  pos.needsUpdate = true; mesh.geometry.computeBoundingSphere(); comp.collapsed = true;
}
// copy a component into its own mesh (geometry recentred on the component centre, parented to the scene root so
// world == local) and collapse the original triangles
function detach(mesh, comp, material) {
  const g = mesh.geometry, pos = g.attributes.position, idx = g.index.array;
  const inComp = new Uint8Array(pos.count); comp.verts.forEach((i) => { inComp[i] = 1; });
  const remap = new Map(); const P = [], UV = [], N = [], I = [];
  const uv = g.attributes.uv, nor = g.attributes.normal, v = new THREE.Vector3(), nm = new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld);
  const c = comp.center;
  const take = (i) => { let j = remap.get(i); if (j === undefined) { j = remap.size; remap.set(i, j); v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(mesh.matrixWorld); P.push(v.x - c.x, v.y - c.y, v.z - c.z); if (uv) UV.push(uv.getX(i), uv.getY(i)); if (nor) { v.set(nor.getX(i), nor.getY(i), nor.getZ(i)).applyMatrix3(nm).normalize(); N.push(v.x, v.y, v.z); } } return j; };
  for (let t = 0; t < idx.length; t += 3) {
    const a = idx[t], b = idx[t + 1], d = idx[t + 2];
    if (!inComp[a] && !inComp[b] && !inComp[d]) continue;
    I.push(take(a), take(b), take(d));
  }
  collapse(mesh, comp);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(P, 3));
  if (UV.length) geo.setAttribute('uv', new THREE.Float32BufferAttribute(UV, 2));
  if (N.length) geo.setAttribute('normal', new THREE.Float32BufferAttribute(N, 3)); else geo.computeVertexNormals();
  geo.setIndex(I); geo.computeBoundingBox(); geo.computeBoundingSphere();
  const m = new THREE.Mesh(geo, material || mesh.material);
  m.castShadow = mesh.castShadow; m.receiveShadow = mesh.receiveShadow; m.frustumCulled = false; m.name = 'DETACHED';
  m.position.copy(c); m.userData.base = comp.box.min.y; m.userData.size = comp.size.clone();
  let root = mesh; while (root.parent) root = root.parent;
  root.add(m);
  return m;
}
// several components as one object: a Group at the base centre of their joint bounds, the detached meshes as children
function detachGroup(mesh, comps) {
  const box = new THREE.Box3(); comps.forEach((c) => box.union(c.box));
  const c = box.getCenter(new THREE.Vector3()); c.y = box.min.y;
  const g = new THREE.Group(); g.position.copy(c); g.name = 'DETACHED_GROUP';
  let root = mesh; while (root.parent) root = root.parent;
  root.add(g);
  for (const comp of comps) { const m = detach(mesh, comp); root.remove(m); m.position.sub(c); g.add(m); }
  g.userData.size = box.getSize(new THREE.Vector3());
  return g;
}
function proxyFor(scene, at, size, color = 0x4d6b3a) {
  const m = new THREE.Mesh(new THREE.ConeGeometry(Math.max(size.x, size.z) * 0.45, size.y, 6), new THREE.MeshBasicMaterial({ color }));
  m.position.set(at.x, at.y + size.y / 2, at.z); m.visible = false; scene.add(m); return m;
}

// the rope fences of the upstream garden (post positions, see World/ExtraColliders.js): removed in the benchmark
// build - posts, rope strands and the lanterns / knots hung on the posts
const FENCES = [
  [[0.57, 2.23], [0.24, 3.17], [-0.09, 4.51], [-0.15, 5.62], [-0.46, 6.53]],
  [[-0.99, 2.27], [-1.47, 1.37], [-1.47, 0.3], [-1.4, -1.23], [-1.52, -3.09], [-2.0, -4.45], [-3.19, -5.53], [-3.96, -6.38], [-4.82, -6.97], [-6.38, -6.91], [-7.44, -6.69], [-8.25, -6.8]],
];
function fenceDistance(x, z) {
  let best = 1e9;
  for (const chain of FENCES) for (let i = 0; i + 1 < chain.length; i++) {
    const [ax, az] = chain[i], [bx, bz] = chain[i + 1]; const dx = bx - ax, dz = bz - az; const L2 = dx * dx + dz * dz;
    const t = L2 ? Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / L2)) : 0;
    best = Math.min(best, Math.hypot(x - (ax + t * dx), z - (az + t * dz)));
  }
  return best;
}
function removeFences(ctx) {
  let n = 0;
  for (const c of components(ctx.env)) {
    const d = fenceDistance(c.center.x, c.center.z);
    const post = c.n === 32 && Math.abs(c.size.y - 0.52) < 0.06 && d < 0.08;
    const rope = c.n >= 97 && c.n <= 132 && c.size.y < 0.65 && d < 0.08;
    if (post || rope) { collapse(ctx.env, c); n++; }
  }
  if (ctx.noPhysics) for (const c of components(ctx.noPhysics)) {
    const d = fenceDistance(c.center.x, c.center.z);
    if (d < 0.10 && c.size.y < 0.9 && Math.max(c.size.x, c.size.z) < 0.55 && c.n <= 50) { collapse(ctx.noPhysics, c); n++; }
  }
  return n;
}

// carriers (world units; the scene is ~1 unit = 1.5 m).  Spawn (-0.6, 5) on the path south of the front door.
const TREE_A = { x: 1.82, z: 2.47, n: 800 };     // big tree east of the front door (one welded piece, 4.2 tall)
const TREE_B = { x: 1.49, z: -4.54, n: 200 };    // tree behind the cottage: trunk component + separate canopy blobs
const BRANCH = { x: 2.41, z: 2.0, n: 150 };      // gnarled dead branch lying beside the path, under the big tree
const TABLE = { x: -3.97, z: -1.66, n: 200 };    // stone picnic table in the west garden (0.8 x 0.7 x 1.7 units)
const BENCH_E = { x: -3.1, z: -1.6 };            // the garden bench east of the table (seat + backrest boards)
const POST = { x: -4.97, z: 2.69, n: 150 };      // tall lamp post by the west steps (2.75 units)
const LANTERN = { x: -4.19, z: 1.74, n: 100 };   // small lantern post west of the path (1.5 units)
const treeBComps = (c) => components(c.env).filter((k) => !k.collapsed && Math.hypot(k.center.x - TREE_B.x, k.center.z - TREE_B.z) < 1.6 && (k.n >= 200 || k.center.y > 1.0));
const benchComps = (c) => components(c.env).filter((k) => !k.collapsed && Math.hypot(k.center.x - BENCH_E.x, k.center.z - BENCH_E.z) < 0.6 && (k.n === 62 || k.n === 92));

export const CATALOG = {
  // ---- geometry & space
  'ct01-float': (c) => {
    const m = c.detach(c.env, c.pick(c.env, TREE_A)); m.position.y += 1.1;
    return { name: 'floating tree', where: 'the big tree east of the front door hovers more than a metre above the ground - its roots hang in the air', at: [TREE_A.x, 2.4, TREE_A.z], category: CAT.geo };
  },
  'ct02-clip': (c) => {
    // tilted and sunk (review 2026-09-12: the merely lowered well read as a small trough)
    // review 2026-09-14: 24 degrees / 0.22 could pass as a quirky table; now tipped 38 degrees and sunk 0.42 units
    const m = c.detach(c.env, c.pick(c.env, TABLE)); m.rotation.z = THREE.MathUtils.degToRad(38); m.position.y -= 0.42;
    return { name: 'sunken picnic table', where: 'the stone picnic table in the west garden is tipped over at about 40 degrees and sunk into the lawn - one half of the table top and its bench is under the grass, the other half sticks up into the air', at: [TABLE.x, -0.3, TABLE.z], category: CAT.geo };
  },
  'ct03-scale': (c) => {
    // one of the two identical garden benches, 2.2x, next to its normal twin and the table
    const g = c.detachGroup(c.env, benchComps(c)); g.scale.setScalar(2.2); g.position.x = -2.95;
    return { name: 'giant garden bench', where: 'one of the two garden benches in the west garden is more than twice its normal size - the bench east of the table towers over the identical bench on the other side', at: [-2.95, 0.4, BENCH_E.z], category: CAT.geo };
  },
  'ct04-doublespawn': (c) => {
    // the garden bench east of the picnic table, spawned twice (review 2026-09-14: a doubled dead branch read as an odd tree)
    const g = c.detachGroup(c.env, benchComps(c)); const twin = g.clone(); twin.position.add(new THREE.Vector3(0.32, 0.06, 0.22)); twin.rotation.y += 0.42; g.parent.add(twin);
    return { name: 'double-spawned bench', where: 'the garden bench east of the stone picnic table in the west garden is spawned TWICE - a second identical bench sits shifted and turned into the first one, seat boards and legs passing through each other', at: [BENCH_E.x, 0.4, BENCH_E.z], category: CAT.geo };
  },
  // ---- collision & physics
  'ct05-airwall': (c) => {
    c.addBox(-0.35, c.groundY(-0.35, 3.3) + 0.8, 3.3, [1.3, 0.8, 0.08]);
    return { name: 'invisible wall', where: 'an invisible barrier across the front path, halfway between the gate and the cottage door, stops you although nothing is visible there', at: [-0.35, 0.2, 3.3], category: CAT.col };
  },
  'ct06-hole': (c) => {
    // the walker drops just below the flagstones and then falls under the garden for ~1.7 s (the fall is visible) before respawning
    const zone = { x: -0.6, z: 3.7, r: 0.55 }; let falling = 0;
    c.onFrame(() => { const p = c.playerPos(); if (!falling && Math.hypot(p[0] - zone.x, p[2] - zone.z) < zone.r && p[1] > -2) { falling = performance.now(); c.dropPlayer(0.9); } else if (falling && performance.now() - falling > 1700) { falling = 0; c.respawn(); } });
    return { name: 'hole in the path', where: 'you fall straight through the solid-looking flagstones of the front path at one spot and drop into darkness below the garden, then respawn', at: [zone.x, -0.5, zone.z], category: CAT.col };
  },
  'ct07-ghost': (c) => {
    // the tree keeps its look; its collision is gone (the environment trimesh is rebuilt without it)
    c.detach(c.env, c.pick(c.env, TREE_A)); c.physicsDirty = true;
    return { name: 'no-collision tree', where: 'the big tree east of the front door has no collision - you walk straight through its trunk while everything else is solid', at: [TREE_A.x, 0.6, TREE_A.z], category: CAT.col };
  },
  'ct08-jitter': (c) => {
    const m = c.detach(c.env, c.pick(c.env, LANTERN)); const base = m.position.clone();
    c.onFrame((t) => { m.position.set(base.x + Math.sin(t * 9) * 0.03, base.y + Math.sin(t * 13) * 0.01, base.z + Math.cos(t * 11) * 0.03); });
    return { name: 'trembling lantern post', where: 'the small lantern post west of the path (by the pond bank) shakes / trembles in place on its own', at: [LANTERN.x, -0.6, LANTERN.z], category: CAT.col };
  },
  // ---- visual consistency
  'ct09-magenta': (c) => {
    const mat = new THREE.MeshBasicMaterial({ color: 0xff00ff });
    c.well.material = mat;
    // the day cycle re-assigns the shared environment material to the well on every cycle change (review 2026-09-14: the
    // magenta reverted after ~10 s); keep the placeholder material in place
    c.onFrame(() => { if (c.well.material !== mat) c.well.material = mat; });
    return { name: 'missing-texture well', where: 'the stone well on the hill to the west renders as flat bright MAGENTA (missing texture placeholder)', at: [-9.65, 3.6, -6.14], category: CAT.vis };
  },
  'ct10-backcull': (c) => {
    const g = c.detachGroup(c.env, treeBComps(c));
    c.onFrame((t, cam) => { g.visible = (cam.position.z - TREE_B.z) > 0; });
    return { name: 'tree invisible from behind', where: 'the tree behind the cottage is visible from the south (cottage side) but vanishes completely when viewed from its north side', at: [TREE_B.x, 0.8, TREE_B.z], category: CAT.vis };
  },
  'ct11-xray': (c) => {
    const pf = c.pictures; pf.material = pf.material.clone(); pf.material.depthTest = false; pf.renderOrder = 999;
    return { name: 'x-ray picture frames', where: 'the picture frames hanging inside the cottage show through the front wall - from outside you see them floating on the facade', at: [0.51, 1.25, 1.17], category: CAT.vis };
  },
  'ct14-lodpop': (c) => {
    const comp = c.pick(c.env, TREE_A); const m = c.detach(c.env, comp); const proxy = c.proxyFor(new THREE.Vector3(comp.center.x, comp.box.min.y, comp.center.z), comp.size);
    c.onFrame((t, cam) => { const far = Math.hypot(cam.position.x - TREE_A.x, cam.position.z - TREE_A.z) > 5.5; m.visible = !far; proxy.visible = far; });
    return { name: 'tree LOD pop', where: 'the big tree east of the front door shows as a crude green cone from a few metres away and pops into a detailed tree only when you get close', at: [TREE_A.x, 1.5, TREE_A.z], category: CAT.vis };
  },
  // ---- spatiotemporal & state
  'ct12-unload': (c) => {
    const g = c.detachGroup(c.env, treeBComps(c)); let visited = false, gone = false;
    c.onFrame((t, cam) => { const d = Math.hypot(cam.position.x - TREE_B.x, cam.position.z - TREE_B.z); if (d < 4.5) visited = true; if (visited && !gone && d > 7) { gone = true; g.visible = false; c.rebuildEnvPhysics(); } });
    return { name: 'unloaded tree', where: 'after you walk round to the tree behind the cottage and leave, the tree is unloaded and gone when you come back', at: [TREE_B.x, 0.8, TREE_B.z], category: CAT.state };
  },
  'ct13-statereset': (c) => {
    // the lamp post by the west steps stands somewhere else each time you come back; a box collider follows it
    const comp = c.pick(c.env, POST); const m = c.detach(c.env, comp); c.physicsDirty = true;
    const a = m.position.clone(), b = a.clone().add(new THREE.Vector3(1.5, 0, 1.1));
    const col = c.addBox(a.x, comp.box.min.y + comp.size.y / 2, a.z, [0.1, comp.size.y / 2, 0.1]);
    let nearIt = false, flips = 0;
    c.onFrame((t, cam) => { const d = Math.hypot(cam.position.x - a.x, cam.position.z - a.z); if (d < 4.2) nearIt = true; if (nearIt && d > 6.2) { nearIt = false; flips++; const q = flips % 2 ? b : a; m.position.copy(q); col.setTranslation({ x: q.x, y: comp.box.min.y + comp.size.y / 2, z: q.z }); } });   // the post stands in the pond: 4.2 is the path-side bank, 6.2 the east lawn
    return { name: 'lamp post position resets', where: 'the tall lamp post standing in the pond west of the path is at a different spot each time you come back after walking away (its position resets / jumps about 2.5 m)', at: [POST.x, -0.5, POST.z], category: CAT.state, extent_x: 0.8, extent_z: 0.6 };
  },
  'ct17-timejump': (c) => {
    // instant cuts between full daylight and night about once a second (the normal cycle is a 2 s cross-fade every 30 s;
    // review 2026-09-14: every 3 s was hard to tell from the normal cycle)
    let last = performance.now(), night = false;
    c.onFrame(() => { if (performance.now() - last > 800) { last = performance.now(); night = !night; c.setCycle(night ? 3 : 1, true); } });
    return { name: 'time of day flickers', where: 'the whole scene FLICKERS between full daylight and night about once a second - instant cuts back and forth, nothing like the normal slow half-minute cycle with its gentle cross-fade', at: [-0.6, 0.5, 5.0], category: CAT.state, global: true };
  },
  // ---- semantics & world logic
  'ct15-spawnpile': (c) => {
    const comp = c.pick(c.env, TABLE); const m = c.detach(c.env, comp); const px = 1.6, pz = 4.6, gy = c.groundY(px, pz);
    const h = comp.size.y * 0.5;
    for (let i = 0; i < 9; i++) { const k = m.clone(); k.scale.setScalar(0.5); k.position.set(px + (i % 3) * 0.35, gy + h / 2 + Math.floor(i / 3) * 0.33, pz + (i % 2) * 0.3); k.rotation.y = i * 0.8; m.parent.add(k); }
    m.position.copy(new THREE.Vector3(comp.center.x, comp.center.y, comp.center.z));   // the original stays where it was
    c.addBox(px + 0.35, gy + 0.55, pz + 0.15, [0.75, 0.55, 0.65]);                    // the heap is solid (review: piles had no collision)
    return { name: 'table pile', where: 'nine small stone tables are dumped on top of each other in one heap on the lawn east of the front path, under the big tree (failed spawns)', at: [px + 0.3, gy + 0.4, pz], category: CAT.sem };
  },
  // ct16-missingdoor retired 2026-09-16 (review round 3): the doorway is lower than the walker, so the leftover door collision reads as the walker's head hitting the lintel.
};

export function applyBug(id, ctx) {
  const fn = CATALOG[id];
  if (!fn) return null;
  const ans = fn(ctx);
  return { id, ...ans };
}

// context over the live Experience (see app/main.js)
export function createBugContext(experience) {
  const world = experience.world, scene = experience.scene, physics = experience.physics, RAPIER = physics.RAPIER;
  const items = world.environment.items;
  const byName = (n) => { let m = null; scene.traverse((o) => { if (!m && o.name === n) m = o; }); return m; };
  const frameHooks = []; const t0 = performance.now(); let resets = 0; let fixedBody = null;
  const spawn = { x: -0.6, z: 5.0 };
  const ctx = {
    THREE, scene, experience, physics, env: items.EnvironmentMerged, noPhysics: items.NoPhysics, well: items.Well,
    water: world.terrain.pond.water,
    waterLevel: () => world.terrain.pond.water.getWorldPosition(new THREE.Vector3()).y,
    front: byName('CottageFrontMerged'), frontWindows: byName('frontwindows'), pictures: byName('pictureframes'),
    pick: (mesh, t) => pickComponent(mesh, t.x, t.z, t.n || 60, 1.6),
    components: (mesh) => components(mesh),
    detach: (mesh, comp, material) => detach(mesh, comp, material),
    detachGroup: (mesh, comps) => detachGroup(mesh, comps),
    proxyFor: (at, size) => proxyFor(scene, at, size),
    onFrame: (fn) => frameHooks.push(fn),
    groundY: (x, z) => { const ray = new RAPIER.Ray({ x, y: 20, z }, { x: 0, y: -1, z: 0 }); const hit = physics.world.castRay(ray, 60, true, undefined, undefined, world.player.collider); return hit ? 20 - hit.timeOfImpact : 0; },
    addBox: (x, y, z, half) => { if (!fixedBody) fixedBody = physics.world.createRigidBody(RAPIER.RigidBodyDesc.fixed()); return physics.world.createCollider(RAPIER.ColliderDesc.cuboid(half[0], half[1], half[2]).setTranslation(x, y, z), fixedBody); },
    removeFences: () => removeFences(ctx),
    physicsDirty: false,
    rebuildEnvPhysics: () => {   // the environment trimesh follows the (collapsed) render geometry
      const env = world.environment;
      if (env.envPhysics) physics.world.removeRigidBody(env.envPhysics.rigidBody);
      env.envPhysics = physics.glbToTrimesh(items.EnvironmentMerged);
      ctx.physicsDirty = false;
    },
    playerPos: () => { const t = world.player.rigidBody.translation(); return [t.x, t.y, t.z]; },
    dropPlayer: (dy = 6) => { const t = world.player.rigidBody.translation(); window.BenchmarkWorld.teleport(t.x, t.y - dy, t.z); },
    respawn: () => { resets++; window.BenchmarkWorld.teleport(spawn.x, null, spawn.z); },
    resets: () => resets,
    setCycle: (i, instant = false) => {
      experience.cycles.advanceToSpecificCycle(i);
      if (!instant) return;
      // kill the 2 s cross-fades the cycle change started and jump straight to the new textures
      const g = window.gsap;
      for (const part of [world.cottage, world.environment, world.terrain, world.room, world.fog]) {
        if (!part) continue;
        for (const key of ['uniforms', 'uniformsLeft', 'uniformsFront']) { const u = part[key]; if (u && u.uMixProgress) { if (g) g.killTweensOf(u.uMixProgress); u.uMixProgress.value = 1; } }
      }
    },
    spawn,
  };
  const loop = () => { const t = (performance.now() - t0) / 1000; const cam = experience.camera.instance; for (const h of frameHooks) { try { h(t, cam); } catch (e) { console.warn('bug hook', e); frameHooks.splice(frameHooks.indexOf(h), 1); } } requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
  return ctx;
}

// review overlay hooks (src/common/bug_picker.js): stand 3.2 units from the answer looking at it; a beam marks it
export function installReviewHooks(experience, ctx) {
  window.__bugGoto = (at) => {
    // a standing spot 3.2 units from the answer: outside the cottage footprint, out of the pond, inside the garden
    const bad = (x, z) => (x > -1.3 && x < 2.5 && z > -2.8 && z < 1.7) || (x < -2.4 && z > 0.3) || x < -12 || x > 7.5 || z < -10.5 || z > 8.5;
    let cx = at[0] + 3.2, cz = at[2] + 3.2;
    for (const deg of [20, 340, 60, 300, 120, 240, 200, 160, 0, 180]) { const a = deg * Math.PI / 180; const x = at[0] + Math.sin(a) * 3.2, z = at[2] + Math.cos(a) * 3.2; if (!bad(x, z)) { cx = x; cz = z; break; } }
    window.BenchmarkWorld.setFirstPerson(true); window.BenchmarkWorld.teleport(cx, null, cz);
    const p = experience.camera.instance.position; const dx = at[0] - p.x, dz = at[2] - p.z;
    window.BenchmarkWorld.setView(Math.atan2(-dx, -dz), Math.max(0.35, Math.min(2.6, Math.PI / 2 + Math.atan2(at[1] - p.y, Math.hypot(dx, dz)))));
  };
  let beacon = null;
  window.__bugBeacon = (at) => {
    if (beacon) { beacon.visible = !beacon.visible; return beacon.visible; }
    beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 6, 8), new THREE.MeshBasicMaterial({ color: 0xffd166 }));
    beacon.position.set(at[0], at[1] + 3, at[2]); ctx.scene.add(beacon); return true;
  };
}

// harness contract (shared classic script src/common/harness_page.js, injected by build.py into template.html)
export function installHarnessAdapter(experience, ctx, config, bugAnswer, query) {
  const cam = () => experience.world.player.cameraPOV;
  window.BenchmarkWorld.setFirstPerson(true);
  return window.__installHarness({
    renderer: experience.renderer.instance, camera: experience.camera.instance,
    getPos: ctx.playerPos,
    getYaw: () => cam().theta, getPitch: () => cam().phi - Math.PI / 2,
    setView: (yaw, pitch) => { window.BenchmarkWorld.setView(yaw, Math.max(0.35, Math.min(2.6, Math.PI / 2 + pitch))); },
    speed: 2.3, spawn: { pos: [ctx.spawn.x, 0, ctx.spawn.z], yawDeg: 0 },
    // walkable = ground above the pond's water level (the pond bank is fine, the water is not); replaces the old
    // exclusion rectangle that also fenced off the bank west of the cottage
    allowed: (x, z) => ctx.groundY(x, z) > ctx.waterLevel() + 0.22,   // +0.22: keeps the walker off the last, cliff-like bit of bank (the path itself sits 0.34 above the water)
    teleport: (x, y, z) => window.BenchmarkWorld.teleport(x, null, z),
    clamp: (x, z) => window.BenchmarkWorld.teleport(x, null, z),
    resetCount: ctx.resets,
    config, bugAnswer, film: window.__harnessFilmFromQuery(query),
    meta: { renderer: 'webgl (cottage page)', three: THREE.REVISION },
  });
}
