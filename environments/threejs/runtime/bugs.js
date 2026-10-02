/* environments/threejs/runtime/bugs.js - bug injector: reads config and applies bugs to the built scene/objects.
 * Registry migrated from reference/bug-walk2.html + buggy-world.html's planted bugs;
 * extended per the Butt et al. 2023 game-bug taxonomy (environment layer only).
 * Note: type/target here are needed to build the world but are never exposed via the __env API. */
import * as THREE from 'three';
import { buildObject } from './scenes.js';

function findMesh(ctx, target) {
  const o = ctx.objectsById?.get(target) ?? ctx.scene.getObjectByName(target);
  if (!o) throw new Error(`bug target not found: ${target}`);
  return o;
}
function findPanel(ctx, target) {
  for (const d of ctx.doors.values())
    if (d.panels) for (const p of d.panels) if (p.id === target) return { door: d, panel: p };
  if (ctx.doors.has(target)) return { door: ctx.doors.get(target), panel: null };
  throw new Error(`door/panel not found: ${target}`);
}

const BUGS = {
  /* L2: air wall - invisible but impassable */
  air_wall(ctx, b) {
    const c = ctx.resolvePos(b.at); c.y += b.dy ?? 1.3;
    const box = new THREE.Box3().setFromCenterAndSize(c, new THREE.Vector3(...(b.size ?? [.35, 2.6, 4.2])));
    ctx.addSolidBox(box, 'bug:air_wall', () => true, 0xffa640);
  },
  /* L2: fake floor - a pit you cannot fall into */
  fake_floor(ctx, b) {
    const c = ctx.resolvePos(b.at); c.y += b.dy ?? -0.05;
    const box = new THREE.Box3().setFromCenterAndSize(c, new THREE.Vector3(...(b.size ?? [2.2, .14, 2.2])));
    ctx.addSolidBox(box, 'bug:fake_floor', () => true, 0x40d0ff);
  },
  /* L1: floating object */
  float(ctx, b) { findMesh(ctx, b.target).position.y += b.dy ?? 0.35; },
  /* L3: portal sends you to the wrong destination */
  portal_misroute(ctx, b) {
    const p = ctx.portals.get(b.target);
    if (!p) throw new Error(`portal not found: ${b.target}`);
    p.partnerId = b.partner;
  },
  /* L3: ghost door - visually open, collider still active */
  door_ghost(ctx, b) {
    const { door, panel } = findPanel(ctx, b.target);
    if (panel) panel.behavior = 'ghost'; else door.behavior = 'ghost';
  },
  /* L3: phantom door - visually closed, passable */
  door_phantom(ctx, b) {
    const { door, panel } = findPanel(ctx, b.target);
    if (panel) panel.behavior = 'phantom'; else door.behavior = 'phantom';
  },
  /* L3: delayed mechanism (set on the door/gate record; takes effect on lever use) */
  mechanism_delay(ctx, b) {
    const d = ctx.doors.get(b.target);
    if (!d) throw new Error(`door/gate not found: ${b.target}`);
    d.delayMs = b.delayMs ?? 2000;
  },
  /* L3 (temporal): frozen animation - torch stops flickering / gem stops spinning; only continuous observation reveals it */
  frozen_anim(ctx, b) {
    if (ctx.freezeUpdaters(b.target) === 0)
      throw new Error(`frozen_anim: no updaters for '${b.target}'`);
  },
  /* temporal: door/gate closes by itself seconds after opening (Invalid Context State Overtime) */
  door_autoclose(ctx, b) {
    const d = ctx.doors.get(b.target);
    if (!d) throw new Error(`door_autoclose: door not found '${b.target}'`);
    d.autoCloseMs = b.afterMs ?? 2000;
  },
  /* temporal: abnormally accelerated mechanism animation (Accelerated Response) */
  anim_accelerated(ctx, b) {
    const d = ctx.doors.get(b.target);
    if (!d) throw new Error(`anim_accelerated: door not found '${b.target}'`);
    d.speedFactor = b.factor ?? 6;
  },
  /* temporal: animation jams midway and still blocks passage (Interrupted Event) */
  anim_interrupted(ctx, b) {
    const d = ctx.doors.get(b.target);
    if (!d) throw new Error(`anim_interrupted: door not found '${b.target}'`);
    d.interruptT = b.t ?? 0.5;
    d.behavior = 'interrupted';
  },
  /* temporal: object drifts back and forth on its own (Invalid Position Overtime) */
  drift(ctx, b) {
    const m = findMesh(ctx, b.target);
    const axis = b.axis ?? 'x', speed = b.speed ?? 0.2, range = b.range ?? 2;
    const base = m.position[axis];
    let dir = 1;
    ctx.addUpdater('bug:drift:' + b.target, dt => {
      m.position[axis] += dir * speed * dt;
      if (m.position[axis] > base + range) dir = -1;
      if (m.position[axis] < base - range) dir = 1;
    });
  },
  /* collision: wall trap - one face of a visible pillar lets you slip in, then seals (embedded in geometry) */
  wall_trap(ctx, b) {
    const c = ctx.resolvePos(b.at);
    const [w, h, d] = b.size ?? [1.2, 2.8, 1.2];
    ctx.box(w, h, d, ctx.MAT.stone, c.x, c.y + h / 2, c.z);   // visible but not in the BVH
    // entrance seal activates only once the player is 0.25m inside: avoids capsule oscillation at the threshold
    const inside = () => {
      const p = ctx.playerPos();
      return Math.abs(p.x - c.x) < w / 2 - 0.25 && Math.abs(p.z - c.z) < d / 2 - 0.25;
    };
    const t = 0.1;
    const mk = (cx, cz, sx, sz, activeFn) => ctx.addSolidBox(
      new THREE.Box3().setFromCenterAndSize(
        new THREE.Vector3(cx, c.y + h / 2, cz), new THREE.Vector3(sx, h, sz)),
      'bug:wall_trap', activeFn, 0xff2222);
    mk(c.x, c.z - d / 2 + t / 2, w, t, inside);        // entrance face (-z): active only from inside -> one-way
    mk(c.x, c.z + d / 2 - t / 2, w, t, () => true);
    mk(c.x - w / 2 + t / 2, c.z, t, d, () => true);
    mk(c.x + w / 2 - t / 2, c.z, t, d, () => true);
  },
  /* interaction: works through a solid barrier (Action through barrier) */
  interact_through_wall(ctx, b) { ctx.noOcclusionFor.add(b.target); },
  /* rendering: full-screen tint / frame pollution (Corrupted Frame) */
  corrupted_frame(ctx, b) {
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(8, 5),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(b.color ?? '#ff0033'),
        transparent: true, opacity: b.opacity ?? 0.35, depthTest: false, depthWrite: false,
      }));
    quad.position.z = -1.2;
    quad.renderOrder = 999;
    ctx.camera.add(quad);
  },
  /* placement: an asset that should not exist appears in the scene (Extra Game Asset) */
  extra_asset(ctx, b) { buildObject(ctx, b.object); },
  /* L3: dead gem - interact does nothing */
  dead_gem(ctx, b) {
    const g = ctx.gems.get(b.target);
    if (!g) throw new Error(`gem not found: ${b.target}`);
    g.dead = true;
  },
  /* L2: no-clip - collision removed */
  no_collision(ctx, b) {
    if (!(ctx._pendingSolids ?? new Map()).delete(b.target))
      console.warn(`no_collision: '${b.target}' had no collider to begin with`);
  },
  /* -- L1 single-frame-visible family (migrated from the bug-walk2 registry) -- */
  missing_tex(ctx, b) {
    const m = findMesh(ctx, b.target);
    m.material.map = null; m.material.color.set(0xff00ff); m.material.needsUpdate = true;
  },
  oversize(ctx, b) { findMesh(ctx, b.target).scale.multiplyScalar(b.factor ?? 2.5); },
  vanish(ctx, b) { findMesh(ctx, b.target).visible = false; },
  tilt(ctx, b) { findMesh(ctx, b.target).rotation.z += THREE.MathUtils.degToRad(b.deg ?? 25); },
  mirrored(ctx, b) { findMesh(ctx, b.target).scale.x *= -1; },
  flip_normals(ctx, b) { findMesh(ctx, b.target).material.side = THREE.BackSide; },
  wrong_mat(ctx, b) {
    const m = findMesh(ctx, b.target);
    m.material.metalness = 1; m.material.roughness = .02; m.material.needsUpdate = true;
  },
  ghost_mesh(ctx, b) {
    const m = findMesh(ctx, b.target);
    m.material.transparent = true; m.material.opacity = .35; m.material.needsUpdate = true;
  },
  emissive(ctx, b) {
    const m = findMesh(ctx, b.target);
    m.material.emissive.set(0x44ff88); m.material.emissiveIntensity = 1.5; m.material.needsUpdate = true;
  },
  no_shadow(ctx, b) { findMesh(ctx, b.target).castShadow = false; },

  /* ==================== gltf mesh-mutation family (Sponza-native bugs) ====================
   * Bugs implemented as mutations of the loaded real scene itself, exploiting its internal
   * consistency (repeated pots / drapes) as the baseline. Selector: b.meshes = child-mesh
   * names inside the loaded gltf (e.g. ["mesh_0_87","mesh_0_88"]). Categories follow the
   * project taxonomy: geometry-space / collision-physics / visual-consistency /
   * spatiotemporal-state / semantics-logic. Static mutations run before the BVH bake, so
   * collision follows the visual automatically; dynamic ones are un-baked and get AABB
   * colliders that track the mesh. */

  /* geometry-space: floating / sunken (clipping) object - world-space offset */
  mesh_offset(ctx, b) {
    ctx.scene.updateMatrixWorld(true);
    const off = new THREE.Vector3(b.dx ?? 0, b.dy ?? 0, b.dz ?? 0);
    for (const m of gltfMeshes(ctx, b)) {
      const p = m.getWorldPosition(new THREE.Vector3()).add(off);
      m.position.copy(m.parent.worldToLocal(p));
    }
  },
  /* geometry-space: abnormal scale vs identical siblings (kept standing on its base) */
  mesh_scale(ctx, b) {
    ctx.scene.updateMatrixWorld(true);
    for (const m of gltfMeshes(ctx, b)) {
      const before = new THREE.Box3().setFromObject(m);
      const c = before.getCenter(new THREE.Vector3());
      m.scale.multiplyScalar(b.factor ?? 2.2);
      m.updateMatrixWorld(true);
      const after = new THREE.Box3().setFromObject(m);
      const ac = after.getCenter(new THREE.Vector3());
      const p = m.getWorldPosition(new THREE.Vector3())
        .add(new THREE.Vector3(c.x - ac.x, before.min.y - after.min.y, c.z - ac.z))
        .add(new THREE.Vector3(b.shift?.[0] ?? 0, 0, b.shift?.[1] ?? 0));   // optional world shift (clear of neighbours)
      m.position.copy(m.parent.worldToLocal(p));
    }
  },
  /* geometry-space: object tilted into the floor - rotated about its base centre (world axis 'x' or 'z')
     and sunk by dy, so one side is below floor level: an unmistakable clipping defect (review 2026-09-12:
     a merely lowered pot read as a shorter pot). Baked into the geometry (gltf child meshes carry their
     vertices in world space with the node origin at (0,0,0), so node rotations would orbit the origin). */
  mesh_tilt(ctx, b) {
    ctx.scene.updateMatrixWorld(true);
    const objs = gltfMeshes(ctx, b);
    const box = new THREE.Box3();
    for (const o of objs) box.expandByObject(o);
    const pivot = new THREE.Vector3((box.min.x + box.max.x) / 2, box.min.y, (box.min.z + box.max.z) / 2);
    const ang = THREE.MathUtils.degToRad(b.deg ?? 22);
    const R = b.axis === 'z' ? new THREE.Matrix4().makeRotationZ(ang) : new THREE.Matrix4().makeRotationX(ang);
    const W = new THREE.Matrix4().makeTranslation(pivot.x, pivot.y + (b.dy ?? 0), pivot.z).multiply(R)
      .multiply(new THREE.Matrix4().makeTranslation(-pivot.x, -pivot.y, -pivot.z));
    for (const m of leafMeshes(objs)) {
      const mw = m.matrixWorld.clone();
      m.geometry = m.geometry.clone();
      m.geometry.applyMatrix4(mw.clone().invert().multiply(W).multiply(mw));
      m.geometry.computeBoundingBox(); m.geometry.computeBoundingSphere();
    }
  },
  /* geometry-space: duplicated object interpenetrating the original */
  mesh_clone(ctx, b) {
    ctx.scene.updateMatrixWorld(true);
    const off = new THREE.Vector3(...(b.offset ?? [0.28, 0, 0.18]));
    for (const m of gltfMeshes(ctx, b)) {
      const c = m.clone();
      c.name = m.name + '_dup';
      m.parent.add(c);
      c.updateMatrixWorld(true);
      const p = c.getWorldPosition(new THREE.Vector3()).add(off);
      c.position.copy(c.parent.worldToLocal(p));
      ctx.worldMeshes.push(...leafMeshes([c]));   // pre-BVH: the duplicate is solid like the original
    }
  },
  /* collision-physics: visible object with no collision (walk straight through) */
  mesh_nosolid(ctx, b) { unbake(ctx, gltfMeshes(ctx, b)); },
  /* collision-physics: floor region loses collision - player falls through intact-looking
     floor into the void and respawns. Region carved at physics level (collideBVH skips it). */
  floor_hole(ctx, b) {
    const c = ctx.resolvePos(b.at);
    const [sx, sz] = b.size ?? [1.7, 1.7];
    // deep box: must carve the walking floor AND any foundation slab beneath it,
    // otherwise the player lands in a crawlspace instead of falling into the void
    const depth = b.depth ?? 4.0;
    ctx.collisionHoles.push(new THREE.Box3().setFromCenterAndSize(
      new THREE.Vector3(c.x, c.y + 0.8 - depth / 2, c.z), new THREE.Vector3(sx, depth, sz)));
  },
  /* collision-physics: object slides back and forth on its own (physics misbehavior) */
  mesh_drift(ctx, b) {
    const meshes = gltfMeshes(ctx, b);
    unbake(ctx, meshes);
    const box = dynBox(ctx, meshes, 'bug:mesh_drift');
    const speed = b.speed ?? 0.3, range = b.range ?? 1.2;
    const dir = new THREE.Vector3(...(b.dir ?? [1, 0, 0])).normalize();
    let s = 0, sign = 1;
    ctx.addUpdater('bug:mesh_drift', dt => {
      const step = sign * speed * dt;
      s += step;
      if (s > range) sign = -1;
      else if (s < -range) sign = 1;
      shiftWorld(meshes, dir.clone().multiplyScalar(step));
      groupBox(meshes, box);
    });
  },
  /* visual-consistency: missing texture - flat magenta */
  mesh_missing_tex(ctx, b) {
    for (const m of leafMeshes(gltfMeshes(ctx, b))) {
      if (b.lit) {   // legacy: keep the lit material, drop the map
        const mat = ownMaterial(m);
        mat.map = null;
        mat.color.set(b.color ?? '#ff00ff');
        mat.needsUpdate = true;
      } else {       // placeholder look: flat unlit colour, no shading (review 2026-09-12)
        m.material = new THREE.MeshBasicMaterial({ color: new THREE.Color(b.color ?? '#ff00ff') });
        m.userData.__ownMat = true;
      }
    }
  },
  /* visual-consistency: one-sided rendering - object invisible when viewed from one side of
     its plane (classic backface-culled wall), still solid, visible from the other side.
     b.normal points toward the side FROM WHICH the object is invisible. */
  mesh_sideview_cull(ctx, b) {
    const meshes = gltfMeshes(ctx, b);
    ctx.scene.updateMatrixWorld(true);
    const c = new THREE.Box3().setFromObject(meshes[0]).getCenter(new THREE.Vector3());
    const n = new THREE.Vector3(...(b.normal ?? [0, 0, 1])).normalize();
    const v = new THREE.Vector3();
    ctx.addUpdater('bug:sideview_cull', () => {
      const vis = ctx.camera.getWorldPosition(v).sub(c).dot(n) < 0;
      for (const m of leafMeshes(meshes)) m.visible = vis;
    });
  },
  /* visual-consistency: occlusion broken - renders on top of everything (x-ray) */
  mesh_xray(ctx, b) {
    for (const m of leafMeshes(gltfMeshes(ctx, b))) {
      const mat = ownMaterial(m);
      mat.depthTest = false;
      mat.depthWrite = false;
      m.renderOrder = 999;
      mat.needsUpdate = true;
    }
  },
  /* spatiotemporal-state: object permanently despawns the moment you look away */
  mesh_vanish_unseen(ctx, b) {
    const meshes = gltfMeshes(ctx, b);
    unbake(ctx, meshes);
    const box = dynBox(ctx, meshes, 'bug:vanish_unseen', () => meshes[0].visible);
    groupBox(meshes, box);
    watchUnseen(ctx, meshes, 'bug:vanish_unseen', () => {
      for (const m of meshes) m.visible = false;   // group or mesh: hides the subtree
      ctx.logEvent('despawn_fired', { mesh: meshes[0].name });
      return true;   // fire once
    });
  },
  /* spatiotemporal-state: object is at a different position after being out of view */
  mesh_move_unseen(ctx, b) {
    const meshes = gltfMeshes(ctx, b);
    unbake(ctx, meshes);
    const box = dynBox(ctx, meshes, 'bug:move_unseen');
    groupBox(meshes, box);
    const off = new THREE.Vector3(...(b.offset ?? [0, 0, -2.4]));
    let flipped = false;
    watchUnseen(ctx, meshes, 'bug:move_unseen', () => {
      shiftWorld(meshes, flipped ? off.clone().negate() : off);
      flipped = !flipped;
      groupBox(meshes, box);
      ctx.logEvent('teleport_fired', { mesh: meshes[0].name, flipped });
      return false;  // re-arm: moves every time it goes unobserved
    });
  },
  /* collision-physics: physics-solver oscillation - the object trembles in place
     (WOB "geometry corruption" family; the look of two interpenetrating colliders
     being pushed apart every frame). Deterministic multi-frequency noise on simT. */
  mesh_tremble(ctx, b) {
    const meshes = gltfMeshes(ctx, b);
    const amp = b.amp ?? 0.025;
    let t = 0;
    const prev = new THREE.Vector3(), cur = new THREE.Vector3();
    ctx.addUpdater('bug:tremble', dt => {
      t += dt;
      // 1.5-2.5 Hz rocking (review 2026-09-12: the former 7-15 Hz buzz looked unreal and was invisible at 2 fps)
      cur.set(
        amp * (Math.sin(t * 9.0) + 0.6 * Math.sin(t * 14.3 + 1.3)),
        amp * 0.5 * Math.abs(Math.sin(t * 11.0 + 0.7)),
        amp * (Math.sin(t * 12.7 + 2.1) + 0.6 * Math.sin(t * 7.3)));
      shiftWorld(meshes, cur.clone().sub(prev));
      prev.copy(cur);
    });
  },
  /* spatiotemporal-state: streaming/cell-unload bug - once the player has visited the
     area (came within enterR) and then leaves (beyond exitR), the object is unloaded
     and never respawns. Distance-triggered: real streaming semantics, not gaze. */
  mesh_despawn_on_leave(ctx, b) {
    const meshes = gltfMeshes(ctx, b);
    unbake(ctx, meshes);
    const box = dynBox(ctx, meshes, 'bug:despawn_leave', () => meshes[0].visible);
    groupBox(meshes, box);
    watchLeave(ctx, meshes, 'bug:despawn_leave', b.enterR ?? 5, b.exitR ?? 9, () => {
      for (const m of meshes) m.visible = false;
      ctx.logEvent('despawn_fired', { mesh: meshes[0].name });
      return true;   // unloaded for good
    });
  },
  /* spatiotemporal-state: unsaved-state bug - each time the player leaves the area,
     the object reverts/relocates to its other position (state not persisted). */
  mesh_reset_on_leave(ctx, b) {
    const meshes = gltfMeshes(ctx, b);
    unbake(ctx, meshes);
    const box = dynBox(ctx, meshes, 'bug:reset_leave');
    groupBox(meshes, box);
    const off = new THREE.Vector3(...(b.offset ?? [0, 0, -2.4]));
    let flipped = false;
    watchLeave(ctx, meshes, 'bug:reset_leave', b.enterR ?? 5, b.exitR ?? 9, () => {
      shiftWorld(meshes, flipped ? off.clone().negate() : off);
      flipped = !flipped;
      groupBox(meshes, box);
      ctx.logEvent('teleport_fired', { mesh: meshes[0].name, flipped });
      return false;  // every leave-and-return desyncs again
    });
  },
  /* semantics-logic: failed spawns pile up at a point - CLONES of real scene props are
     dumped interpenetrating at the target (the originals stay in place). Uses only assets
     that already exist in the scene. b.groups = [{meshes:[names], off:[dx,dy,dz]}] */
  mesh_pile(ctx, b) {
    ctx.scene.updateMatrixWorld(true);
    const target = ctx.resolvePos(b.at);
    for (const g of b.groups) {
      const srcs = gltfMeshes(ctx, { meshes: g.meshes });
      const box = new THREE.Box3();
      for (const m of srcs) { m.updateMatrixWorld(true); box.expandByObject(m); }
      const c = box.getCenter(new THREE.Vector3());
      const shift = new THREE.Vector3(
        target.x + (g.off?.[0] ?? 0) - c.x,
        target.y + (g.off?.[1] ?? 0) - box.min.y,
        target.z + (g.off?.[2] ?? 0) - c.z);
      // optional per-copy tilt / scale about the group's base centre (review 2026-09-14: copies dropped upright next
      // to each other read as clutter; copies tilted into and through each other read as a failed-spawn heap).
      // Baked into cloned geometry, like mesh_tilt (gltf child meshes keep world-space vertices).
      const rot = g.rot ? new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(...g.rot.map(d => THREE.MathUtils.degToRad(d)))) : null;
      const scl = g.scale ? new THREE.Matrix4().makeScale(g.scale, g.scale, g.scale) : null;
      const pivot = new THREE.Vector3(c.x, box.min.y, c.z);
      let W = null;
      if (rot || scl) {
        W = new THREE.Matrix4().makeTranslation(shift.x, shift.y, shift.z)
          .multiply(new THREE.Matrix4().makeTranslation(pivot.x, pivot.y, pivot.z));
        if (rot) W.multiply(rot);
        if (scl) W.multiply(scl);
        W.multiply(new THREE.Matrix4().makeTranslation(-pivot.x, -pivot.y, -pivot.z));
      }
      for (const m of srcs) {
        const cl = m.clone();
        cl.name = m.name + '_pile';
        m.parent.add(cl);
        cl.updateMatrixWorld(true);
        if (W) {
          for (const lm of leafMeshes([cl])) {
            const mw = lm.matrixWorld.clone();
            lm.geometry = lm.geometry.clone();
            lm.geometry.applyMatrix4(mw.clone().invert().multiply(W).multiply(mw));
            lm.geometry.computeBoundingBox(); lm.geometry.computeBoundingSphere();
          }
        } else {
          const p = cl.getWorldPosition(new THREE.Vector3()).add(shift);
          cl.position.copy(cl.parent.worldToLocal(p));
        }
        ctx.worldMeshes.push(...leafMeshes([cl]));   // pre-BVH: the pile is solid
      }
    }
  },
  /* visual-consistency: texture-streaming/LOD pop - beyond the distance threshold the
     material drops to an ultra-low mip (blocky), and pops back sharp when approaching. */
  mesh_lod_pop(ctx, b) {
    if (b.proxy) return meshLodProxy(ctx, b);
    const meshes = leafMeshes(gltfMeshes(ctx, b)).filter(m => m.material && m.material.map);
    if (!meshes.length) throw new Error('mesh_lod_pop: no textured mesh under ' + (b.meshes || []).join(','));
    for (const m of meshes) ownMaterial(m);
    const thresh = b.dist ?? 6.0, hyst = 0.4;
    const highs = meshes.map(m => m.material.map);
    const lows = meshes.map(() => undefined);   // built lazily once images are loaded
    const box = new THREE.Box3(), c = new THREE.Vector3();
    let low = false;
    ctx.addUpdater('bug:lod_pop', () => {
      box.makeEmpty();
      for (const m of meshes) box.expandByObject(m);
      box.getCenter(c);
      meshes.forEach((m, i) => {
        if (lows[i] === undefined && highs[i] && highs[i].image && highs[i].image.width) {
          const cv = document.createElement('canvas');
          cv.width = cv.height = 8;
          cv.getContext('2d').drawImage(highs[i].image, 0, 0, 8, 8);
          const t = new THREE.CanvasTexture(cv);
          t.colorSpace = highs[i].colorSpace;
          t.magFilter = THREE.NearestFilter;
          t.wrapS = highs[i].wrapS; t.wrapT = highs[i].wrapT;
          lows[i] = t;
        }
      });
      const d = ctx.playerPos().sub(c).setY(0).length();
      const want = low ? d > thresh - hyst : d > thresh + hyst;
      if (want !== low) {
        low = want;
        meshes.forEach((m, i) => {
          if (lows[i]) { m.material.map = low ? lows[i] : highs[i]; m.material.needsUpdate = true; }
        });
        ctx.logEvent('lod_pop', { low });
      }
    });
  },
  /* spatiotemporal-state: abrupt color flip over time (no animation, sudden state change)
     [retired from the SP suite 2026-09-01 - no engine causal story; kept for archives] */
  mesh_colorflip(ctx, b) {
    const meshes = gltfMeshes(ctx, b);
    const orig = meshes.map(m => m.material.color.clone());
    const alt = new THREE.Color(b.color ?? '#c03030');
    const period = b.period ?? 3;
    let t = 0, phase = 0;
    ctx.addUpdater('bug:colorflip', dt => {
      t += dt;
      const ph = Math.floor(t / period) % 2;
      if (ph !== phase) {
        phase = ph;
        meshes.forEach((m, i) => { m.material.color.copy(ph ? alt : orig[i]); });
        ctx.logEvent('colorflip', { phase: ph });
      }
    });
  },
};

/* LOD pop, geometry flavour: beyond b.dist the object is drawn as a crude flat-shaded box of its
   bounds (one flat colour), and pops back to the detailed model when approached. */
function meshLodProxy(ctx, b) {
  ctx.scene.updateMatrixWorld(true);
  const objs = gltfMeshes(ctx, b);
  const box = new THREE.Box3();
  for (const o of objs) box.expandByObject(o);
  const size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
  const proxy = new THREE.Mesh(new THREE.BoxGeometry(size.x, size.y, size.z),
    new THREE.MeshStandardMaterial({ color: new THREE.Color(b.color ?? '#8a857c'), roughness: 1, flatShading: true }));
  proxy.position.copy(c); proxy.visible = false; proxy.name = (objs[0].name || 'lod') + '_proxy';
  proxy.castShadow = true; proxy.receiveShadow = true;
  ctx.scene.add(proxy);
  const thresh = b.dist ?? 4.0, hyst = 0.3;
  let low = false;
  ctx.addUpdater('bug:lod_proxy', () => {
    const d = ctx.playerPos().sub(c).setY(0).length();
    const want = low ? d > thresh - hyst : d > thresh + hyst;
    if (want !== low) {
      low = want;
      for (const o of objs) o.visible = !low;
      proxy.visible = low;
      ctx.logEvent('lod_pop', { low });
    }
  });
}

/* ---- helpers for the gltf mesh-mutation family ---- */
/* Named targets. Sponza: child meshes of the loaded gltf (mesh_0_87 ...). House suite
   (2026-09-06): procedural furniture groups (DINING_CHAIR#1 ...) - a group is returned as
   the transform target itself, while material/visibility/collision helpers expand it to its
   child meshes (leafMeshes). Sponza behavior is unchanged (a mesh expands to itself). */
function gltfMeshes(ctx, b) {
  return (b.meshes || []).map(n => {
    const o = ctx.scene.getObjectByName(n);
    if (!o || !(o.isMesh || o.isGroup || o.isObject3D)) throw new Error(`gltf mesh not found: ${n}`);
    return o;
  });
}
function leafMeshes(objs) {
  const out = [];
  for (const o of objs) o.traverse(c => { if (c.isMesh) out.push(c); });
  return out;
}
/* material of a leaf mesh, cloned on first mutation (house furniture instances share materials) */
function ownMaterial(m) {
  if (!m.userData.__ownMat) { m.material = m.material.clone(); m.userData.__ownMat = true; }
  return m.material;
}
function unbake(ctx, meshes) {   // remove from the static collision bake
  for (const m of leafMeshes(meshes)) {
    const i = ctx.worldMeshes.indexOf(m);
    if (i >= 0) ctx.worldMeshes.splice(i, 1);
  }
}
function groupBox(meshes, target) {
  target.makeEmpty();
  for (const m of meshes) { m.updateMatrixWorld(true); target.expandByObject(m); }
  return target;
}
function dynBox(ctx, meshes, label, activeFn = () => true) {
  const box = new THREE.Box3();
  groupBox(meshes, box);
  ctx.addSolidBox(box, label, activeFn, 0xff66ff);
  return box;
}
function shiftWorld(meshes, off) {
  for (const m of meshes) {
    const p = m.getWorldPosition(new THREE.Vector3()).add(off);
    m.position.copy(m.parent.worldToLocal(p));
    m.updateMatrixWorld(true);
  }
}
/* Fires cb when the player LEAVES the object's area after having visited it:
   arm when horizontal distance < enterR, fire when it then exceeds exitR.
   cb returns true to disarm permanently. Streaming/cell semantics (distance, not gaze). */
function watchLeave(ctx, meshes, id, enterR, exitR, cb) {
  let armed = false, done = false;
  const box = new THREE.Box3(), c = new THREE.Vector3();
  ctx.addUpdater(id + ':watch', () => {
    if (done) return;
    box.makeEmpty();
    for (const m of meshes) box.expandByObject(m);
    box.getCenter(c);
    const d = ctx.playerPos().sub(c).setY(0).length();
    if (!armed && d < enterR) armed = true;
    else if (armed && d > exitR) { armed = false; if (cb()) done = true; }
  });
}

/* Fires cb on the seen -> out-of-view transition of the mesh group (with hysteresis).
   cb returns true to disarm permanently, false to re-arm for the next cycle.
   NOTE: gltf child meshes carry their vertices in world space with node origin at (0,0,0),
   so the watch center MUST come from the world AABB, never from getWorldPosition(). */
function watchUnseen(ctx, meshes, id, cb) {
  let seen = false, done = false;
  const box = new THREE.Box3(), center = new THREE.Vector3();
  const vCam = new THREE.Vector3(), vDir = new THREE.Vector3();
  ctx.addUpdater(id + ':watch', () => {
    if (done) return;
    box.makeEmpty();
    for (const m of meshes) box.expandByObject(m);
    box.getCenter(center);
    ctx.camera.getWorldPosition(vCam);
    ctx.camera.getWorldDirection(vDir);
    const to = center.sub(vCam);
    const dist = to.length();
    const dot = to.normalize().dot(vDir);
    if (!seen && dot > 0.75 && dist < 10) seen = true;         // clearly in view
    else if (seen && dot < 0.25) {                             // safely out of view
      seen = false;
      if (cb()) done = true;
    }
  });
}

export function applyBugs(ctx, bugs) {
  for (const b of bugs) {
    const fn = BUGS[b.type];
    if (!fn) throw new Error(`unknown bug type: ${b.type}`);
    fn(ctx, b);
  }
}
