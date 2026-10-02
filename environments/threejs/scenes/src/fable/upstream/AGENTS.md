# AGENTS.md — Beyond Fable

Guide for AI agents and developers working on this codebase.

## Project summary

**Beyond Fable** is a browser-based, first-person procedural wilderness explorer built with **TypeScript**, **Vite**, and **Three.js**. Every page load generates a new seeded open world: terrain, forests, grass, rocks, water, sky, day/night, weather, and interactables. There is no backend, no downloaded asset packs, and no external game engine.

Design goals: Skyrim/Elden Ring-inspired scale and atmosphere, fully procedural geometry/textures/shaders, chunked streaming, and laptop-friendly performance via instancing, LOD, and fog.

---

## Commands

```bash
npm install          # install deps
npm run dev          # dev server (default http://localhost:5173)
npm run build        # tsc + production bundle → dist/
npm run preview      # serve production build
npm run typecheck    # TypeScript only
```

Always run `npm run typecheck` (or `npm run build`) after substantive edits.

---

## Tech stack

| Layer    | Choice                                                                  |
| -------- | ----------------------------------------------------------------------- |
| Language | TypeScript (strict)                                                     |
| Bundler  | Vite 5                                                                  |
| 3D       | Three.js 0.165 (WebGL2)                                                 |
| Assets   | 100% procedural (canvas textures, shaders, generated geometry)          |
| Physics  | Custom: analytic terrain height + cylinder push-out (no physics engine) |

---

## Directory layout

```
beyond-fable/
├── index.html              # HUD DOM + canvas mount (#app)
├── src/
│   ├── main.ts             # Entry: seed from URL, start Game
│   ├── config.ts           # Typed exports backed by settings/global-defaults.json
│   ├── settings/
│   │   └── global-defaults.json # ★ Editable global world/gameplay/render defaults
│   ├── styles.css          # HUD / overlay styles
│   │
│   ├── core/               # Application shell
│   │   ├── Game.ts         # Main loop, quality fallback, wires all systems
│   │   ├── Renderer.ts     # WebGLRenderer + EffectComposer post chain
│   │   ├── CameraController.ts  # FPS walk + fly mode, terrain collision
│   │   └── Hud.ts          # FPS, seed, time/weather, interact UI, hack menu
│   │
│   ├── render/
│   │   └── AerialFogPass.ts # Scene render + depth-based distance-fog composite
│   │
│   ├── world/              # Scene content & simulation
│   │   ├── World.ts        # ★ Top-level world composition root
│   │   ├── Terrain.ts      # Analytic height field + chunk mesh builder
│   │   ├── Biomes.ts       # Moisture, forest mask, ground color, placement rules
│   │   ├── ChunkManager.ts # ★ Chunk streaming, LOD, build/grass/tree-batch queues
│   │   ├── FarTerrain.ts   # Distant ~11 km horizon mesh (1 draw call)
│   │   ├── Environment.ts  # ★ Day/night, weather, wind, lights, rain, torch
│   │   ├── Sky.ts          # Sky dome mesh + shader uniforms
│   │   ├── Water.ts        # Water chunk meshes + player ripple state
│   │   ├── Vegetation.ts   # Chunk-streaming facade over the vegetation/ grammar
│   │   ├── GrassSettings.ts # Runtime-tunable grass params (hack menu)
│   │   ├── Rocks.ts        # Props class: boulders, stones, logs, shrubs, flowers
│   │   ├── Structures.ts   # Fantasy landmarks (spires, floating islands, fossils…)
│   │   ├── Glow.ts         # Bioluminescent plants + fireflies (night)
│   │   ├── SnowTrail.ts    # Temporary footstep depressions in snow
│   │   ├── Clearings.ts    # Deterministic campfire-clearing test (shared by veg + POIs)
│   │   ├── Fire.ts         # Lightable campfire: procedural flame/ember shaders
│   │   └── Interactables.ts # POIs + InteractionSystem (E key)
│   │
│   ├── vegetation/         # ★ Procedural flora kit (no external assets)
│   │   ├── Botany.ts       # Profile/tier/canopy/skeleton type definitions
│   │   ├── TreeCatalog.ts  # TREE_CATALOG presets (spruce, pine, beech, birch, karst, snag, oak, cherry)
│   │   ├── Branching.ts    # Recursive branch growth (tropisms, phyllotaxis, crown envelope)
│   │   ├── MeshForge.ts    # Append-only geometry accumulator (shared by all builders)
│   │   ├── Limbs.ts        # Tube hierarchy meshing for bark
│   │   ├── Foliage.ts      # Real leaf / needle-fan geometry builders
│   │   ├── CardAtlas.ts    # Bakes leafy twigs to a per-species atlas; scatters cluster cards
│   │   ├── Assemble.ts     # Profile + SeedStream → bark + foliage geometry (LOD-aware)
│   │   ├── Undergrowth.ts  # Shrubs, ferns, flowers (same grammar, bush-tuned)
│   │   ├── Sward.ts        # Grass blade-tuft geometry
│   │   └── SeedStream.ts   # Label-forkable seeded RNG for the flora kit
│   │
│   ├── procedural/
│   │   ├── Noise.ts        # Seeded 2D simplex + fBm + ridged
│   │   ├── Textures.ts     # CanvasTexture generators (bark, rock, ground)
│   │   └── Materials.ts    # MaterialLibrary (shared PBR materials per world)
│   │
│   ├── shaders/            # GLSL source strings (imported as TS modules)
│   │   ├── noiseGLSL.ts    # Shared hash/fBm for sky & water
│   │   ├── sky.ts
│   │   ├── grass.ts
│   │   ├── treeWind.ts     # Shared trunk-bend wind material wrapper
│   │   └── water.ts
│   │
│   └── utils/
│       ├── Random.ts       # SeededRandom, combineSeed, URL seed parsing
│       ├── GpuInfo.ts      # WebGL adapter vendor/renderer detection
│       └── MathUtils.ts    # clamp, lerp, smoothstep, damp
│
└── README.md               # User-facing docs
```

> `shaders/leaves.ts` still exists but is **legacy/unused** — foliage now uses
> the card shader defined inline in `Vegetation.ts`. Don't wire new work to it.

---

## Architecture overview

```
main.ts
  └── Game
        ├── Renderer          → WebGL render + EffectComposer post chain + resize
        ├── CameraController  → input, movement, collision
        ├── Hud               → DOM overlay + hack menu
        ├── InteractionSystem → ray-free proximity interact (E)
        └── World
              ├── SnowTrail           (footstep depression texture)
              ├── MaterialLibrary     (once per seed)
              ├── Terrain             (analytic height, mesh sampling)
              ├── Biomes              (moisture/forest/color rules)
              ├── Sky                 (dome shader mesh)
              ├── Environment         (time, weather, lights, rain, shared uniforms)
              ├── Water               (shared shader material)
              ├── Vegetation          (growth-grammar trees + grass tiles + undergrowth)
              ├── Props               (boulders, stones, logs, shrubs, flowers)
              ├── Interactables
              ├── Structures          (super-cell fantasy landmarks)
              ├── Glow                (night bioluminescence + fireflies)
              ├── FarTerrain          (horizon backdrop)
              └── ChunkManager        (streams detail around player)
```

### Frame loop (`Game.tick`)

1. **Update** — gather colliders → `CameraController.update` → `World.update` (chunks, sky, environment, water, far terrain, grass LOD) → interaction → HUD status
2. **Render** — `renderer.render(scene, camera)`, which drives the `EffectComposer` post chain: **scene+depth → AerialFogPass → OutputPass (tone map + bloom) → FXAA**
3. **Perf** — smoothed FPS; auto pixel-ratio reduction if FPS &lt; ~27 for 4s

`World.update` receives `underwater` flag; when true it overrides fog to thick teal (water medium).

---

## Seeding & determinism

- **Random seed**: no `?seed=` param → `generateRandomSeed()` in `main.ts`
- **Fixed seed**: `?seed=12345` or `?seed=anyString` (strings hashed via FNV-style `hashString`)
- All generation uses `combineSeed(worldSeed, …)` so subsystems are independent but reproducible
- Chunk placement uses `combineSeed(seed, cx, cz, salt)` — same chunk coords always produce identical content

**Critical rule**: terrain height at `(x, z)` must be a pure function of seed + coordinates. Never use unseeded `Math.random()` in generation paths.

---

## Terrain system

**File**: `src/world/Terrain.ts`

Height is **analytic** (not baked to textures):

1. Domain-warped coordinates (large warp bends ranges into arcs)
2. Continent noise (lakes in negative basins)
3. Mountain **range mask** (very low frequency) + foothill apron — massifs are
   kilometres-wide domains, not lone cones
4. Rolling hills (damped near water and inside ranges)
5. Averaged ridged crests + mid-frequency craggy relief inside ranges
6. High-frequency detail, faded on mountains so steep faces stay smooth

Chunk geometry also bakes an `aSnow` vertex attribute (from
`Biomes.getSnowFactor`) used by the snow-trail deformation in the terrain
material.

| Method                                         | Purpose                                                                                    |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `getHeightAt(x, z)`                            | True field value; used for biomes, water depth, far terrain                                |
| `getMeshHeightAt(x, z)`                        | Bilinear sample on the **rendered** chunk grid — use for placing grass, props, player feet |
| `getNormalAt(x, z, out)`                       | Central differences of `getHeightAt`                                                       |
| `buildChunkGeometry(cx, cz, segments, biomes)` | Per-chunk `BufferGeometry` with vertex colors                                              |

Chunk meshes are positioned at `(cx * chunkSize, 0, cz * chunkSize)` with **local** vertex positions. Normals are computed analytically (not `computeVertexNormals`) to avoid chunk-edge seams.

`gridStep = chunkSize / terrainSegments` — must stay in sync with `QUALITY_PRESETS.*.terrainSegments`.

---

## Chunk streaming

**File**: `src/world/ChunkManager.ts`

- Chunk size: `WORLD.chunkSize` (96 m)
- **viewRadius**: chunks loaded in a square around player
- **detailRadius**: chunks get full vegetation; beyond → far LOD

**LOD bands** (`VegLevel`):

| Level         | Trees                              | Grass                             | Props         |
| ------------- | ---------------------------------- | --------------------------------- | ------------- |
| `detail`      | Detail (LOD 1) instanced templates | Full tiles                        | Full          |
| `detail-edge` | Same                               | Reduced (`edgeDensityMultiplier`) | Full          |
| `far`         | Far (LOD 2) instanced templates    | None                              | Boulders only |

Build budget driven by `STREAMING.*`: 1 chunk/frame normally, 4/frame while
`totalBuilt < 60`; LOD swaps 2/frame (8 during warmup). Trees are flushed in
batches (`detailTreeBatchSize`, `farTreeBatchSize`) under `treeBatchFlushBudgetMs`;
grass tiles under `grassBuildBudgetMs`. detail↔detail-edge transitions transfer
tree batches and re-thin grass without rebuilding geometry.

Each chunk may include: terrain mesh, water mesh (if submerged), vegetation group, optional interactable, static + veg colliders.

**Disposal**: per-chunk geometry tagged `userData.ownsGeometry = true`; `InstancedMesh.dispose()` frees instance buffers without touching shared template geometry.

---

## Environment (day/night, weather, wind)

**File**: `src/world/Environment.ts`

Central director that owns:

- `timeOfDay` [0..1): 0 midnight, 0.25 sunrise, 0.5 noon, 0.75 sunset
- Night sky extras: `uStarAngle` (celestial rotation of the star field /
  Milky Way) and per-night aurora strength rolled at nightfall
- Weather state machine over `WEATHER_STATES`: `clear`, `breezy`, `cloudy`,
  `lowclouds`, `overcast`, `rain` (each sets cloud cover/darkness, wind, fog
  multiplier, rain). `WEATHER_OPTIONS` is exported for the hack menu.
- **Lights**: directional sun/moon (shadows), shadowless fill, hemisphere, night torch (`PointLight` on player)
- **Fog**: `FogExp2` density/color driven by weather + night
- **Rain**: camera-following `Points` shader
- **`SharedEnvUniforms`**: passed by reference to grass, leaf, water, sky shaders

URL overrides for testing:

- `?tod=0.75` — force time of day
- `?weather=rain` — force weather state

---

## Vegetation

**Facade**: `src/world/Vegetation.ts` — adapts the growth grammar to chunk
streaming, terrain sampling, wind, and biomes.
**Grammar**: `src/vegetation/*` — generates every tree, shrub, fern, and flower
model procedurally, with zero external assets.

### Flora kit (`src/vegetation/`)

A parametric, L-system-style growth pipeline. Each model is grown from its own
label-forkable `SeedStream`, so identical profile + seed always reproduce it:

1. **`TreeCatalog.ts`** — `TREE_CATALOG` presets: `spruce`, `pine`, `beech`,
   `birch`, `karst` (cliff gnarl), `snag` (dead standing), `oak` (tall heavy
   elder oak), `cherry` (rare flowering). Each is a bundle of per-tier branching
   params (`TierParams`) + canopy params (`CanopyParams`) typed in `Botany.ts`.
2. **`Branching.ts`** — `cultivate`: recursive branch polylines walked
   segment-by-segment with up-bias, jitter, cantilever sag; children spawned via
   whorl/spiral phyllotaxis, length shaped by a crown envelope +
   light-competition lean. Produces limbs + leaf tufts (`BranchTree`).
3. **`MeshForge.ts`** + **`Limbs.ts`** — the forge is the shared append-only
   geometry accumulator; `extrudeSkeleton` skins the branch hierarchy into bark
   (root buttress, taper, LOD ring/level culling).
4. **`Foliage.ts`** — real leaf and needle-fan geometry builders.
5. **`CardAtlas.ts`** — `bakeFoliageAtlas` renders a lush leafy twig (dozens of
   real leaf meshes) **once** into a per-species 2×2 atlas via a WebGL render
   target; `scatterCards` then drops big alpha-tested cards at the leaf tufts.
   One card = a whole spray at 2–4 tris — where crown fullness comes from.
   Albedo is sqrt-encoded + CPU edge-bled (clean dark greens, no mip halos).
6. **`Assemble.ts`** — `assembleTree(profile, rng, { lod, bias })` ties it
   together. LOD 0/1/2 drop tube levels and thin/enlarge cards to a card budget.
7. **`Undergrowth.ts`** — shrubs (incl. flowering), ferns, flowers — same grammar,
   bush-tuned params.

### Trees (in `Vegetation.ts`)

- 8 species × `TREE_VARIANTS` (3) detail templates + matching far (LOD 2)
  templates, built once at startup. Foliage atlas + bark wind material per species.
- Foliage card material is a shader defined **inline** in `Vegetation.ts`
  (height-gradient lighting, per-instance hue/contrast). Bark uses the shared
  `treeWind` material.
- Placement: clustered groves via `groveNoise` + `biomes.getTreeDensity`;
  species chosen by height/moisture (`pickTreeSpecies`).
- Instanced per (species, variant); per-instance lean, scale, rot, tint.
- Far LOD: same grammar at LOD 2 (fewer tubes, fatter cards), no shadows.

### Grass (tile-based)

- `GRASS_TILES_PER_CHUNK` (16) independently-culled `InstancedMesh` tiles per
  chunk — keeps off-screen meadow triangles out of the draw entirely.
- Built by a **generator** (`buildGrassTile`) so the streamer can time-slice the
  expensive terrain sampling across frames (`grassBuildBudgetMs`); the RNG
  sequence is identical to a synchronous build, and `gen.return()` releases a
  partial mesh on abort.
- 3 blade-tuft geometries (`Sward.bladeTuft`) selected by camera
  distance in `updateGrassLod`. Instances are stored shuffled, so distance
  thinning is a single `mesh.count` prefix write — no rebuilds, no popping bands.
- Placed via `getMeshHeightAt` + normal tilt; density/coverage from
  `biomes.getGrassFactor`; patch noise drives hue/size; wind wave from Environment.
- Each tile also scatters rarer **undergrowth** (shrubs/ferns/flowers) as
  colony instances.

### Runtime tuning (`GrassSettings`)

`GrassSettings` (defaults from `GRASS` config) is mutable at runtime via the HUD
hack menu — density, height, width, coverage, edge density, undergrowth. The
streamer reads it live; changing it marks grass LOD dirty.

### Placement exclusion

`vegetation.setExclusion(x, z, radius)` — spawn clearing (set in `World.findSpawn`).

---

## Water

**Files**: `src/world/Water.ts`, `src/shaders/water.ts`

- One shared `ShaderMaterial` for all water chunks
- Per-vertex `aDepth` = water level minus terrain height (shoreline foam, depth tint)
- Wind-driven vertex waves + fBm normals
- Player ripples: noisy rings + movement wake (`uPlayerVel`)
- **Double-sided**: above = Fresnel + sky reflection; below = Snell-window refraction approximation
- Underwater detected in `Game` when `camera.y < -0.15`

---

## Far terrain (horizon)

**File**: `src/world/FarTerrain.ts`

- Single coarse mesh (~11 km, ~288 segments) sampling `terrain.getHeightAt`
- Heights = min of 4 taps (never bridges valleys)
- Progressive sink toward player so near chunks hide it
- Rebuilds incrementally (`rowsPerFrame`) when player moves &gt; `rebuildDistance` (420 m) from last center
- `buildNow()` called synchronously at warmup

---

## Player controller

**File**: `src/core/CameraController.ts`

| Mode      | Controls                                                       |
| --------- | -------------------------------------------------------------- |
| Walk      | WASD, Shift sprint, Space jump, mouse look                     |
| Fly (`F`) | WASD, Space up, `Z` down, Shift fast; toggle `F` off → gravity |

Collision:

- Ground: `terrain.getMeshHeightAt` + `PLAYER.eyeHeight`
- Cylinders: tree trunks, boulders (from `ChunkManager.collectCollidersNear`)

---

## Interactables

**Files**: `src/world/Interactables.ts`, `src/world/Clearings.ts`, `src/world/Fire.ts`

- ~22% chance per chunk: marker, crystal, crate, signpost
- `InteractionSystem`: proximity + facing dot product; `E` shows flavor text in HUD
- No raycasting — distance + angle only

### Campfire clearings

- `Clearings.clearingForChunk(seed, cx, cz, terrain, biomes)` is a **pure**
  function: a flat, dry, open grassland chunk may host one clearing (kept well
  inside the chunk). Both `Vegetation` (to pull trees/grass back) and
  `Interactables` (to place the fire) call it independently and agree — no
  shared state.
- `Fire.ts` builds a lightable campfire: scorched-ground decal
  (`createScorchTexture`), stone ring + log teepee, and a hidden fire group
  (procedural flame billboards + GPU embers + base glow) revealed on `E`.
- The flame is a cylindrical-billboard shader (vertex billboards toward the
  camera, fragment carves fbm tongues through a black-body heat ramp, additive
  so renderer bloom finishes it). Each fire bakes its own `aSeed` to desync.
- Lit state lives in `Interactables.litFires` (survives chunk reloads). `World`
  drives one shared, flickering `PointLight` snapped to the nearest lit fire.

---

## Shaders convention

Shaders live as exported GLSL template strings in `src/shaders/*.ts`, not separate `.glsl` files. They are wired via `THREE.ShaderMaterial` with:

- `THREE.UniformsLib.fog` merged where fog is needed
- `#include <fog_vertex>` / `#include <fog_fragment>` in GLSL
- Shared uniforms from `Environment.uniforms` passed **by reference** (same object), not cloned values

Some shaders are colocated with their owner rather than in `shaders/`: the
**foliage card** vertex/fragment shaders live inline in `Vegetation.ts`, and the
**aerial fog** composite lives in `render/AerialFogPass.ts`. `shaders/treeWind.ts`
exports a helper that wraps a base material with trunk-bend wind in instance-local
space.

When adding a new animated outdoor material, prefer consuming `SharedEnvUniforms` for time, wind, sun, and night.

---

## Configuration reference

**File**: `src/settings/global-defaults.json` — edit global tunables here.
`src/config.ts` provides typed named exports for code consumers.

| Constant                        | What it controls                                                                  |
| ------------------------------- | --------------------------------------------------------------------------------- |
| `QUALITY_PRESETS`               | Pixel ratio, shadows, view/detail radius, densities, terrain segments             |
| `FORCED_QUALITY`                | Override auto-detect (`null` = auto)                                              |
| `WORLD.*`                       | Chunk size, water level, terrain noise freqs/amps, snow/treeline                  |
| `PLAYER.*`                      | Movement, jump, fly speeds, collision radius                                      |
| `ATMOSPHERE.*`                  | Base fog, sun/hemi/fill intensities                                               |
| `DAYNIGHT.*`                    | Cycle length, start time, torch params                                            |
| `WEATHER.*`                     | State change intervals, blend rate                                                |
| `GRASS.*`                       | Grass appearance, LOD distances, instance cap, tiles/chunk                        |
| `FOLIAGE.*`                     | Tree/undergrowth card lighting (bottom brightness, gradient, contrast, variation) |
| `NIGHT_SKY.*`                   | Star count, sphere radius, brightness, galaxy/nebula strength                     |
| `CAMERA.*` / `RENDERER.*`       | Camera clipping/FOV; renderer defaults, exposure, bloom                           |
| `STREAMING.*`                   | Chunk build, unload, LOD, grass/tree batching budgets                             |
| `FAR_TERRAIN.*` / `WATER.*`     | Distant terrain and water mesh resolution                                         |
| `SNOW_TRAIL.*` / `STRUCTURES.*` | Snow trail persistence; landmark super-cell size & spawn chance                   |

---

## URL debug parameters

| Param           | Effect                                           |
| --------------- | ------------------------------------------------ |
| `?seed=N`       | Deterministic world                              |
| `?noui=1`       | Hide HUD (screenshots)                           |
| `?stats=1`      | Console: draws, tris, LOD grid every 2s          |
| `?tod=0.5`      | Force time of day [0..1)                         |
| `?weather=rain` | Force weather state                              |
| `?looksky=1`    | Start camera pitched up at the sky (screenshots) |

---

## Performance guidelines for agents

**Do**

- Use `InstancedMesh` for repeated objects (grass, trees, rocks)
- Generate per-chunk geometry once, dispose on unload
- Reuse `THREE.Vector3` / scratch objects in hot paths
- Keep draw calls low; merge static far geometry
- Use fog + far terrain to hide chunk boundaries
- Cap `devicePixelRatio` (see `Renderer`)

**Don't**

- Call `getHeightAt` per frame for thousands of objects without caching
- Create new materials/geometries every frame
- Use `computeVertexNormals` on chunk terrain (causes seams)
- Add downloaded textures or external asset dependencies
- Introduce a physics engine without strong justification

Typical loaded scene: ~100–120 draw calls, ~200–250k visible triangles (high quality, forested area).

---

## Common modification tasks

| Task                           | Where to look                                                                                                        |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| Change world scale / mountains | `settings/global-defaults.json` → `world`                                                                            |
| More/fewer trees or grass      | `settings/global-defaults.json` → `quality.presets` / `grass`                                                        |
| New tree species               | Add a `TreeProfile` preset to `vegetation/TreeCatalog.ts` + `TREE_CATALOG`; route it in `Vegetation.pickTreeSpecies` |
| Tune tree branching/foliage    | `vegetation/TreeCatalog.ts` tier/canopy params (grammar in `Branching.ts`, cards in `CardAtlas.ts`)                  |
| New undergrowth plant          | `vegetation/Undergrowth.ts`; scatter it in `Vegetation.buildGrassTile`                                               |
| New weather type               | `Environment.ts` → `WEATHER_STATES`, transition weights                                                              |
| New interactable type          | `Interactables.ts` → `KINDS`, `build()` switch                                                                       |
| Fix floating props             | Ensure placement uses `terrain.getMeshHeightAt`, not `getHeightAt`                                                   |
| Adjust lighting at night       | `Environment.update` palette + torch params in `DAYNIGHT`                                                            |
| New shader effect on foliage   | Foliage card shader is inline in `Vegetation.ts`; grass in `grass.ts`. Wire uniforms from `Environment.uniforms`     |

---

## TypeScript conventions

- `strict: true`; avoid `any`
- Classes for major systems; pure functions for math/noise
- `readonly` on injected dependencies where possible
- Export types/interfaces alongside classes (`TreePlacement`, `Interactable`, `SharedEnvUniforms`, `CylinderCollider`)
- Comments on non-obvious procedural steps and shader tricks; avoid narrating obvious code
- No placeholders or `TODO` stubs — ship working code

---

## Known limitations (do not "fix" without explicit request)

- Water is a single global `waterLevel` plane, not flowing rivers with gradients
- Water reflections are analytic sky, not screen-space/planar RT
- Tree LOD swaps at chunk boundaries (possible silhouette pop)
- Collision is 2D cylinders + height field (no climbing on rocks)
- No save state, no audio, no multiplayer
- Headless WebGL (CI screenshots) requires SwiftShader flags; real GPU needed for faithful visuals

---

## File dependency graph (simplified)

```
settings/global-defaults.json → config.ts
Random.ts, MathUtils.ts, Noise.ts, GpuInfo.ts
Textures.ts → Materials.ts
Terrain.ts ← Biomes.ts
sky.ts (shader) → Sky.ts
vegetation/ kit: Botany ← TreeCatalog, SeedStream → Branching → MeshForge/Limbs/Foliage
                 → CardAtlas → Assemble; Undergrowth, Sward
Environment.ts → uniforms → grass.ts, treeWind.ts, water.ts, AerialFogPass
                              → Vegetation.ts (inline foliage shader), Water.ts, Glow.ts
GrassSettings.ts (config-backed, runtime-mutable) → Vegetation.ts
Vegetation.ts → vegetation/ grammar; Rocks, Water, Interactables, Structures, Glow
ChunkManager.ts → uses all world generators (+ tree-batch / grass-tile queues)
FarTerrain.ts → Terrain, Biomes
Renderer.ts → EffectComposer (AerialFogPass, OutputPass, FXAA)
World.ts → composes everything
CameraController.ts → Terrain
Game.ts → World, Renderer, CameraController, Hud, Interactables
main.ts → Game
```

---

## Related docs

- `README.md` — install, controls, user-facing feature overview

  When in doubt about intended behavior, check the running game with `npm run dev` and `?seed=777` (good lake + mountains test world).
