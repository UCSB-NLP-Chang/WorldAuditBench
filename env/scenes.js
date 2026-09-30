/* env/scenes.js - scene builders and object factories. Fully config-driven, no hardcoded levels.
 * Geometry/mechanism behavior ported line-by-line from reference/buggy-world.html (human-verified prototype). */
import * as THREE from 'three';

/* =========== scene builders =========== */

export async function buildSceneEntry(ctx, sc) {
  if (sc.type === 'corridor') return buildCorridor(ctx, sc);
  if (sc.type === 'vault') return buildVault(ctx, sc);
  if (sc.type === 'gltf') return buildGltf(ctx, sc);
  if (sc.type === 'house') return (await import('./house/house.js')).buildHouse(ctx, sc);
  throw new Error(`unknown scene type: ${sc.type}`);
}

/* env0 corridor. Interior x in [0,L], z in [-W/2,W/2], floor top at y=0, world origin. */
function buildCorridor(ctx, sc) {
  const { MAT, box, worldMeshes } = ctx;
  const L = sc.length ?? 20, W = sc.width ?? 4, H = sc.height ?? 3, T = sc.thickness ?? .4;
  worldMeshes.push(box(L + 2 * T, T, W + 2 * T, MAT.stone, L / 2, -T / 2, 0));            // floor
  worldMeshes.push(box(L + 2 * T, T, W + 2 * T, MAT.stone, L / 2, H + T / 2, 0, ctx.scene, false)); // ceiling
  worldMeshes.push(box(L + 2 * T, H, T, MAT.stone, L / 2, H / 2, -(W + T) / 2));          // south wall
  worldMeshes.push(box(L + 2 * T, H, T, MAT.stone, L / 2, H / 2, (W + T) / 2));           // north wall
  worldMeshes.push(box(T, H, W, MAT.stone, -T / 2, H / 2, 0));                            // west end
  worldMeshes.push(box(T, H, W, MAT.stone, L + T / 2, H / 2, 0));                         // east end
  for (const pt of (sc.partitions || [])) {
    const ow = pt.openWidth, oh = pt.openHeight ?? H, x = pt.x + T / 2;
    const stub = (W / 2 - ow / 2);
    if (stub > 0.01) {
      worldMeshes.push(box(T, H, stub, MAT.stone, x, H / 2, -(ow / 2 + stub / 2)));
      worldMeshes.push(box(T, H, stub, MAT.stone, x, H / 2, ow / 2 + stub / 2));
    }
    if (oh < H - 0.01) worldMeshes.push(box(T, H - oh, ow, MAT.stone, x, oh + (H - oh) / 2, 0));
  }
  for (const lx of (sc.lightsX || [])) {
    const li = new THREE.PointLight(0xffd9a0, 10, 12, 2);
    li.position.set(lx, H - 0.4, 0);
    ctx.scene.add(li);
  }
  const b = new THREE.Box3(new THREE.Vector3(-T, -T, -(W / 2 + T)), new THREE.Vector3(L + T, H + T, W / 2 + T));
  ctx.anchors[sc.id] = {
    box: b, floorY: 0,
    local: (x, z) => new THREE.Vector3(x, 0, z),
    spawn: { pos: new THREE.Vector3(1.2, 0, 0), yawDeg: -90 },
  };
}

/* vault: procedural stone rooms (ported from the prototype's vault section) */
function buildVault(ctx, sc) {
  const { MAT, box, worldMeshes } = ctx;
  const ref = ctx.anchors[sc.origin.scene];
  const V = new THREE.Vector3(
    ref.box.getCenter(new THREE.Vector3()).x + (sc.origin.dx || 0),
    ref.floorY,
    ref.box.getCenter(new THREE.Vector3()).z + (sc.origin.dz || 0));
  const W = sc.width ?? 10, H = sc.height ?? 4.6, L = sc.length ?? 30, T = sc.thickness ?? .4;
  const vf = x => V.x + x;
  const pit = sc.pit;   // {x0,x1,z0,z1} deep pit (optional)

  // floor slabs (hole left at the pit)
  const slabs = pit
    ? [[0, pit.x0, -W / 2, W / 2], [pit.x1, L, -W / 2, W / 2],
       [pit.x0, pit.x1, -W / 2, pit.z0], [pit.x0, pit.x1, pit.z1, W / 2]]
    : [[0, L, -W / 2, W / 2]];
  for (const [x0, x1, z0, z1] of slabs)
    worldMeshes.push(box(x1 - x0, T, z1 - z0, MAT.stone, vf((x0 + x1) / 2), V.y - T / 2, V.z + (z0 + z1) / 2));
  if (pit) {  // pit body: dark lining + bottom (numbers match the prototype)
    const cx = (pit.x0 + pit.x1) / 2;
    worldMeshes.push(box(pit.x1 - pit.x0, T, .24, MAT.dark, vf(cx), V.y - 1.6, V.z + pit.z0 - .12));
    worldMeshes.push(box(pit.x1 - pit.x0, T, .24, MAT.dark, vf(cx), V.y - 1.6, V.z + pit.z1 + .12));
    worldMeshes.push(box(.24, T, pit.z1 - pit.z0, MAT.dark, vf(pit.x0 + .12), V.y - 1.6, V.z));
    worldMeshes.push(box(.24, T, pit.z1 - pit.z0, MAT.dark, vf(pit.x1 - .12), V.y - 1.6, V.z));
    worldMeshes.push(box(pit.x1 - pit.x0, .2, pit.z1 - pit.z0, MAT.dark, vf(cx), V.y - 3, V.z));
    for (const [x0, x1, z0, z1] of [
      [pit.x0, pit.x1, pit.z0 - .12, pit.z0], [pit.x0, pit.x1, pit.z1, pit.z1 + .12],
      [pit.x0 - .12, pit.x0, pit.z0, pit.z1], [pit.x1, pit.x1 + .12, pit.z0, pit.z1]])
      worldMeshes.push(box(x1 - x0, 3, z1 - z0, MAT.dark, vf((x0 + x1) / 2), V.y - 1.5, V.z + (z0 + z1) / 2));
  }
  const wall = (x0, x1, z0, z1, h = H) => worldMeshes.push(
    box(Math.max(x1 - x0, T), h, Math.max(z1 - z0, T), MAT.stone,
      vf((x0 + x1) / 2), V.y + h / 2, V.z + (z0 + z1) / 2));
  wall(0, L, -W / 2 - T, -W / 2);
  wall(0, L, W / 2, W / 2 + T);
  wall(-T, 0, -W / 2, W / 2);
  wall(L, L + T, -W / 2, W / 2);
  for (const pt of (sc.partitions || [])) {
    const ow = pt.openWidth, oh = pt.openHeight ?? H;
    wall(pt.x, pt.x + T, -W / 2, -ow / 2);
    wall(pt.x, pt.x + T, ow / 2, W / 2);
    if (oh < H - 0.01)
      worldMeshes.push(box(T, H - oh, ow, MAT.stone, vf(pt.x + T / 2), V.y + oh + (H - oh) / 2, V.z));
  }
  worldMeshes.push(box(L + 2 * T, T, W + 2 * T, MAT.stone, vf(L / 2), V.y + H + T / 2, V.z, ctx.scene, false));

  const b = new THREE.Box3(
    new THREE.Vector3(vf(-T), V.y - (pit ? 3.2 : T), V.z - W / 2 - T),
    new THREE.Vector3(vf(L + T), V.y + H + T, V.z + W / 2 + T));
  ctx.anchors[sc.id] = {
    box: b, floorY: V.y,
    local: (x, z) => new THREE.Vector3(vf(x), V.y, V.z + z),
    spawn: { pos: new THREE.Vector3(vf(2), V.y, V.z), yawDeg: -90 },
  };
}

/* glTF scenes (Sponza / dungeon): per-mesh material clone, optional height normalization, relative placement, material donation */
async function buildGltf(ctx, sc) {
  const gltf = await new Promise((res, rej) =>
    ctx.loader.load(sc.url, res,
      e => { if (e.lengthComputable) ctx.progress(`downloading ${sc.id} ${(e.loaded / e.total * 100).toFixed(0)}%`); },
      rej));
  const model = gltf.scene;
  ctx.scene.add(model);
  model.updateMatrixWorld(true);
  let bbox = new THREE.Box3().setFromObject(model);
  const size = bbox.getSize(new THREE.Vector3());
  const nh = sc.normalizeHeight;
  if (nh && (size.y > nh.max || size.y < nh.min)) {
    const s = nh.to / size.y;
    model.scale.setScalar(s);
    console.log(`[${sc.id}] abnormal size (height ${size.y.toFixed(1)}), auto-scaling x${s.toFixed(2)}`);
    model.updateMatrixWorld(true);
    bbox = new THREE.Box3().setFromObject(model);
  }
  if (sc.alignTo) {
    const ref = ctx.anchors[sc.alignTo.scene];
    const rc = ref.box.getCenter(new THREE.Vector3());
    const c = bbox.getCenter(new THREE.Vector3());
    model.position.x += (rc.x + (sc.alignTo.dx || 0)) - c.x;
    model.position.z += (rc.z + (sc.alignTo.dz || 0)) - c.z;
    model.updateMatrixWorld(true);
    bbox = new THREE.Box3().setFromObject(model);
  }
  let donor = null, maxVol = 0;
  model.traverse(o => {
    if (!o.isMesh) return;
    o.castShadow = o.receiveShadow = true;
    o.material = o.material.clone();          // pitfall #3: glTF shares materials, must clone per mesh
    if (o.material.map) o.material.map.anisotropy = 8;
    if (!o.name) o.name = `${sc.id}_mesh_${ctx.worldMeshes.length}`;
    ctx.worldMeshes.push(o);
    if (sc.materialDonor) {
      const s2 = new THREE.Box3().setFromObject(o).getSize(new THREE.Vector3());
      const v = s2.x * s2.y * s2.z;
      if (v > maxVol && o.material) { maxVol = v; donor = o.material; }
    }
  });
  if (donor) { ctx.MAT[sc.materialDonor].copy(donor); ctx.MAT[sc.materialDonor].side = THREE.FrontSide; }

  const floorPts = ctx.floorPoints(model, bbox);
  ctx.anchors[sc.id] = {
    box: bbox, floorPts,
    floorY: floorPts.length ? floorPts[0].p.y : bbox.min.y,
    spawn: { pos: floorPts.length ? floorPts[0].p.clone() : bbox.getCenter(new THREE.Vector3()), yawDeg: -90 },
    model,
  };
}

/* =========== object factories =========== */

export function buildObject(ctx, ob) {
  const F = FACTORIES[ob.type];
  if (!F) throw new Error(`unknown object type: ${ob.type}`);
  F(ctx, ob);
}

function pendingSolid(ctx, id, obj, label) {
  (ctx._pendingSolids ??= new Map()).set(id, { obj, label });
}
function remember(ctx, id, obj) { (ctx.objectsById ??= new Map()).set(id, obj); }

function makeDoorPanel(ctx, hx, hy, hz, width, sign) {
  const g = new THREE.Group(); g.position.set(hx, hy, hz); ctx.scene.add(g);
  const p = ctx.box(.09, 3.0, width, ctx.MAT.wood, 0, 1.5, sign * width / 2, g);
  ctx.box(.02, .28, .28, ctx.MAT.iron, -.06, 1.5, sign * (width - .3), g, false);
  return { group: g, panelMesh: p, sign };
}

const FACTORIES = {
  /* Hinged wooden door. Single: at=hinge position, sign sets panel direction; double: at=doorway center, width=per-panel width */
  door(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const rec = {
      id: ob.id, kind: 'hinged', panels: [],
      wantOpen: false, effOpen: false, pendingAt: Infinity, delayMs: 0, behavior: 'normal', t: 0,
    };
    if (ob.double) {
      const w = ob.width ?? 1.5;
      const L = makeDoorPanel(ctx, at.x, at.y, at.z - w, w, +1);
      const R = makeDoorPanel(ctx, at.x, at.y, at.z + w, w, -1);
      L.id = `${ob.id}_L`; R.id = `${ob.id}_R`;
      rec.panels.push(L, R);
    } else {
      const P = makeDoorPanel(ctx, at.x, at.y, at.z, ob.width ?? 2, ob.sign ?? 1);
      P.id = ob.id;
      rec.panels.push(P);
    }
    for (const p of rec.panels) {
      p.behavior = 'normal';
      const frozen = ctx.aabbOf(p.group);   // frozen closed-state AABB (feature: mechanism behind ghost/phantom door bugs)
      ctx.addSolidBox(frozen, `door:${p.id}`, () => {
        if (p.behavior === 'ghost' || rec.behavior === 'ghost' || rec.behavior === 'interrupted') return true;
        if (p.behavior === 'phantom' || rec.behavior === 'phantom') return !rec.effOpen;
        return rec.t < 0.25;
      }, 0xff5555);
      ctx.occluders.push(p.panelMesh);
    }
    ctx.doors.set(ob.id, rec);
    remember(ctx, ob.id, rec.panels[0].group);
    ctx.interactables.push({
      ownerId: ob.id,
      meshes: rec.panels.map(p => p.panelMesh),
      prompt: () => rec.wantOpen ? 'E close door' : 'E open door',
      use() { rec.wantOpen = !rec.wantOpen; rec.pendingAt = ctx.simT() + rec.delayMs / 1000; },
    });
    if (ob.target) ctx.registerTarget(ob.target, at.clone().add(new THREE.Vector3(0, 1, 0)));
  },

  /* Portcullis: at=center. Direct interaction only hints (a lever is required) */
  portcullis(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const width = ob.width ?? 3, height = ob.height ?? 3.1;
    const g = new THREE.Group(); g.position.copy(at); ctx.scene.add(g);
    const bars = Math.floor(width / .34);
    for (let i = 0; i <= bars; i++)
      ctx.box(.07, height, .07, ctx.MAT.iron, 0, height / 2, -width / 2 + i * (width / bars), g);
    for (const hy of [.35, height / 2, height - .35])
      ctx.box(.09, .12, width, ctx.MAT.iron, 0, hy, 0, g);
    const rec = {
      id: ob.id, kind: 'portcullis', group: g, baseY: at.y, height,
      wantOpen: false, effOpen: false, pendingAt: Infinity, delayMs: 0, behavior: 'normal', t: 0,
    };
    ctx.addSolidBox(ctx.aabbOf(g), `gate:${ob.id}`, () => {
      if (rec.behavior === 'ghost' || rec.behavior === 'interrupted') return true;
      return !rec.effOpen;
    }, 0xff5555);
    ctx.occluders.push(...g.children);
    ctx.doors.set(ob.id, rec);
    remember(ctx, ob.id, g);
    ctx.interactables.push({
      ownerId: ob.id,
      meshes: [...g.children],
      prompt: () => 'The gate will not budge... (there seems to be a mechanism nearby)',
      use() { ctx.fx.toast?.('It will not move. Look for a mechanism?'); },
    });
    if (ob.target) ctx.registerTarget(ob.target, at.clone().add(new THREE.Vector3(0, 1, 0)));
  },

  /* Lever: links=[door/gate id...] */
  lever(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const g = new THREE.Group(); g.position.copy(at);
    g.rotation.y = (ob.yawDeg ?? 0) * Math.PI / 180;
    ctx.scene.add(g);
    const base = ctx.box(.3, .5, .22, ctx.MAT.stone, 0, .25, 0, g);
    const arm = new THREE.Group(); arm.position.set(0, .5, 0); g.add(arm);
    const rod = ctx.box(.05, .55, .05, ctx.MAT.iron, 0, .27, 0, arm);
    const knob = ctx.box(.11, .11, .11, ctx.MAT.wood, 0, .55, 0, arm);
    arm.rotation.z = .6;
    const rec = { id: ob.id, arm, pulled: false, links: ob.links || [] };
    ctx.levers.set(ob.id, rec);
    remember(ctx, ob.id, g);
    ctx.interactables.push({
      ownerId: ob.id,
      meshes: [base, rod, knob],
      prompt: () => 'E pull lever',
      use() {
        rec.pulled = !rec.pulled;
        for (const id of rec.links) {
          const d = ctx.doors.get(id);
          if (!d) continue;
          d.wantOpen = rec.pulled;
          d.pendingAt = ctx.simT() + d.delayMs / 1000;
        }
      },
    });
    if (ob.target) ctx.registerTarget(ob.target, at);
  },

  /* Chest (may hide a gem) */
  chest(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const g = new THREE.Group(); g.position.copy(at); g.rotation.y = ob.yaw ?? 0; ctx.scene.add(g);
    const body = ctx.box(1.0, .55, .65, ctx.MAT.woodDark, 0, .275, 0, g);
    const lidPivot = new THREE.Group(); lidPivot.position.set(0, .55, -.325); g.add(lidPivot);
    const lid = ctx.box(1.0, .16, .65, ctx.MAT.wood, 0, .08, .325, lidPivot);
    ctx.box(.1, .1, .66, ctx.MAT.iron, 0, .6, 0, g);
    const chest = { id: ob.id, group: g, lidPivot, open: false };
    ctx.chests.set(ob.id, chest);
    remember(ctx, ob.id, g);
    let gemRec = null;
    if (ob.gem) gemRec = makeGem(ctx, { id: ob.gem, pos: at.clone().add(new THREE.Vector3(0, .4, 0)), hidden: true });
    ctx.addUpdater(ob.id, dt => {
      if (chest.open && lidPivot.rotation.x > -1.85)
        lidPivot.rotation.x = THREE.MathUtils.lerp(lidPivot.rotation.x, -1.85, Math.min(1, dt * 7.2));
    });
    ctx.occluders.push(body, lid);
    ctx.interactables.push({
      ownerId: ob.id,
      meshes: [body, lid],
      prompt: () => chest.open ? '' : 'E open chest',
      use() {
        if (chest.open) return;
        chest.open = true;
        if (gemRec) ctx.after(0.35, () => { gemRec.mesh.visible = true; ctx.fx.toast?.('There is something inside!'); });
      },
    });
    if (ob.solid) pendingSolid(ctx, ob.id, g, `chest:${ob.id}`);
    if (ob.target) ctx.registerTarget(ob.target, at);
  },

  gem(ctx, ob) { makeGem(ctx, { id: ob.id, pos: ctx.resolvePos(ob.at), hidden: false, target: ob.target }); },

  crate(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const m = ctx.box(.85, .85, .85, ctx.MAT.wood, at.x, at.y + .425, at.z);
    m.material = m.material.clone();          // texture/color bugs affect only this crate
    m.rotation.y = ctx.rng() * .8;
    remember(ctx, ob.id, m);
    if (ob.solid) { pendingSolid(ctx, ob.id, m, `crate:${ob.id}`); ctx.occluders.push(m); }
    if (ob.target) ctx.registerTarget(ob.target, at);
  },

  /* Stone pillar (decor / occlusion / collision testing) */
  pillar(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const [w, h, d] = ob.size ?? [1.2, 2.8, 1.2];
    const m = ctx.box(w, h, d, ctx.MAT.stone, at.x, at.y + h / 2, at.z);
    remember(ctx, ob.id, m);
    if (ob.solid !== false) { pendingSolid(ctx, ob.id, m, `pillar:${ob.id}`); ctx.occluders.push(m); }
    if (ob.target) ctx.registerTarget(ob.target, at);
  },

  torch(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const g = new THREE.Group(); g.position.copy(at);
    if (ob.scale) g.scale.setScalar(ob.scale);
    ctx.scene.add(g);
    ctx.box(.08, .5, .08, ctx.MAT.woodDark, 0, .25, 0, g, false);
    const flame = new THREE.Mesh(new THREE.ConeGeometry(.09, .26, 8),
      new THREE.MeshBasicMaterial({ color: 0xffa632 }));
    flame.position.y = .62; g.add(flame);
    const light = new THREE.PointLight(0xff9640, 14, 14, 2);
    light.position.y = .7; g.add(light);
    const seed = ctx.rng() * 10;
    let acc = 0;
    ctx.addUpdater(ob.id, dt => {
      acc += dt;
      light.intensity = 12 + Math.sin(acc * 9 + seed) * 2.2 + Math.sin(acc * 23 + seed * 2) * 1.2;
      flame.scale.setScalar(1 + Math.sin(acc * 11 + seed) * .12);
    });
    remember(ctx, ob.id, g);
  },

  /* Portal (teleports on step-on) */
  portal(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const color = new THREE.Color(ob.color ?? '#35e0ff');
    const g = ringVisual(ctx, at, color, 2);
    const rec = {
      id: ob.id, center: at.clone(), radius: ob.radius ?? .9,
      partnerId: ob.partner ?? null,
      exitDir: new THREE.Vector3(...(ob.exitDir ?? [1, 0, 0])),
      armed: true, ring: g.ring,
    };
    ctx.portals.set(ob.id, rec);
    ctx.portalList.push(rec);
    remember(ctx, ob.id, g.group);
    if (ob.target) ctx.registerTarget(ob.target, at);
  },

  /* Navigation target ring (visual only, no teleport) */
  ring(ctx, ob) {
    const at = ctx.resolvePos(ob.at);
    const color = new THREE.Color(ob.color ?? '#35e0ff');
    const g = ringVisual(ctx, at, color, 2);
    let acc = 0;
    ctx.addUpdater(ob.id, dt => {
      acc += dt;
      g.ring.material.emissiveIntensity = 2 + .6 * Math.sin(acc * 3);
      g.ring.rotation.z += dt * .8;
    });
    remember(ctx, ob.id, g.group);
    if (ob.target) ctx.registerTarget(ob.target, at);
  },
};

function ringVisual(ctx, at, color, emissive) {
  const g = new THREE.Group(); g.position.copy(at); ctx.scene.add(g);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(.85, .07, 10, 40),
    new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: emissive, roughness: .3 }));
  ring.rotation.x = Math.PI / 2; ring.position.y = .06; g.add(ring);
  const disc = new THREE.Mesh(new THREE.CircleGeometry(.8, 32),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .28 }));
  disc.rotation.x = -Math.PI / 2; disc.position.y = .05; g.add(disc);
  const light = new THREE.PointLight(color, 8, 8, 2); light.position.y = 1; g.add(light);
  return { group: g, ring };
}

function makeGem(ctx, { id, pos, hidden, target }) {
  const m = new THREE.Mesh(new THREE.OctahedronGeometry(.22), ctx.MAT.gem.clone());
  m.position.set(pos.x, pos.y + .55, pos.z);
  m.castShadow = true;
  m.visible = !hidden;
  ctx.scene.add(m);
  const rec = { id, mesh: m, dead: false, collected: false };
  ctx.gems.set(id, rec);
  ctx.totalGems++;
  remember(ctx, id, m);
  ctx.addUpdater(id, dt => { if (m.visible) m.rotation.y += dt * 1.6; });
  ctx.interactables.push({
    ownerId: id,
    meshes: [m],
    prompt: () => m.visible ? 'E pick up gem' : '',
    use() {
      if (!m.visible || rec.dead) return;     // dead: silently unresponsive (bug)
      m.visible = false;
      rec.collected = true;
      ctx.gemsCollected++;
      ctx.fx.toast?.(`Gems ${ctx.gemsCollected}/${ctx.totalGems}`);
    },
  });
  if (target) ctx.registerTarget(target, pos);
  return rec;
}

/* Freeze solid objects' AABBs only after bug injection (so transform bugs like float show up in collision) */
export function finalizeColliders(ctx) {
  for (const { obj, label } of (ctx._pendingSolids ?? new Map()).values())
    ctx.addSolid(obj, label);
}
