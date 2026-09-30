# Beyond Fable

**Beyond Fable** is a first-person procedural wilderness explorer built
with TypeScript, Vite, and Three.js. Every page load creates a new open world
with forests, lakes, mountain ranges, snowfields, weather, and a complete
day/night cycle.

The entire landscape is generated at runtime. There is no backend, external
game engine, downloaded asset pack, or prebuilt world map.

## Highlights

- Seeded, seamless terrain spanning rolling valleys, lakes, rocky peaks, and
  wind-shaped snowy mountains
- Dense procedural forests with varied tree species, shapes, branches, leaf
  canopies, and shared wind animation
- Grass, rocks, shrubs, flowers, fallen logs, and discoverable points of
  interest
- Dynamic sun and moon lighting, soft environmental bounce light, shadows,
  fog, rain, clouds, and restrained highlight bloom
- Night sky with a rotating star field, the Milky Way, and occasional aurora
  displays; calm water mirrors the stars
- Depth-based aerial perspective (compositor fog pass) that dissolves far
  ridgelines into the horizon haze
- Kilometres-wide procedural mountain ranges with foothills, wind-drifted
  snow, and temporary footstep trails in the snow
- Rare procedural landmarks: tombstone fields, twisted spires, floating
  islands, colossal flora, fossils, and monolith rings
- Bioluminescent mushrooms, luminous flowers, and drifting fireflies at night
- Animated reflective water with shoreline foam, player ripples, underwater
  visuals, and full 3D swimming
- Live atmosphere console for changing time, weather, wind, fog, lighting, and
  exposure
- Chunk streaming, instancing, vegetation LOD, batched distant trees, and
  adaptive render resolution

## Run Locally

Requires a current Node.js release and npm.

```bash
npm install
npm run dev
```

Open the printed URL, normally `http://localhost:5173`, then click the game to
lock the pointer.

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite development server |
| `npm run build` | Typecheck and create the production build in `dist/` |
| `npm run preview` | Preview the production build locally |
| `npm run typecheck` | Run TypeScript checks only |

## Controls

| Input | Action |
| --- | --- |
| Click | Lock pointer and enter the world |
| Mouse | Look around |
| `W A S D` | Walk or swim |
| `Shift` | Sprint or move faster while flying/swimming |
| `Space` | Jump or swim/fly upward |
| `Z` | Swim/fly downward |
| `F` | Toggle fly mode |
| `E` | Inspect a nearby point of interest |
| `R` | Randomize the current time, weather, and wind |
| `T` | Toggle HUD text |
| `~` | Open or close the atmosphere console |
| `Esc` | Release the pointer |

Swimming follows the camera direction and stops at the water surface, keeping
the horizon visible without allowing water-powered flight.

## Atmosphere Console

Press `~` to edit the current world's atmosphere without regenerating its
terrain. The console provides live controls for:

- Time of day and day-cycle speed
- Weather and automatic weather changes
- Cloud cover, cloud darkness, and rain
- Wind strength and direction
- Fog density, world lighting, and exposure

Pressing `R` directly randomizes these atmospheric variables while preserving
the current seed and world layout.

## Seeds And Debugging

Each refresh generates a new seed and starts with randomized time and weather.
Use URL parameters to create repeatable worlds or test specific conditions:

```text
?seed=777
?seed=beyondfable
?tod=0.75
?weather=rain
?stats=1
?noui=1
```

| Parameter | Effect |
| --- | --- |
| `seed` | Generate a deterministic world from a number or string |
| `tod` | Force time of day from `0` to `1` |
| `weather` | Force `clear`, `breezy`, `cloudy`, `lowclouds`, `overcast`, or `rain` |
| `stats=1` | Log renderer statistics and the chunk LOD grid |
| `noui=1` | Hide the HUD for clean screenshots |

Terrain and placement generation are deterministic for a given seed. Time,
weather, and wind remain dynamic.

## Procedural World

### Terrain And Biomes

Terrain height is an analytic function of the seed and world coordinates. It
combines domain-warped continent noise, rolling hills, broad mountain masks,
ridged peaks, erosion-style shaping, and small surface detail. Since the field
is sampled directly, streamed chunks meet seamlessly and gameplay systems can
query terrain height anywhere.

Moisture, altitude, slope, and additional noise fields define forests,
grasslands, shores, exposed rock, and snow. Snow coverage varies with local
drifts, wind scour, and slope so mountain tops retain readable relief instead
of becoming a flat white band.

### Vegetation

Trees are generated from reusable procedural templates with multiple species
and variants. Detailed trees contain tapered trunks, branches, coherent leaf
clusters, and wind-reactive foliage. Forest-mask noise creates dense woods,
clearings, and natural transitions rather than distributing trees uniformly.

Grass is rendered as dense instanced clumps, follows the rendered terrain
surface, and bends through a shared gusting wind field. Nearby vegetation uses
detailed templates while distant tree instances are simplified and batched
across multiple chunks.

### Water

Water chunks use a shared custom shader with animated wave normals, analytic
sky reflection, Fresnel response, depth tint, shoreline foam, and movement
ripples. Above and below the surface use different shading paths, with
underwater fog and refraction-style coloring completing the transition.

### Sky, Weather, And Lighting

A procedural sky dome renders the atmosphere gradient, sun, moon, stars, and
wind-driven cloud layers. The environment system advances a full day/night
cycle and blends between clear, breezy, cloudy, low-cloud, overcast, and rainy
conditions.

Lighting combines a shadow-casting sun or moon with hemisphere light,
shadowless fill, and dynamic diffuse irradiance. This keeps occluded areas
readable while preserving directional shadows. ACES tone mapping and a
single-pass highlight glow provide the final presentation.

### Distant Vistas

Beyond the streamed gameplay chunks, one coarse terrain mesh samples the same
height field across roughly eight kilometres. It supplies mountain silhouettes
and forest-tinted hills at minimal draw-call cost, rebuilding incrementally as
the player travels.

## Performance Design

The world is designed to remain dense without sending every object as an
individual draw call:

- The world streams in `96 m` chunks and disposes geometry after it leaves the
  active radius.
- Trees, grass, rocks, shrubs, flowers, and other repeated objects use
  `InstancedMesh`.
- Distant trees use simplified procedural templates batched across groups of
  chunks.
- Grass and small props are omitted outside the detail radius.
- Terrain normals are calculated analytically, avoiding expensive normal
  rebuilds and visible chunk seams.
- Shared materials, shaders, geometries, and scratch vectors limit CPU work and
  per-frame allocation.
- Pixel ratio is capped by quality preset and automatically reduced after
  sustained low frame rates.
- Bloom is folded into the existing output pass to avoid another full-screen
  post-processing chain.

Quality is selected automatically from hardware hints. To force a preset,
change `quality.forcedLevel` in `src/settings/global-defaults.json` to `low`,
`medium`, or `high`.

## Project Structure

```text
src/
├── core/          Game loop, renderer, player controller, and HUD
├── procedural/    Seeded noise, textures, and shared materials
├── shaders/       Sky, water, grass, and foliage shaders
├── utils/         Random, math, and GPU helpers
└── world/         Terrain, biomes, chunks, vegetation, water, and environment
```

Most visual and gameplay tuning lives in `src/settings/global-defaults.json`.
It includes player movement and camera height, world generation, quality,
grass, rendering, atmosphere, streaming, water, and landmark defaults.
`src/config.ts` exposes those values to TypeScript systems. See `AGENTS.md` for a
detailed architecture guide and contributor conventions.

## GitHub Pages

Pushing to `main` runs `.github/workflows/deploy-pages.yml`. GitHub Actions
installs dependencies, builds `dist/` with the correct relative base path, and
deploys the result to GitHub Pages.

In the repository settings, set **Pages > Build and deployment > Source** to
**GitHub Actions**.

## Known Limitations

- All water shares one global water level; there are no flowing rivers with
  independent gradients.
- Water reflections are analytic sky reflections rather than planar or
  screen-space scene reflections.
- Collision uses terrain height and simple horizontal cylinders, so props
  cannot be climbed.
- There is no audio, persistence, multiplayer, or saved world state.

## License

Released under the [MIT License](LICENSE).
