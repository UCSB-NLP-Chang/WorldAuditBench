// Airfield bug catalogue (AF suite): injected mutations for the benchmark, one per case, selected with
// `?bug=afXX-slug` (or the harness config's `bug`).  Same taxonomy as the SP / HS / WT suites (geometry, collision,
// visual, state, semantics) plus two airfield-specific cases.  Every entry mutates the live scene through the
// context built by enhance.js and returns the judge answer {name, where, at, category}.
(function () {
  'use strict';
  const CAT = { geo: 'geometry-space', col: 'collision-physics', vis: 'visual-consistency', state: 'spatiotemporal-state', sem: 'semantics-logic' };
  const dist2 = (o, x, z) => Math.hypot(o.position.x - x, o.position.z - z);
  function prop(ctx, model, x, z) {           // the placed prop of that model nearest to (x, z)
    let best = null, bd = 1e9;
    for (const o of ctx.props) { if (o.userData.prop.m !== model) continue; const d = dist2(o, x, z); if (d < bd) { bd = d; best = o; } }
    if (!best) throw new Error('no prop ' + model);
    return best;
  }
  const near = (ctx, x, z, r) => ctx.props.filter((o) => dist2(o, x, z) < r);
  const at = (o, dy = 0) => [+o.position.x.toFixed(2), +(o.position.y + dy).toFixed(2), +o.position.z.toFixed(2)];
  function moveWithBody(ctx, o, x, y, z) { o.position.set(x, y, z); ctx.syncBody(o); }
  function cloneVisual(o) {                 // Object3D.clone() JSON-copies userData, which holds the cannon body (circular)
    const saved = o.userData; o.userData = {}; const c = o.clone(); o.userData = saved; c.userData = { prop: saved.prop, twin: true }; return c;
  }
  function cloneProp(ctx, o, dx, dy, dz) {
    const c = cloneVisual(o); c.position.set(o.position.x + dx, o.position.y + dy, o.position.z + dz); c.name = o.name + '_twin';
    o.parent.add(c); return c;
  }
  function proxyFor(ctx, o) {                 // crude blocky stand-in of a prop (LOD pop)
    const bb = new ctx.T.Box3().setFromObject(o); const s = bb.getSize(new ctx.T.Vector3()); const c = bb.getCenter(new ctx.T.Vector3());
    const m = new ctx.T.Mesh(new ctx.T.BoxGeometry(s.x, s.y, s.z, 1, 1, 1), new ctx.T.MeshStandardMaterial({ color: 0x8d8a82, roughness: 1, flatShading: true }));
    m.position.copy(c); m.rotation.y = o.rotation.y; m.visible = false; o.parent.add(m); return m;
  }

  const CATALOG = {
    // ---- geometry & space
    'af01-float': (ctx) => {
      const o = prop(ctx, 'barrel_03', 15.4, -14.4);
      moveWithBody(ctx, o, o.position.x, o.position.y + 1.5, o.position.z);
      return { name: 'floating barrel', where: 'one of the three barrels east of the start hovers about 1.5 m above the tarmac with open air under it', at: at(o), category: CAT.geo };
    },
    'af02-clip': (ctx) => {
      // tilted and sunk (review 2026-09-12: a merely lowered cart read as a shorter cart)
      // review 2026-09-14: 24 degrees / 0.38 m read as a cart with a short leg -> tipped 45 degrees and sunk 0.6 m
      const o = prop(ctx, 'tool_cart', -12.0, -14.0);
      o.rotation.z += 0.78; moveWithBody(ctx, o, o.position.x, o.position.y - 0.6, o.position.z);
      return { name: 'sunken tool cart', where: 'the tool cart by the generator (west of the start) is tipped over at about 45 degrees and sunk into the tarmac - its lower half, wheels included, is under the ground and the tarmac cuts straight through its body', at: at(o, 0.3), category: CAT.geo };
    },
    'af03-scale': (ctx) => {
      // a fire hydrant has a size everybody knows (review 2026-09-12: a big propane tank could pass as a real one)
      const o = prop(ctx, 'fire_hydrant', 18.0, -20.0);
      o.scale.multiplyScalar(3.2); ctx.syncBody(o, 3.2);
      return { name: 'giant fire hydrant', where: 'the fire hydrant north-east of the start is about three times its normal size - a hydrant taller than a person', at: at(o, 1.2), category: CAT.geo };
    },
    'af04-doublespawn': (ctx) => {
      const o = prop(ctx, 'old_military_crate', 12.0, 10.0);
      const twin = cloneProp(ctx, o, 0.10, 0.04, 0.08); twin.rotation.y += 0.12;
      return { name: 'double-spawned crate', where: 'the military crate north-east of the start is spawned twice almost on top of itself - a doubled, slightly offset copy interpenetrates it with flickering faces', at: at(o, 0.4), category: CAT.geo };
    },
    // ---- collision & physics
    'af05-airwall': (ctx) => {
      ctx.addStaticBox(0, ctx.groundY(0, -30), -30, 0, [14, 1.6, 0.25]);   // 28 m wide (review 2026-09-14: 18 m was walked around)
      return { name: 'invisible wall', where: 'an invisible barrier right across the tarmac about 8 m north of the north barrier row (about 16 m north of the start) stops you although nothing is visible there', at: [0, ctx.groundY(0, -30) + 1, -30], category: CAT.col };
    },
    'af06-hole': (ctx) => {
      // the walker drops just under the tarmac and falls for ~1.8 s (the fall is visible: the strip seen from below), then respawns
      // the capsule ignores the ground trimesh and stands on its feet raycast: switch the raycast and the contacts off
      // for 1.8 s so gravity takes it straight through the tarmac (a visible fall), then respawn
      // review 2026-09-14: 48 m south "near the middle of the strip" took a long search (and the stone gate stands between
      // the start and anything south of it); now 4 m straight ahead of the start, on the way to the north barrier row
      const zone = { x: 0, z: -18, r: 2.2 }; const gy = ctx.groundY(zone.x, zone.z); let falling = 0, savedLen = null;
      ctx.onFrame(() => {
        const ch = ctx.character(); if (!ch) return; const p = ch.position; const body = ch.characterCapsule && ch.characterCapsule.body;
        if (falling === 0 && Math.hypot(p.x - zone.x, p.z - zone.z) < zone.r && p.y < gy + 1.0) {
          falling = performance.now(); savedLen = ch.rayCastLength; ch.rayCastLength = 0; ch.rayHasHit = false;
          if (body) { body.collisionResponse = false; body.velocity.set(0, -1.5, 0); }
        } else if (falling && performance.now() - falling > 1800) {
          falling = 0; ch.rayCastLength = savedLen; if (body) body.collisionResponse = true; ctx.respawn();
        }
      });
      return { name: 'hole in the ground', where: 'you fall straight through the solid-looking tarmac at one spot about 4 m straight ahead (north) of the start, on the centre line of the strip just before the north barrier row, and drop into darkness, then respawn', at: [zone.x, gy, zone.z], category: CAT.col };
    },
    'af07-ghost': (ctx) => {
      const o = prop(ctx, 'concrete_road_barrier', 2.0, -22.0);
      ctx.removeBody(o);
      return { name: 'no-collision barrier', where: 'one concrete road barrier in the row north of the start has no collision - you walk straight through it while the others are solid', at: at(o, 0.4), category: CAT.col };
    },
    'af08-jitter': (ctx) => {
      const o = prop(ctx, 'street_lamp_01', 12.0, -18.0); const base = o.position.clone();
      ctx.onFrame((t) => { o.position.set(base.x + Math.sin(t * 9) * 0.06, base.y + Math.sin(t * 13) * 0.02, base.z + Math.cos(t * 11) * 0.06); });
      return { name: 'trembling street lamp', where: 'the street lamp east of the barrier row shakes / vibrates rapidly in place (physics jitter)', at: at(o, 2.5), category: CAT.col };
    },
    // ---- visual consistency
    'af09-magenta': (ctx) => {
      const o = prop(ctx, 'wooden_crate_02', 12.4, 12.2); const mat = new ctx.T.MeshBasicMaterial({ color: 0xff00ff });
      o.traverse((m) => { if (m.isMesh) m.material = mat; });
      return { name: 'missing-texture crate', where: 'the wooden crate in the north-east cluster renders as flat bright MAGENTA (missing texture placeholder)', at: at(o, 0.4), category: CAT.vis };
    },
    'af10-backcull': (ctx) => {
      const o = prop(ctx, 'concrete_road_barrier', -6.0, -22.0); const p = o.position.clone();
      ctx.onFrame((t, cam) => { o.visible = (cam.position.z - p.z) > 0; });
      return { name: 'barrier invisible from behind', where: 'the SECOND barrier from the west end of the north barrier row (the row 8 m north of the start) is visible from the south (start side) but vanishes completely when viewed from its north side', at: at(o, 0.4), category: CAT.vis };
    },
    'af11-xray': (ctx) => {
      // the parked red car by the stone gate is drawn on top of everything (review 2026-09-14: a small plastic crate was
      // hardly ever occluded, so the effect never showed): stand behind a gate pillar or a barrier and the car still shows through
      const w = ctx.world(); let best = null, bd = 1e9;
      for (const v of w.vehicles) { const d = Math.hypot(v.position.x + 4.2, v.position.z + 5.6); if (d < bd) { bd = d; best = v; } }
      best.traverse((m) => {
        if (!m.isMesh) return;
        const mats = Array.isArray(m.material) ? m.material : [m.material];
        const cl = mats.map((mat) => { const c = mat.clone(); c.defines = mat.defines; c.onBeforeCompile = mat.onBeforeCompile; c.depthTest = false; c.depthWrite = false; c.needsUpdate = true; return c; });
        m.material = Array.isArray(m.material) ? cl : cl[0]; m.renderOrder = 999;
      });
      return { name: 'x-ray car', where: 'the red car parked just south of the start (by the stone gate) renders THROUGH everything in front of it - it stays fully visible through the stone gate pillars, the barriers and the crates that should hide it', at: [+best.position.x.toFixed(2), +(best.position.y + 0.6).toFixed(2), +best.position.z.toFixed(2)], category: CAT.vis, extent_x: 2.5, extent_z: 2.5 };
    },
    'af14-lodpop': (ctx) => {
      const cluster = near(ctx, -12.5, -11.5, 4.5); const proxies = cluster.map((o) => proxyFor(ctx, o));
      ctx.onFrame((t, cam) => { const far = Math.hypot(cam.position.x + 12.5, cam.position.z + 11.5) > 7; cluster.forEach((o) => { o.visible = !far; }); proxies.forEach((m) => { m.visible = far; }); });
      return { name: 'prop LOD pop', where: 'the generator / tool cart / jerrycan group west of the start shows as crude grey blocks from a few metres away and pops into detailed props only when you get close', at: [-12.5, ctx.groundY(-12.5, -11.5) + 0.5, -11.5], category: CAT.vis };
    },
    // ---- spatiotemporal & state
    'af12-unload': (ctx) => {
      const cluster = near(ctx, 13.0, 10.5, 4.0); let visited = false, gone = false;
      ctx.onFrame((t, cam) => { const d = Math.hypot(cam.position.x - 13, cam.position.z - 10.5); if (d < 6) visited = true; if (visited && !gone && d > 16) { gone = true; cluster.forEach((o) => { o.visible = false; ctx.removeBody(o); }); } });
      return { name: 'unloaded crate cluster', where: 'after you visit the crate cluster north-east of the start and walk away, the whole cluster is unloaded and gone when you come back', at: [13.0, ctx.groundY(13, 10.5) + 0.4, 10.5], category: CAT.state };
    },
    'af13-statereset': (ctx) => {
      const o = prop(ctx, 'barrel_03', 15.0, -15.0); const a = o.position.clone(), b = a.clone(); b.x -= 2.6; b.z += 1.4; let nearIt = false, flips = 0;
      ctx.onFrame((t, cam) => { const d = Math.hypot(cam.position.x - a.x, cam.position.z - a.z); if (d < 6) nearIt = true; if (nearIt && d > 14) { nearIt = false; flips++; const q = flips % 2 ? b : a; moveWithBody(ctx, o, q.x, q.y, q.z); } });
      return { name: 'barrel position resets', where: 'one of the barrels east of the start stands at a different spot each time you come back after walking away (its position resets / jumps about 3 m)', at: at(o, 0.4), category: CAT.state };
    },
    // ---- semantics & world logic
    'af15-spawnpile': (ctx) => {
      const src = [prop(ctx, 'barrel_03', 15.0, -15.0), prop(ctx, 'plastic_crate_01', -10.2, 12.8), prop(ctx, 'metal_jerrycan_green', -11.6, -9.3), prop(ctx, 'wooden_crate_02', 12.4, 12.2)];
      const x0 = 6, z0 = -8, y0 = ctx.groundY(x0, z0);   // sunlit open tarmac south-east of the start (review 2026-09-14: the old spot lay in the gate's shadow)
      for (let i = 0; i < 9; i++) { const c = cloneVisual(src[i % src.length]); c.position.set(x0 + (i % 3) * 0.3, y0 + Math.floor(i / 3) * 0.45, z0 + (i % 2) * 0.25); c.rotation.y += i * 0.7; c.name = 'PILE_' + i; c.userData = { pile: true }; src[0].parent.add(c); }
      ctx.addStaticBox(x0 + 0.3, y0, z0 + 0.15, 0, [0.75, 0.7, 0.6]);   // the heap is solid (review 2026-09-16: walking through it read as a collision bug)
      return { name: 'prop pile', where: 'nine barrels, crates and jerrycans are dumped on top of each other in one solid heap on the open tarmac a few metres south-east of the start (failed spawns)', at: [x0 + 0.3, y0 + 0.6, z0], category: CAT.sem };
    },
    'af16-misrotated': (ctx) => {
      // upside down (review 2026-09-12: a barrier turned 90 degrees could pass as deliberate placement)
      const o = prop(ctx, 'concrete_road_barrier', -2.0, -22.0);
      const h = new ctx.T.Box3().setFromObject(o).getSize(new ctx.T.Vector3()).y;
      o.rotation.z += Math.PI; o.position.y += h; ctx.syncBody(o);
      return { name: 'upside-down barrier', where: 'one concrete road barrier in the north row is UPSIDE DOWN - flipped over and resting on its top while the others stand normally', at: at(o, 0.4), category: CAT.sem };
    },
    'af18-pushcar': (ctx) => {
      // the parked car by the stone gate has a light dynamic chassis: the walker shoves it around (every other vehicle is a static prop)
      const w = ctx.world(); let best = null, bd = 1e9;
      for (const v of w.vehicles) { const d = Math.hypot(v.position.x + 4.2, v.position.z + 5.6); if (d < bd) { bd = d; best = v; } }
      ctx.unparkVehicle(best, 6);
      return { name: 'car pushed by the walker', where: 'the red car parked just south of the start (by the stone gate) rolls / slides away when the walker bumps into it - a parked car that a person can push around', at: [+best.position.x.toFixed(2), +(best.position.y + 0.6).toFixed(2), +best.position.z.toFixed(2)], category: CAT.col, extent_x: 2.5, extent_z: 2.5 };
    },
    'af17-noshadow': (ctx) => {
      // the street lamp east of the start casts no shadow (review 2026-09-14: a barrel's small shadow had to be inspected from up
      // close; a 5 m lamp post throws a long shadow whose absence shows from far away, next to the west lamp's long shadow)
      const o = prop(ctx, 'street_lamp_01', 12.0, -18.0); o.traverse((m) => { if (m.isMesh) m.castShadow = false; });
      return { name: 'street lamp casts no shadow', where: 'the street lamp east of the start (by the east end of the north barrier row) casts NO shadow on the tarmac at all, while the matching lamp on the west side of the strip and every other prop cast long shadows', at: at(o, 2.5), category: CAT.vis };
    },
  };
  window.__AF_BUGS = {
    CATALOG,
    ids: Object.keys(CATALOG),
    apply(id, ctx) { const fn = CATALOG[id]; if (!fn) return null; const ans = fn(ctx); return { id, ...ans }; },
  };
})();
