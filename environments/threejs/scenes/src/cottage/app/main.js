// Entry: Mistwood Cottage (upstream MIT project by Amira Deuraseh) with an animated CC0 character
// replacing the capsule placeholder, pointer-lock look, an optional first-person mode and a
// BenchmarkWorld helper for the harness.
import Experience from '../upstream/Experience/Experience.js';
import { CATALOG, applyBug, createBugContext, installHarnessAdapter, installReviewHooks } from './bugs.js';

const experience = new Experience(document.querySelector('canvas.webgl'));

window.BenchmarkWorld = {
  version: 'mistwood-cottage-character-v2',
  get ready() { return !!(experience.world && experience.world.player && experience.world.player.character); },
  get scene() { return experience.scene; },
  get camera() { return experience.camera.instance; },
  get renderer() { return experience.renderer.instance; },
  get player() { return experience.world && experience.world.player; },
  experience,
  // teleport(x, y, z): y may be omitted (null) to stand the capsule on the highest surface at (x, z)
  teleport(x, y, z) {
    const p = experience.world.player;
    if (y === undefined || y === null) {
      const physics = experience.physics;
      const ray = new physics.RAPIER.Ray({ x, y: 20, z }, { x: 0, y: -1, z: 0 });
      const hit = physics.world.castRay(ray, 60, true, undefined, undefined, p.collider);
      const terrain = experience.world.terrain && experience.world.terrain.getElevationFromTerrain(x, z);
      const ground = hit ? 20 - hit.timeOfImpact : (terrain === null || terrain === undefined ? 0 : terrain);
      y = ground + p.options.halfHeight + p.options.radius + 0.03;
    }
    p.rigidBody.setTranslation({ x, y, z }, true);
    p.rigidBody.setNextKinematicTranslation({ x, y, z });
    p.mesh.position.set(x, y + 0.1, z);
    if (p.cameraPOV) p.cameraPOV.snap();
  },
  setView(theta, phi) { const c = experience.world.player.cameraPOV; c.theta = theta; if (phi !== undefined) c.phi = phi; c.snap(); },
  setDistance(d) { const c = experience.world.player.cameraPOV; c.distance = d; c.snap(); },
  setFirstPerson(on) { experience.world.player.cameraPOV.setFirstPerson(on); },
  setCycle(i) { experience.cycles.advanceToSpecificCycle(i); },
  getState() {
    const p = experience.world && experience.world.player;
    if (!p) return { ready: false };
    const t = p.rigidBody.translation();
    const c = p.cameraPOV;
    return { position: [t.x, t.y, t.z], theta: c.theta, phi: c.phi, distance: c.distance, firstPerson: c.firstPerson, cycle: experience.cycles.currentCycle, animation: p.currentAction };
  },
};

// ---- bug injection (?bug=ctXX-slug or the harness config's bug) + harness contract (?harness=1&config=<name>)
(async () => {
  const query = new URLSearchParams(location.search);
  const harnessOn = query.has('harness');
  let hcfg = null;
  if (harnessOn && query.get('config')) { try { hcfg = await (await fetch('/environments/threejs/runtime/configs/' + query.get('config') + '.json')).json(); } catch (e) { hcfg = null; } }
  const bugId = query.get('bug') || (hcfg && hcfg.bug) || null;
  const reviewOn = !harnessOn;   // the review overlay works on the clean scene too (pick a case from it)
  if (!bugId && !harnessOn && !reviewOn) return;
  while (!window.BenchmarkWorld.ready || !experience.world.environment || !experience.world.environment.items) await new Promise((r) => setTimeout(r, 200));
  // skip the intro overlay: press ENTER for the user as soon as loading is done (the controls are gated on it)
  for (let i = 0; i < 300; i++) {
    const btn = document.querySelector('.enter-button');
    const loading = document.querySelector('.loading-progress');
    if (btn && (!loading || /100/.test(loading.textContent) || btn.offsetParent !== null) && !btn.disabled) { btn.click(); break; }
    await new Promise((r) => setTimeout(r, 200));
  }
  await new Promise((r) => setTimeout(r, 1800));
  const ctx = createBugContext(experience);
  // benchmark build: the rope fences are removed from the garden (they hemmed the walker in; review 2026-09-12)
  try { ctx.removeFences(); ctx.rebuildEnvPhysics(); } catch (e) { console.warn('fence removal failed', e); }
  let bugAnswer = null;
  if (bugId) { try { bugAnswer = applyBug(bugId, ctx); if (!bugAnswer) console.warn('unknown bug', bugId); } catch (e) { console.warn('bug apply failed', bugId, e); window.__bugError = String(e && e.stack || e); } }
  if (ctx.physicsDirty) ctx.rebuildEnvPhysics();   // only the cases that ask for it (ghost tree, relocated post): collision follows the collapsed geometry
  window.BenchmarkWorld.bug = bugAnswer; window.BenchmarkWorld.bugCatalog = Object.keys(CATALOG); window.BenchmarkWorld.bugRuntime = ctx;
  if (reviewOn) installReviewHooks(experience, ctx);
  if (harnessOn && window.__installHarness) installHarnessAdapter(experience, ctx, hcfg || { name: query.get('config') || 'cottage' }, bugAnswer, query);
})();
