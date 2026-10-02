// Reef bug catalogue (WT suite) — injected mutations for the benchmark, one per case, selected with
// `?bug=wtXX`.  Mirrors the SP / HS taxonomy (geometry, collision, visual, state, semantics) plus two
// reef-specific behaviour bugs the reviewer asked for (fish swimming tail-first / upside down).
// Each entry returns the judge answer {name, where, at, category}; behaviour bugs update per frame.
import * as THREE from 'three';

const CAT = { geo: 'geometry-space', col: 'collision-physics', vis: 'visual-consistency', state: 'spatiotemporal-state', sem: 'semantics-logic' };

function byName(root, name, pred = () => true) {
  const out = [];
  root.traverse((o) => { if (o.name === name && pred(o)) out.push(o); });
  return out;
}
function nearest(list, x, z) {
  let best = null, bd = 1e9;
  for (const o of list) { const d = Math.hypot(o.position.x - x, o.position.z - z); if (d < bd) { bd = d; best = o; } }
  return best;
}
function within(list, x, z, r) { return list.filter((o) => Math.hypot(o.position.x - x, o.position.z - z) < r); }
function rockRadius(rock) {
  const bb = new THREE.Box3().setFromObject(rock);
  const s = bb.getSize(new THREE.Vector3());
  return 0.42 * (s.x + s.z) / 2;
}

export const CATALOG = {
  // ---- geometry & space
  'wt01-float': (ctx) => {
    const rock = nearest(ctx.rocks, 5.0, 12.5);          // boulder by the spawn lane
    rock.position.y += 1.6;
    return { name: 'floating boulder', where: 'a boulder hovers about 1.6 m above the sand with open water underneath', at: [rock.position.x, rock.position.y, rock.position.z], category: CAT.geo };
  },
  'wt02-clip': (ctx) => {
    // a school swims half-buried in the open sand lane north of the start (review 2026-09-12: a rock sunk into sand
    // looked natural). The fish keep their boids behaviour; only their vertical band is pinned into the seabed.
    const school = ctx.schools.find((s) => s.count === 6) || ctx.schools[1];
    school.home.set(1.5, -6.3, 5.5); school.radius = 2.4; school.yBand = [-0.45, 0.05];
    return { name: 'fish clipping into the seabed', where: 'a school of barramundi swims HALF-BURIED in the sand of the open lane just north of the start - the fish bodies clip through the seabed, only their backs and fins show above the sand', at: [1.5, -6.0, 5.5], category: CAT.geo, extent_x: 3, extent_z: 3 };
  },
  // wt03-scale retired 2026-09-16 (review round 4): a giant fish clipping through the other schools read as a different bug.
  // wt04-doublespawn retired 2026-09-16 (review round 3): a duplicated rock set read as a floating rock, not a double spawn.
  // ---- collision & physics
  'wt05-airwall': (ctx) => {
    ctx.addCollider({ box: { min: new THREE.Vector3(-9, -6.5, 7.6), max: new THREE.Vector3(9, 0.5, 8.1) } });   // 18 m wide (review 2026-09-14: 8 m could be swum around)
    return { name: 'invisible wall', where: 'an invisible barrier right across the sandy lane a few metres north of the start stops the diver although nothing is visible there', at: [0, -2, 7.85], category: CAT.col };
  },
  // wt06-hole retired 2026-09-14 (review): a buoyant diver with no vertical control "sinking through the sand" read as an
  // arbitrary black hole, not a floor-collision defect; the case has no natural counterpart in a swimming environment.
  'wt07-ghostrock': (ctx) => {
    // the tall boulder north-east of the start (top at -2.2 m: it reaches well above the diver's cruising depth)
    const rock = nearest(ctx.rocks, 12.2, 4.5);
    ctx.removeColliderFor(rock);
    return { name: 'no-collision rock', where: 'the tall boulder north-east of the start (by the coral cluster) has no collision - the diver swims straight through it while every other rock is solid', at: [rock.position.x, rock.position.y + 1.0, rock.position.z], category: CAT.col, extent_x: 1.5, extent_z: 1.5 };
  },
  'wt08-jitter': (ctx) => {
    const c = nearest(ctx.corals.filter((o) => o.name === 'CORAL_STAGHORN'), -7.5, 6.0) || nearest(ctx.corals, -7.5, 6.0);
    const base = c.position.clone();
    ctx.onFrame((t) => { c.position.set(base.x + Math.sin(t * 9) * 0.05, base.y + Math.sin(t * 13) * 0.02, base.z + Math.cos(t * 11) * 0.05); });
    return { name: 'trembling coral', where: 'a staghorn coral shakes / vibrates rapidly in place (physics jitter) instead of swaying gently like its neighbours', at: [base.x, base.y, base.z], category: CAT.col };
  },
  // ---- visual consistency
  'wt09-magenta': (ctx) => {
    const rock = nearest(ctx.rocks, 13.5, -2.5);
    const mat = new THREE.MeshBasicMaterial({ color: 0xff00ff });
    rock.traverse((o) => { if (o.isMesh) o.material = mat; });
    return { name: 'missing-texture rock', where: 'a big rock face renders as flat bright MAGENTA (missing texture placeholder)', at: [rock.position.x, rock.position.y, rock.position.z], category: CAT.vis };
  },
  // wt10-backcull retired 2026-09-16 (review round 3): not findable even with the instructions.
  'wt11-xray': (ctx) => {
    // the silver school that circles the big north-east rock renders on top of everything (review 2026-09-12: the
    // x-ray brain coral made no visible difference)
    const school = ctx.schools.find((s) => s.count === 70) || ctx.schools[3];
    school.mesh.material = school.mesh.material.clone(); school.mesh.material.depthTest = false; school.mesh.renderOrder = 999;
    return { name: 'x-ray fish school', where: 'the school of small silver fish around the big rock north-east of the reef is drawn ON TOP of everything - the fish stay visible through the rock and the corals that should hide them', at: [10, -2.5, -8], category: CAT.vis, global: true };
  },
  'wt14-lodpop': (ctx) => {
    const cluster = within(ctx.corals, 12.0, 1.0, 3.0);
    const proxies = cluster.map((c) => {
      const bb = new THREE.Box3().setFromObject(c); const s = bb.getSize(new THREE.Vector3());
      const m = new THREE.Mesh(new THREE.IcosahedronGeometry(Math.max(s.x, s.z) * 0.55, 0), new THREE.MeshStandardMaterial({ color: 0xc9a27e, roughness: 1 }));
      m.position.copy(c.position); m.position.y += s.y * 0.4; m.visible = false; c.parent.add(m); return m;
    });
    ctx.onFrame((t, cam) => {
      const far = Math.hypot(cam.position.x - 12.0, cam.position.z - 1.0) > 4.5;
      cluster.forEach((c) => { c.visible = !far; }); proxies.forEach((m) => { m.visible = far; });
    });
    return { name: 'coral LOD pop', where: 'a coral cluster shows as crude blocky blobs from a few metres away and pops into detailed corals only when you get very close', at: [12.0, -5.0, 1.0], category: CAT.vis };
  },
  // ---- spatiotemporal & state
  'wt12-unload': (ctx) => {
    // the coral cluster on the mossy rocks west of the start; trigger radii the size of a normal detour (review: 4.5/10 was too strict)
    // review 2026-09-14: "one coral cluster among many" could not be told apart; now the whole landmark rock set unloads
    const rock = nearest(ctx.rocks, -6.0, 8.5); const cx = rock.position.x, cz = rock.position.z;
    const cluster = [rock].concat(within(ctx.corals, cx, cz, 2.6), byName(ctx.reef, 'SEA_FAN').filter((o) => Math.hypot(o.position.x - cx, o.position.z - cz) < 2.6));
    let visited = false, gone = false;
    ctx.onFrame((t, cam) => {
      if (!ctx.diver.isActive()) { visited = false; return; }   // the observer camera before the dive must not arm the trigger
      const d = Math.hypot(cam.position.x - cx, cam.position.z - cz);
      if (d < 5) visited = true;
      if (visited && !gone && d > 8.5) { gone = true; cluster.forEach((c) => { c.visible = false; }); ctx.removeColliderFor(rock); }
    });
    return { name: 'unloaded rock set', where: 'after you swim up to the big mossy rock set west of the start (the large dark rocks with corals growing on them, on your left from the start) and swim away again, the whole rock set with its corals is unloaded - gone when you come back, leaving an empty patch of sand where the rocks stood', at: [cx, -5.6, cz], category: CAT.state, extent_x: 2.6, extent_z: 2.6 };
  },
  // wt13-statereset retired 2026-09-16 (review round 4): the relocated boulder floated above the sand at its second spot and read as a floating-rock bug.
  // ---- semantics & world logic
  'wt15-spawnpile': (ctx) => {
    // review 2026-09-14: a mixed heap of different corals read as corals growing oddly; nine IDENTICAL copies of one coral,
    // all facing the same way, stacked into each other read as a spawn error
    const src = nearest(ctx.corals.filter((o) => o.name === 'CORAL_STAGHORN'), 7.0, 9.5) || within(ctx.corals, 7.0, 9.5, 3.5)[0];
    const at = new THREE.Vector3(2.0, ctx.seabedHeight(2.0, 5.5) - 0.02, 5.5);
    for (let i = 0; i < 9; i++) {
      const c = src.clone(); c.position.set(at.x + (i % 3) * 0.22, at.y + Math.floor(i / 3) * 0.28, at.z + (i % 2) * 0.16);
      c.name = 'CORAL_PILE'; src.parent.add(c);
    }
    return { name: 'coral pile', where: 'nine IDENTICAL copies of the same staghorn coral, all facing exactly the same way, are stacked into one another in a tight heap on the open sand just north of the start (failed spawns)', at: [at.x, at.y, at.z], category: CAT.sem };
  },
  // ---- reef-specific behaviour
  'wt16-fishreverse': (ctx) => {
    const school = ctx.schools.find((s) => s.count === 3) || ctx.schools[0];
    school.reverse = true;
    return { name: 'fish swimming backwards', where: 'the three big barramundi swim TAIL-FIRST - they move in the direction of their tails, heads pointing away from where they go', at: [0, -2.6, 0], category: CAT.sem, global: true };
  },
  'wt17-fishupside': (ctx) => {
    const school = ctx.schools.find((s) => s.count === 9) || ctx.schools[0];
    school.upsideDown = true;
    return { name: 'fish swimming upside down', where: 'a school of barramundi by the eastern ridge swims belly-up (rolled 180 degrees)', at: [6, -3.2, -4], category: CAT.sem, global: true };
  },
};

export function applyBug(id, ctx) {
  const fn = CATALOG[id];
  if (!fn) return null;
  const ans = fn(ctx);
  return { id, ...ans };
}
