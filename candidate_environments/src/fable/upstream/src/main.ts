import { Game } from './core/Game';
import { generateRandomSeed, getSeedFromUrl } from './utils/Random';
import { createBugRuntime, applyBug, installHarnessAdapter, installReviewHooks, CATALOG } from './benchmark/bugs';

const params = new URLSearchParams(window.location.search);
const benchmarkMode = params.has('benchmark') || /benchmark/.test(window.location.hash);
// harness mode (?harness=1&config=<name>): the config fixes the world seed (worldSeed) and names the bug; the
// runner's own &seed= is an episode seed and must not change the world
const harnessMode = params.has('harness');
let harnessCfg: any = null;
let seed = 0;
async function loadHarnessConfig(): Promise<any> {
  if (!harnessMode || !params.get('config')) return null;
  try { return await (await fetch('/env/configs/' + params.get('config') + '.json')).json(); } catch { return null; }
}

function installBenchmarkWorld(game: Game): void {
  const handles = game.getBenchmarkHandles();
  (window as unknown as { BenchmarkWorld: unknown }).BenchmarkWorld = {
    version: 'beyond-fable-v2',
    sourceRepository: 'https://github.com/xikhar/beyond-fable',
    seed,
    ready: true,
    ...handles,
    addObject: (o: import('three').Object3D) => { handles.root.add(o); return o; },
    reset: () => location.reload(),
  };
  if (benchmarkMode || harnessMode) game.enterBenchmarkMode();
  // bug injection (?bug=wlXX-slug or the harness config's bug) + judge answer + harness contract
  const bugId = params.get('bug') || (harnessCfg && harnessCfg.bug) || null;
  const bw = (window as any).BenchmarkWorld;
  const ctx = createBugRuntime(handles);
  let bugAnswer: any = null;
  if (bugId) {
    try { bugAnswer = applyBug(bugId, ctx); if (!bugAnswer) console.warn('unknown bug', bugId); }
    catch (e) { console.warn('bug apply failed', bugId, e); }
  }
  bw.bug = bugAnswer; bw.bugCatalog = Object.keys(CATALOG); bw.bugRuntime = ctx;
  installReviewHooks(handles);
  game.onFrame = () => { if ((handles as any).onBenchmarkFrame) (handles as any).onBenchmarkFrame(); };
  if (harnessMode && (window as any).__installHarness) installHarnessAdapter(handles, ctx, harnessCfg || { name: params.get('config') || 'wilderness' }, bugAnswer, params);
}

(async () => {
  harnessCfg = await loadHarnessConfig();
  // Deterministic world with ?seed=12345 (or any string); random otherwise.  A harness config fixes the world seed;
  // a plain ?bug= view defaults to the world the catalogue was authored for (seed 7).
  seed = (harnessCfg && harnessCfg.worldSeed !== undefined && harnessCfg.worldSeed !== null)
    ? (Number(harnessCfg.worldSeed) >>> 0)
    // a ?bug= view always uses seed 7: the catalogue is only valid there (the review site appends its own &seed=, which
    // used to pick a different world and left every position-authored bug undeployed - review 2026-09-14)
    : (params.has('bug') ? 7 : (getSeedFromUrl() ?? generateRandomSeed()));
  if (params.has('noui')) {
    // Clean screenshot mode: no HUD, no loading screen, world straight away.
    document.getElementById('hud')!.style.display = 'none';
    document.getElementById('loading-screen')!.style.display = 'none';
    const game = new Game(seed);
    game.start();
    installBenchmarkWorld(game);
  } else {
    // Let the loading screen paint a frame first, then forge the world behind it
    // (the heavy build blocks the main thread, but the loading animation is
    // composited so it keeps moving). Once ready, the loading screen lets the
    // player click into an already-loaded world.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const game = new Game(seed);
        game.start();
        installBenchmarkWorld(game);
        if (!benchmarkMode && !harnessMode) game.runIntro();
      });
    });
  }
})();
