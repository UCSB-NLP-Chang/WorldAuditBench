import * as THREE from 'three';
import { FOLIAGE, GRASS, WORLD, type QualitySettings } from '../config';
import { Noise2D } from '../procedural/Noise';
import type { MaterialLibrary } from '../procedural/Materials';
import { GRASS_FRAGMENT, GRASS_VERTEX } from '../shaders/grass';
import { createWindTrunkMaterial } from '../shaders/treeWind';
import { combineSeed, SeededRandom } from '../utils/Random';
import { bakeFoliageAtlas } from '../vegetation/CardAtlas';
import { bladeTuft } from '../vegetation/Sward';
import { SeedStream } from '../vegetation/SeedStream';
import { TREE_CATALOG } from '../vegetation/TreeCatalog';
import { assembleTree } from '../vegetation/Assemble';
import {
  FERN_PROTO,
  SHRUB_CATALOG,
  assembleFern,
  assembleFlower,
  assembleShrub,
  type BloomKind,
} from '../vegetation/Undergrowth';
import type { TreeProfile } from '../vegetation/Botany';
import type { CylinderCollider } from '../core/CameraController';
import type { SharedEnvUniforms } from './Environment';
import type { Biomes } from './Biomes';
import type { Terrain, HeightField } from './Terrain';
import type { GrassSettings } from './GrassSettings';
import { clearingForChunk, CLEARING_BARE_RADIUS } from './Clearings';

export interface TreePlacement {
  x: number;
  y: number;
  z: number;
  species: string;
  scale: number;
  rotY: number;
  lean: number;
  leanDir: number;
  tint: number;
  variant: number;
}

export const GRASS_TILES_PER_CHUNK = GRASS.tilesPerChunk;
const GRASS_TILE_SIZE = WORLD.chunkSize / Math.sqrt(GRASS_TILES_PER_CHUNK);

interface TreeTemplate {
  bark: THREE.BufferGeometry;
  foliage: THREE.BufferGeometry | null;
  barkMaterial: THREE.Material;
  foliageMaterial: THREE.Material | null;
  collisionRadius: number;
}

interface UndergrowthTemplate {
  bark: THREE.BufferGeometry | null;
  foliage: THREE.BufferGeometry;
  barkMaterial: THREE.Material | null;
  foliageMaterial: THREE.Material;
}

const TREE_VARIANTS = 3;
const UNDERGROWTH_VARIANTS = 2;
const UP = new THREE.Vector3(0, 1, 0);
const IDENTITY_QUAT = new THREE.Quaternion();
const FLOWER_KINDS: readonly BloomKind[] = ['umbel', 'bell', 'daisy'];

const FOLIAGE_VERTEX = /* glsl */ `
#include <common>
#include <fog_pars_vertex>

attribute vec4 vdata;
attribute float aHeightGradient;
uniform float uTime;
uniform vec2 uWindDir;
uniform float uWindStrength;
varying vec2 vUv;
varying vec4 vData;
varying float vHeightGradient;
varying vec3 vInstanceColor;

void main() {
  vUv = uv;
  vData = vdata;
  vHeightGradient = aHeightGradient;
  #ifdef USE_INSTANCING_COLOR
    vInstanceColor = instanceColor;
  #else
    vInstanceColor = vec3(1.0);
  #endif
  vec3 transformed = position;
  #ifdef USE_INSTANCING
    vec4 worldOrigin = modelMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);
  #else
    vec4 worldOrigin = modelMatrix * vec4(0.0, 0.0, 0.0, 1.0);
  #endif
  float phase = vdata.z + worldOrigin.x * 0.17 + worldOrigin.z * 0.13;
  float wave = sin(uTime * 1.15 + phase) * 0.65 + sin(uTime * 0.47 + phase * 1.7) * 0.35;
  float sway = wave * uWindStrength * vdata.y * 0.16;
  transformed.x += uWindDir.x * sway;
  transformed.z += uWindDir.y * sway;
  #ifdef USE_INSTANCING
    vec4 mvPosition = modelViewMatrix * instanceMatrix * vec4(transformed, 1.0);
  #else
    vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
  #endif
  gl_Position = projectionMatrix * mvPosition;
  #include <fog_vertex>
}
`;

const FOLIAGE_FRAGMENT = /* glsl */ `
#include <common>
#include <fog_pars_fragment>
uniform sampler2D uMap;
uniform vec3 uSunColor;
uniform vec3 uAmbientColor;
uniform vec3 uGroundBounceColor;
uniform float uNight;
uniform float uBottomBrightness;
uniform float uGradientCurve;
uniform float uColorContrast;
uniform float uColorVariation;
varying vec2 vUv;
varying vec4 vData;
varying float vHeightGradient;
varying vec3 vInstanceColor;

void main() {
  vec4 tex = texture2D(uMap, vUv);
  if (tex.a < 0.42) discard;
  vec3 albedo = tex.rgb * tex.rgb;
  float hue = vData.x * 0.12;
  albedo *= vec3(1.0 + hue, 1.0, 1.0 - hue * 0.7);
  float colorSeed = fract(vData.z * 0.618 + vData.x * 1.713);
  vec3 cool = vec3(0.72, 0.94, 1.12);
  vec3 warm = vec3(1.18, 1.03, 0.62);
  albedo *= mix(vec3(1.0), mix(cool, warm, colorSeed), uColorVariation);
  albedo = mix(vec3(dot(albedo, vec3(0.299, 0.587, 0.114))), albedo, uColorContrast);
  vec3 light = uAmbientColor * 1.05 + uGroundBounceColor * 0.18 + uSunColor * 0.34;
  light *= 1.0 - uNight * 0.38;
  float heightLight = mix(uBottomBrightness, 1.0, pow(vHeightGradient, uGradientCurve));
  gl_FragColor = vec4(albedo * vInstanceColor * light * vData.w * heightLight, 1.0);
  #include <fog_fragment>
}
`;

const FLOWER_VERTEX = /* glsl */ `
#include <common>
#include <fog_pars_vertex>
attribute vec4 vdata;
uniform float uTime;
uniform vec2 uWindDir;
uniform float uWindStrength;
varying vec4 vData;
void main() {
  vData = vdata;
  vec3 transformed = position;
  float sway = sin(uTime * 1.7 + position.y * 3.0) * uWindStrength * position.y * 0.08;
  transformed.x += uWindDir.x * sway;
  transformed.z += uWindDir.y * sway;
  vec4 mvPosition = modelViewMatrix * instanceMatrix * vec4(transformed, 1.0);
  gl_Position = projectionMatrix * mvPosition;
  #include <fog_vertex>
}
`;

const FLOWER_FRAGMENT = /* glsl */ `
#include <common>
#include <fog_pars_fragment>
uniform vec3 uSunColor;
uniform vec3 uAmbientColor;
varying vec4 vData;
void main() {
  vec3 green = vec3(0.12, 0.28, 0.055);
  vec3 center = vec3(0.95, 0.65, 0.12);
  vec3 petal = vec3(0.82, 0.52, 0.76);
  vec3 color = mix(green, petal, step(0.75, vData.x));
  color = mix(color, center, step(0.25, vData.x) * (1.0 - step(0.75, vData.x)));
  gl_FragColor = vec4(color * (uAmbientColor * 1.8 + uSunColor * 0.9), 1.0);
  #include <fog_fragment>
}
`;

function foliageMaterial(
  texture: THREE.Texture,
  env: SharedEnvUniforms,
): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: FOLIAGE_VERTEX,
    fragmentShader: FOLIAGE_FRAGMENT,
    uniforms: {
      ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog),
      uMap: { value: texture },
      uTime: env.uTime,
      uWindDir: env.uWindDir,
      uWindStrength: env.uWindStrength,
      uSunColor: env.uSunColor,
      uAmbientColor: env.uAmbientColor,
      uGroundBounceColor: env.uGroundBounceColor,
      uNight: env.uNight,
      uBottomBrightness: { value: FOLIAGE.bottomBrightness },
      uGradientCurve: { value: FOLIAGE.gradientCurve },
      uColorContrast: { value: FOLIAGE.colorContrast },
      uColorVariation: { value: FOLIAGE.colorVariation },
    },
    side: THREE.DoubleSide,
    fog: true,
  });
}

function flowerMaterial(env: SharedEnvUniforms): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: FLOWER_VERTEX,
    fragmentShader: FLOWER_FRAGMENT,
    uniforms: {
      ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog),
      uTime: env.uTime,
      uWindDir: env.uWindDir,
      uWindStrength: env.uWindStrength,
      uSunColor: env.uSunColor,
      uAmbientColor: env.uAmbientColor,
    },
    side: THREE.DoubleSide,
    fog: true,
  });
}

/**
 * Vegetation facade. The procedural flora kit (src/vegetation) owns every tree,
 * shrub, fern, and flower model; this class adapts those models to Beyond
 * Fable's chunk streaming, terrain sampling, wind, and biomes.
 */
export class Vegetation {
  private readonly templates = new Map<string, TreeTemplate[]>();
  private readonly farTemplates = new Map<string, TreeTemplate[]>();
  private readonly undergrowth = new Map<string, UndergrowthTemplate[]>();
  private readonly grassGeometries: readonly THREE.BufferGeometry[];
  private readonly grassMaterial: THREE.ShaderMaterial;
  private readonly grassTiles = new Set<THREE.InstancedMesh>();
  private grassLodX = Number.POSITIVE_INFINITY;
  private grassLodZ = Number.POSITIVE_INFINITY;
  private grassLodDirty = true;
  private readonly flowerTemplates: THREE.BufferGeometry[];
  private readonly flowerMaterial: THREE.ShaderMaterial;
  private readonly groveNoise: Noise2D;
  private readonly groundPatchNoise: Noise2D;
  private exclusion: { x: number; z: number; radius: number } | null = null;

  private addFoliageHeightGradient(geometry: THREE.BufferGeometry): void {
    geometry.computeBoundingBox();
    const box = geometry.boundingBox!;
    const span = Math.max(box.max.y - box.min.y, 0.001);
    const position = geometry.getAttribute('position') as THREE.BufferAttribute;
    const gradient = new Float32Array(position.count);
    for (let i = 0; i < position.count; i++) {
      gradient[i] = THREE.MathUtils.clamp((position.getY(i) - box.min.y) / span, 0, 1);
    }
    geometry.setAttribute('aHeightGradient', new THREE.BufferAttribute(gradient, 1));
  }

  constructor(
    private readonly seed: number,
    renderer: THREE.WebGLRenderer,
    materials: MaterialLibrary,
    private readonly quality: QualitySettings,
    env: SharedEnvUniforms,
    private readonly grassSettings: GrassSettings,
  ) {
    this.groveNoise = new Noise2D(combineSeed(seed, 311));
    this.groundPatchNoise = new Noise2D(combineSeed(seed, 312));

    for (let si = 0; si < TREE_CATALOG.length; si++) {
      const species = TREE_CATALOG[si] as TreeProfile;
      const atlas = species.canopy
        ? bakeFoliageAtlas(renderer, species, new SeedStream(combineSeed(seed, 300, si)))
        : null;
      const leafMat = atlas ? foliageMaterial(atlas, env) : null;
      const barkBase = species.kind === 'snag'
        ? materials.deadWood
        : species.id === 'birch' ? materials.barkBirch : materials.bark;
      const barkMat = createWindTrunkMaterial(barkBase, env);
      const detail: TreeTemplate[] = [];
      const far: TreeTemplate[] = [];
      for (let v = 0; v < TREE_VARIANTS; v++) {
        detail.push(this.makeTreeTemplate(species, v, 1, barkMat, leafMat));
        far.push(this.makeTreeTemplate(species, v, 2, barkBase, leafMat));
      }
      this.templates.set(species.id, detail);
      this.farTemplates.set(species.id, far);
    }

    for (let si = 0; si < SHRUB_CATALOG.length; si++) {
      const species = SHRUB_CATALOG[si] as TreeProfile;
      const atlas = bakeFoliageAtlas(renderer, species, new SeedStream(combineSeed(seed, 400, si)));
      const leafMat = foliageMaterial(atlas, env);
      const variants: UndergrowthTemplate[] = [];
      for (let v = 0; v < UNDERGROWTH_VARIANTS; v++) {
        const built = assembleShrub(species, new SeedStream(combineSeed(seed, 410, si, v)));
        this.addFoliageHeightGradient(built.foliage!);
        variants.push({
          bark: built.bark,
          foliage: built.foliage!,
          barkMaterial: materials.bark,
          foliageMaterial: leafMat,
        });
      }
      this.undergrowth.set(species.id, variants);
    }

    const fernAtlas = bakeFoliageAtlas(renderer, FERN_PROTO, new SeedStream(combineSeed(seed, 420)));
    const fernMat = foliageMaterial(fernAtlas, env);
    this.undergrowth.set('fern', Array.from({ length: UNDERGROWTH_VARIANTS }, (_, v) => {
      const foliage = assembleFern(new SeedStream(combineSeed(seed, 421, v)));
      this.addFoliageHeightGradient(foliage);
      return {
        bark: null,
        foliage,
        barkMaterial: null,
        foliageMaterial: fernMat,
      };
    }));

    this.flowerTemplates = FLOWER_KINDS.map((kind, i) =>
      assembleFlower(kind, new SeedStream(combineSeed(seed, 430, i))));
    this.flowerMaterial = flowerMaterial(env);
    this.grassGeometries = [
      bladeTuft(7, 3),
      bladeTuft(3, 2),
      bladeTuft(3, 1),
    ];
    for (const geometry of this.grassGeometries) geometry.deleteAttribute('normal');
    this.grassMaterial = new THREE.ShaderMaterial({
      vertexShader: GRASS_VERTEX,
      fragmentShader: GRASS_FRAGMENT,
      uniforms: {
        ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog),
        uTime: env.uTime,
        uWindDir: env.uWindDir,
        uWindStrength: env.uWindStrength,
        uSunDir: env.uSunDir,
        uSunColor: env.uSunColor,
        uAmbientColor: env.uAmbientColor,
        uGroundBounceColor: env.uGroundBounceColor,
        uNight: env.uNight,
      },
      side: THREE.DoubleSide,
      fog: true,
    });
  }

  setExclusion(x: number, z: number, radius: number): void {
    this.exclusion = { x, z, radius };
  }

  getGrassSettings(): Readonly<GrassSettings> {
    return this.grassSettings;
  }

  private makeTreeTemplate(
    species: TreeProfile,
    variant: number,
    lod: 1 | 2,
    barkMaterial: THREE.Material,
    foliageMaterial: THREE.Material | null,
  ): TreeTemplate {
    const tree = assembleTree(species, new SeedStream(combineSeed(this.seed, 301, variant, species.id.length)), {
      lod,
      bias: {
        maturity: 0.55 + variant * 0.2,
        leanX: variant === 1 ? 0.035 : -0.015 * variant,
        leanZ: variant === 2 ? 0.045 : 0,
      },
    });
    if (tree.foliage) this.addFoliageHeightGradient(tree.foliage);
    return {
      bark: tree.bark,
      foliage: tree.foliage,
      barkMaterial,
      foliageMaterial,
      collisionRadius: tree.metrics.height * species.girth * 0.82,
    };
  }

  /**
   * Swap shared grass geometry by camera distance. Small independently culled
   * tiles keep off-screen meadow triangles out of the draw entirely.
   *
   * Tiles also thin smoothly with distance by lowering instanceCount alone:
   * instances are stored in a shuffled order, so any count prefix is a
   * uniform random subset of the tile. Density transitions are therefore a
   * per-tile integer write - no rebuilds, no popping bands.
   */
  updateGrassLod(playerPos: THREE.Vector3): void {
    const movedX = playerPos.x - this.grassLodX;
    const movedZ = playerPos.z - this.grassLodZ;
    if (!this.grassLodDirty && movedX * movedX + movedZ * movedZ < 2.25) return;
    this.grassLodX = playerPos.x;
    this.grassLodZ = playerPos.z;
    this.grassLodDirty = false;
    const near = this.grassSettings.nearLodDistance;
    const mid = this.grassSettings.midLodDistance;
    const nearSq = near * near;
    const midSq = mid * mid;
    const renderSq = this.grassSettings.renderDistance ** 2;
    const minFraction = THREE.MathUtils.clamp(this.grassSettings.edgeDensityMultiplier, 0.05, 1);
    for (const mesh of this.grassTiles) {
      const dx = mesh.userData.grassCenterX as number - playerPos.x;
      const dz = mesh.userData.grassCenterZ as number - playerPos.z;
      const distSq = dx * dx + dz * dz;
      mesh.visible = distSq < renderSq;
      if (!mesh.visible) continue;
      const lod = distSq < nearSq ? 0 : distSq < midSq ? 1 : 2;
      if (mesh.userData.grassLod !== lod) {
        mesh.geometry = this.grassGeometries[lod];
        mesh.userData.grassLod = lod;
      }
      const fade = THREE.MathUtils.smoothstep(Math.sqrt(distSq), near, mid);
      const fraction = 1 - (1 - minFraction) * fade;
      const full = mesh.userData.grassFullCount as number;
      mesh.count = Math.max(1, Math.round(full * fraction));
    }
  }

  markGrassLodDirty(): void {
    this.grassLodDirty = true;
  }

  unregisterGrass(root: THREE.Object3D): void {
    root.traverse((obj) => {
      if (obj.userData.isGrassTile) this.grassTiles.delete(obj as THREE.InstancedMesh);
    });
    this.grassLodDirty = true;
  }

  private excluded(x: number, z: number): boolean {
    if (!this.exclusion) return false;
    const dx = x - this.exclusion.x;
    const dz = z - this.exclusion.z;
    return dx * dx + dz * dz < this.exclusion.radius * this.exclusion.radius;
  }

  private pickTreeSpecies(x: number, z: number, h: number, moisture: number, r: number): string {
    // High and dry ground stays coniferous.
    if (h > WORLD.treeLine * 0.78 || moisture < 0.34) return r < 0.62 ? 'spruce' : 'pine';
    // A rare flowering cherry, sprinkled thinly across the lowland woods so a
    // few stand out as something special wherever you wander.
    if (r < 0.035) return 'cherry';
    if (r < 0.085) return 'snag';
    if (r < 0.18 && h > 45) return 'karst';
    // Damp lowlands favour heavy broadleaves; the elder oak towers over them.
    if (moisture > 0.68) return r < 0.4 ? 'beech' : r < 0.62 ? 'oak' : r < 0.86 ? 'birch' : 'spruce';
    return r < 0.42 ? 'beech' : r < 0.58 ? 'oak' : r < 0.78 ? 'birch' : r < 0.9 ? 'pine' : 'spruce';
  }

  /** Clustered groves with broad clearings between them. */
  generateTreePlacements(cx: number, cz: number, terrain: Terrain, biomes: Biomes, field: HeightField): TreePlacement[] {
    const rng = new SeededRandom(combineSeed(this.seed, cx, cz, 7001));
    const size = WORLD.chunkSize;
    const ox = cx * size;
    const oz = cz * size;
    const placements: TreePlacement[] = [];
    const normal = new THREE.Vector3();
    // A campfire clearing in this chunk keeps trees out of the open spot.
    const clearing = clearingForChunk(this.seed, cx, cz, terrain, biomes);
    const clearingSq = clearing ? clearing.radius * clearing.radius : 0;
    const attempts = Math.floor(190 * this.quality.treeDensityScale);
    for (let i = 0; i < attempts && placements.length < 58; i++) {
      const x = ox + rng.next() * size;
      const z = oz + rng.next() * size;
      if (this.excluded(x, z)) continue;
      if (clearing && (x - clearing.x) ** 2 + (z - clearing.z) ** 2 < clearingSq) continue;
      const h = field.height(x, z);
      field.normal(x, z, normal);
      const density = biomes.getTreeDensity(x, z, h, normal.y);
      if (density <= 0) continue;
      const grove = this.groveNoise.fbm(x * 0.006, z * 0.006, 3) * 0.5 + 0.5;
      const edge = this.groveNoise.fbm(x * 0.017 + 31, z * 0.017 - 19, 2) * 0.5 + 0.5;
      const accept = Math.min(0.8, density * 22 * (0.15 + grove * grove * 1.9) * (0.55 + edge));
      if (!rng.chance(accept)) continue;
      const moisture = biomes.getMoisture(x, z);
      const species = this.pickTreeSpecies(x, z, h, moisture, rng.next());
      placements.push({
        x,
        y: field.meshHeight(x, z) - 0.18,
        z,
        species,
        scale: rng.range(0.72, 1.28),
        rotY: rng.range(0, Math.PI * 2),
        lean: rng.range(0, 0.035),
        leanDir: rng.range(0, Math.PI * 2),
        tint: rng.next(),
        variant: rng.int(0, TREE_VARIANTS - 1),
      });
    }
    return placements;
  }

  buildTreeColliders(placements: TreePlacement[]): CylinderCollider[] {
    return placements.map((p) => ({
      x: p.x,
      z: p.z,
      radius: this.templates.get(p.species)![p.variant].collisionRadius * p.scale,
    }));
  }

  private buildTrees(placements: TreePlacement[], far: boolean, shadows: boolean): THREE.Group {
    const group = new THREE.Group();
    const source = far ? this.farTemplates : this.templates;
    const matrix = new THREE.Matrix4();
    const pos = new THREE.Vector3();
    const quat = new THREE.Quaternion();
    const euler = new THREE.Euler();
    const scale = new THREE.Vector3();
    const treeTint = new THREE.Color();
    for (const species of TREE_CATALOG) {
      for (let v = 0; v < TREE_VARIANTS; v++) {
        const subset = placements.filter((p) => p.species === species.id && p.variant === v);
        if (subset.length === 0) continue;
        const template = source.get(species.id)![v];
        const bark = new THREE.InstancedMesh(template.bark, template.barkMaterial, subset.length);
        const leaves = template.foliage && template.foliageMaterial
          ? new THREE.InstancedMesh(template.foliage, template.foliageMaterial, subset.length)
          : null;
        for (let i = 0; i < subset.length; i++) {
          const p = subset[i];
          euler.set(Math.cos(p.leanDir) * p.lean, p.rotY, Math.sin(p.leanDir) * p.lean);
          quat.setFromEuler(euler);
          pos.set(p.x, p.y, p.z);
          scale.setScalar(p.scale);
          matrix.compose(pos, quat, scale);
          bark.setMatrixAt(i, matrix);
          if (leaves) {
            leaves.setMatrixAt(i, matrix);
            const tint = p.tint;
            treeTint.setRGB(
              0.72 + tint * 0.32,
              0.78 + (1 - Math.abs(tint - 0.5) * 2) * 0.22,
              0.58 + (1 - tint) * 0.42,
            );
            leaves.setColorAt(i, treeTint);
          }
        }
        bark.instanceMatrix.needsUpdate = true;
        bark.castShadow = shadows;
        bark.receiveShadow = shadows;
        group.add(bark);
        if (leaves) {
          leaves.instanceMatrix.needsUpdate = true;
          if (leaves.instanceColor) leaves.instanceColor.needsUpdate = true;
          leaves.castShadow = shadows;
          group.add(leaves);
        }
      }
    }
    return group;
  }

  buildDetailedTrees(placements: TreePlacement[], shadows = true): THREE.Group {
    return this.buildTrees(placements, false, shadows);
  }

  buildFarTrees(placements: TreePlacement[]): THREE.Group {
    return this.buildTrees(placements, true, false);
  }

  /** Deterministic Fisher-Yates over the first `count` instances. */
  private shuffleInstances(mesh: THREE.InstancedMesh, count: number, seed: number): void {
    const matrices = mesh.instanceMatrix.array as Float32Array;
    const colors = mesh.instanceColor ? (mesh.instanceColor.array as Float32Array) : null;
    let state = seed >>> 0;
    for (let i = count - 1; i > 0; i--) {
      state = (state * 1664525 + 1013904223) >>> 0;
      const j = state % (i + 1);
      if (j === i) continue;
      for (let k = 0; k < 16; k++) {
        const a = i * 16 + k;
        const b = j * 16 + k;
        const t = matrices[a];
        matrices[a] = matrices[b];
        matrices[b] = t;
      }
      if (colors) {
        for (let k = 0; k < 3; k++) {
          const a = i * 3 + k;
          const b = j * 3 + k;
          const t = colors[a];
          colors[a] = colors[b];
          colors[b] = t;
        }
      }
    }
  }

  /**
   * Dense sward: one jittered clump cell across every viable grassland
   * surface. Large patch fields vary height/color while biome rules
   * remove grass from water, snow, bare rock, and steep slopes.
   *
   * Implemented as a generator so the streamer can time-slice the expensive
   * terrain sampling across frames; yields land between cell rows, so the
   * RNG sequence (and therefore every placement) is identical to a
   * synchronous build. Aborting via `gen.return()` releases the partial mesh.
   */
  *buildGrassTile(
    cx: number,
    cz: number,
    tileIndex: number,
    terrain: Terrain,
    biomes: Biomes,
    field: HeightField,
    densityScale = 1,
  ): Generator<void, THREE.Group | null, void> {
    const tilesPerSide = Math.sqrt(GRASS_TILES_PER_CHUNK);
    const tx = tileIndex % tilesPerSide;
    const tz = Math.floor(tileIndex / tilesPerSide);
    const rng = new SeededRandom(combineSeed(this.seed, cx, cz, 7777, tileIndex));
    const size = GRASS_TILE_SIZE;
    const ox = cx * WORLD.chunkSize + tx * size;
    const oz = cz * WORLD.chunkSize + tz * size;
    const group = new THREE.Group();
    const normal = new THREE.Vector3();
    const matrix = new THREE.Matrix4();
    const pos = new THREE.Vector3();
    const tilt = new THREE.Quaternion();
    const yaw = new THREE.Quaternion();
    const quat = new THREE.Quaternion();
    const scale = new THREE.Vector3();
    const color = new THREE.Color();
    const coolGrass = new THREE.Color(0x17462f);
    const warmGrass = new THREE.Color(0x9a7a2c);

    // Strip grass from the trampled centre of a campfire clearing, and keep
    // undergrowth out of the whole open spot.
    const clearing = clearingForChunk(this.seed, cx, cz, terrain, biomes);
    const clearingBareSq = clearing ? CLEARING_BARE_RADIUS * CLEARING_BARE_RADIUS : 0;
    const clearingFullSq = clearing ? clearing.radius * clearing.radius : 0;

    const groundItems = new Map<string, Array<{ matrix: THREE.Matrix4; variant: number }>>();
    const requestedDensity = Math.max(
      0.18,
      this.quality.grassDensity * densityScale * this.grassSettings.densityMultiplier,
    );
    const instanceDensity = Math.min(requestedDensity, this.grassSettings.instanceDensityCap);
    const densityWidth = Math.sqrt(requestedDensity / instanceDensity);
    const cell = 1 / Math.sqrt(instanceDensity);
    const cells = Math.ceil(size / cell);
    const mesh = new THREE.InstancedMesh(
      this.grassGeometries[0],
      this.grassMaterial,
      cells * cells,
    );
    let completed = false;
    try {
      let count = 0;
      for (let iz = 0; iz < cells; iz++) {
        yield;
        for (let ix = 0; ix < cells; ix++) {
          const x = ox + (ix + rng.range(0.08, 0.92)) * cell;
          const z = oz + (iz + rng.range(0.08, 0.92)) * cell;
          if (x >= ox + size || z >= oz + size) continue;
          if (clearing && (x - clearing.x) ** 2 + (z - clearing.z) ** 2 < clearingBareSq) continue;
          const h = field.height(x, z);
          field.normal(x, z, normal);
          const factor = biomes.getGrassFactor(x, z, h, normal.y);
          if (!rng.chance(Math.pow(factor, this.grassSettings.coverageExponent))) continue;
          const patchField = this.groundPatchNoise.fbm(x * 0.012, z * 0.012, 3) * 0.5 + 0.5;
          const finePatch = this.groundPatchNoise.fbm(x * 0.045 + 17, z * 0.045 - 29, 2) * 0.5 + 0.5;
          pos.set(x, field.meshHeight(x, z) - 0.025, z);
          tilt.setFromUnitVectors(UP, normal).slerp(IDENTITY_QUAT, 0.35);
          yaw.setFromAxisAngle(UP, rng.range(0, Math.PI * 2));
          quat.copy(tilt).multiply(yaw);
          const s = rng.range(0.95, 1.38) * (0.88 + factor * 0.42) * densityWidth;
          const height =
            rng.range(0.58, 1.18) *
            (0.78 + patchField * 0.72) *
            this.grassSettings.heightMultiplier;
          scale.set(
            rng.range(0.95, 1.32) * s * this.grassSettings.widthMultiplier,
            height,
            rng.range(0.95, 1.32) * s * this.grassSettings.widthMultiplier,
          );
          matrix.compose(pos, quat, scale);
          const colorSeed = rng.next();
          color
            .setHex(
              colorSeed < 0.2 ? 0x183f20
                : colorSeed < 0.4 ? 0x56751c
                  : colorSeed < 0.58 ? 0x89712a
                    : colorSeed < 0.78 ? 0x2b6b26
                      : 0x739b36,
            )
            .lerp(
              colorSeed < 0.5 ? coolGrass : warmGrass,
              this.grassSettings.colorVariation * (0.18 + Math.abs(colorSeed - 0.5)),
            )
            .multiplyScalar(
              (0.66 + finePatch * 0.42) *
              (1 + (patchField - 0.5) * this.grassSettings.colorContrast),
            );
          mesh.setMatrixAt(count, matrix);
          mesh.setColorAt(count, color);
          count++;
        }
      }
      if (count > 1) {
        // Shuffle instance storage order so distance thinning can use a
        // simple count prefix as a uniform random subset of the tile.
        yield;
        this.shuffleInstances(mesh, count, combineSeed(this.seed, cx, cz, 9311, tileIndex));
      }
      if (count > 0) {
        mesh.count = count;
        mesh.userData.grassFullCount = count;
        mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
        mesh.instanceMatrix.needsUpdate = true;
        if (mesh.instanceColor) {
          mesh.instanceColor.setUsage(THREE.StaticDrawUsage);
          mesh.instanceColor.needsUpdate = true;
        }
        mesh.computeBoundingSphere();
        mesh.userData.isGrassTile = true;
        mesh.userData.grassCenterX = ox + size * 0.5;
        mesh.userData.grassCenterZ = oz + size * 0.5;
        mesh.userData.grassLod = 0;
        this.grassTiles.add(mesh);
        this.grassLodDirty = true;
        group.add(mesh);
      } else {
        mesh.dispose();
      }

      // Larger ground plants remain colony-based and much rarer than grass.
      const undergrowthAttempts = Math.floor(
        110 * densityScale * this.grassSettings.undergrowthMultiplier / GRASS_TILES_PER_CHUNK,
      );
      for (let i = 0; i < undergrowthAttempts; i++) {
        if ((i & 3) === 0) yield;
        const x = ox + rng.next() * size;
        const z = oz + rng.next() * size;
        if (clearing && (x - clearing.x) ** 2 + (z - clearing.z) ** 2 < clearingFullSq) continue;
        const h = field.height(x, z);
        field.normal(x, z, normal);
        const factor = biomes.getGrassFactor(x, z, h, normal.y);
        if (!rng.chance(factor * 0.72)) continue;
        const patchField = this.groundPatchNoise.fbm(x * 0.012, z * 0.012, 3) * 0.5 + 0.5;
        pos.set(x, field.meshHeight(x, z) - 0.025, z);
        tilt.setFromUnitVectors(UP, normal).slerp(IDENTITY_QUAT, 0.35);
        yaw.setFromAxisAngle(UP, rng.range(0, Math.PI * 2));
        quat.copy(tilt).multiply(yaw);
        if (rng.chance(0.58)) {
            const forest = biomes.getForestMask(x, z);
            const kind = forest > 0.58 ? (rng.chance(0.68) ? 'fern' : 'bushHazel')
              : rng.chance(0.45) ? 'bushPink' : 'bushJuniper';
            const variants = this.undergrowth.get(kind)!;
            const variant = rng.int(0, variants.length - 1);
            scale.setScalar(kind === 'fern' ? rng.range(0.75, 1.3) : rng.range(0.65, 1.15));
            matrix.compose(pos, quat, scale);
            const items = groundItems.get(kind) ?? [];
            items.push({ matrix: matrix.clone(), variant });
            groundItems.set(kind, items);
        } else if (patchField > 0.48) {
            const kind = `flower${rng.int(0, this.flowerTemplates.length - 1)}`;
            scale.setScalar(rng.range(0.8, 1.35));
            matrix.compose(pos, quat, scale);
            const items = groundItems.get(kind) ?? [];
            items.push({ matrix: matrix.clone(), variant: 0 });
            groundItems.set(kind, items);
        }
      }

      for (const [kind, items] of groundItems) {
        if (kind.startsWith('flower')) {
          const geo = this.flowerTemplates[Number(kind.slice(6))];
          const mesh = new THREE.InstancedMesh(geo, this.flowerMaterial, items.length);
          items.forEach((item, i) => mesh.setMatrixAt(i, item.matrix));
          mesh.instanceMatrix.needsUpdate = true;
          group.add(mesh);
          continue;
        }
        const variants = this.undergrowth.get(kind)!;
        for (let v = 0; v < variants.length; v++) {
          const subset = items.filter((item) => item.variant === v);
          if (subset.length === 0) continue;
          const template = variants[v];
          if (template.bark && template.barkMaterial) {
            const bark = new THREE.InstancedMesh(template.bark, template.barkMaterial, subset.length);
            subset.forEach((item, i) => bark.setMatrixAt(i, item.matrix));
            bark.instanceMatrix.needsUpdate = true;
            group.add(bark);
          }
          const leaves = new THREE.InstancedMesh(template.foliage, template.foliageMaterial, subset.length);
          subset.forEach((item, i) => leaves.setMatrixAt(i, item.matrix));
          leaves.instanceMatrix.needsUpdate = true;
          group.add(leaves);
        }
      }

      completed = true;
      return group.children.length > 0 ? group : null;
    } finally {
      if (!completed) {
        // Aborted mid-build (chunk unloaded or LOD changed): release the
        // partial instance buffers and any LOD registration already made.
        this.grassTiles.delete(mesh);
        mesh.dispose();
      }
    }
  }
}
