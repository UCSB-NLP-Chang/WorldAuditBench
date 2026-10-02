import * as THREE from 'three';
import type { QualitySettings } from '../config';
import { MaterialLibrary } from '../procedural/Materials';
import { Terrain } from './Terrain';
import { Biomes } from './Biomes';
import { Sky } from './Sky';
import { Environment } from './Environment';
import { Water } from './Water';
import { Vegetation } from './Vegetation';
import { Props } from './Rocks';
import { Interactables, type Interactable } from './Interactables';
import { Structures } from './Structures';
import { Glow } from './Glow';
import { ChunkManager } from './ChunkManager';
import { FarTerrain } from './FarTerrain';
import { SnowTrail } from './SnowTrail';
import { PLAYER } from '../config';
import type { CylinderCollider } from '../core/CameraController';
import { createGrassSettings, GRASS_DEFAULTS, type GrassSettings } from './GrassSettings';

/**
 * Top-level world: owns the scene, the environment director (day/night,
 * weather, wind), the terrain field, the distant-vista mesh, and the chunk
 * streamer that fills the landscape with vegetation, rocks, and water.
 */
export class World {
  readonly scene: THREE.Scene;
  readonly terrain: Terrain;
  readonly sky: Sky;
  readonly environment: Environment;

  private biomes: Biomes;
  private water: Water;
  private vegetation: Vegetation;
  private props: Props;
  private interactables: Interactables;
  private structures: Structures;
  private glow: Glow;
  private chunkManager: ChunkManager;
  private farTerrain: FarTerrain;
  private materials: MaterialLibrary;
  private snowTrail: SnowTrail;
  private grassSettings: GrassSettings;
  private grassRefreshTimer: number | null = null;
  /** one shared light that snaps to the nearest lit campfire and flickers */
  private fireLight: THREE.PointLight;

  constructor(readonly seed: number, quality: QualitySettings, renderer: THREE.WebGLRenderer) {
    this.scene = new THREE.Scene();

    this.snowTrail = new SnowTrail();
    this.materials = new MaterialLibrary(seed, this.snowTrail);
    this.terrain = new Terrain(seed, quality.terrainSegments);
    this.biomes = new Biomes(seed);
    this.sky = new Sky(this.scene);
    this.environment = new Environment(this.scene, this.sky, seed, quality);
    this.water = new Water(this.environment.uniforms);
    this.grassSettings = createGrassSettings();
    this.vegetation = new Vegetation(
      seed,
      renderer,
      this.materials,
      quality,
      this.environment.uniforms,
      this.grassSettings,
    );
    this.props = new Props(seed, this.materials, quality);
    this.interactables = new Interactables(seed, this.materials, this.environment.uniforms);
    this.structures = new Structures(seed, this.materials);

    // Warm point light shared by every campfire; parked dark until one is lit.
    // A big bonfire, so it reaches further than the player torch (~60 / 26).
    this.fireLight = new THREE.PointLight(0xff7a33, 0, 30, 1.7);
    this.fireLight.castShadow = false;
    this.scene.add(this.fireLight);
    this.glow = new Glow(seed, this.environment.uniforms);
    this.farTerrain = new FarTerrain(this.scene, this.terrain, this.biomes);

    this.chunkManager = new ChunkManager(
      this.scene,
      this.terrain,
      this.biomes,
      this.vegetation,
      this.props,
      this.water,
      this.interactables,
      this.structures,
      this.glow,
      this.materials,
      quality,
    );
  }

  /** Find a pleasant spawn: dry, reasonably flat ground near the origin. */
  findSpawn(): { x: number; z: number } {
    const normal = new THREE.Vector3();
    for (let r = 0; r < 900; r += 18) {
      for (let a = 0; a < Math.PI * 2; a += Math.PI / 6) {
        const x = Math.cos(a) * r;
        const z = Math.sin(a) * r;
        const h = this.terrain.getHeightAt(x, z);
        this.terrain.getNormalAt(x, z, normal);
        if (h > 2 && h < 45 && normal.y > 0.88) {
          this.vegetation.setExclusion(x, z, 12);
          return { x, z };
        }
      }
    }
    this.vegetation.setExclusion(0, 0, 12);
    return { x: 0, z: 0 };
  }

  warmup(playerPos: THREE.Vector3): void {
    this.chunkManager.warmup(playerPos);
    this.farTerrain.buildNow(playerPos);
  }

  update(
    dt: number,
    elapsed: number,
    camera: THREE.PerspectiveCamera,
    wadeDepth: number,
    playerMoving: boolean,
    underwater: boolean,
  ): void {
    this.chunkManager.update(camera.position);
    this.sky.update(elapsed, camera.position);
    this.environment.update(dt, elapsed, camera);
    this.glow.update(this.environment.nightFactor);
    this.water.update(dt, camera.position, wadeDepth, playerMoving);
    this.farTerrain.update(camera.position);
    this.updateFireLight(camera.position, elapsed);

    // Snow trail: stamp footsteps while walking on snowy ground.
    const px = camera.position.x;
    const pz = camera.position.z;
    const groundY = this.terrain.getMeshHeightAt(px, pz);
    const onGround = Math.abs(camera.position.y - PLAYER.eyeHeight - groundY) < 0.6;
    let onSnow = false;
    if (onGround && groundY > 0) {
      const normalY = 1; // flat-enough check is part of the snow factor
      onSnow = this.biomes.getSnowFactor(px, pz, groundY, normalY) > 0.35;
    }
    this.snowTrail.update(dt, px, pz, onSnow, playerMoving);

    // Underwater: thick teal fog sells the medium (the water shader's
    // underside handles the surface refraction look).
    if (underwater) {
      const fog = this.scene.fog as THREE.FogExp2;
      fog.color.setHex(0x10333c);
      fog.density = 0.055;
      (this.scene.background as THREE.Color).setHex(0x10333c);
    }
  }

  /**
   * Drive the single shared fire light: find the nearest lit campfire around
   * the player and park the (flickering) light on it; fade out when there is
   * none in range. One light covers every fire, so cost stays flat.
   */
  private updateFireLight(playerPos: THREE.Vector3, elapsed: number): void {
    let nearest: THREE.Vector3 | null = null;
    let nearestSq = 32 * 32; // only bother lighting fires within ~32 m
    for (const item of this.chunkManager.collectInteractablesNear(playerPos)) {
      if (!item.campfire?.lit) continue;
      const fp = item.campfire.firePos;
      const dSq = (fp.x - playerPos.x) ** 2 + (fp.z - playerPos.z) ** 2;
      if (dSq < nearestSq) {
        nearestSq = dSq;
        nearest = fp;
      }
    }
    if (nearest) {
      this.fireLight.position.copy(nearest);
      // layered sines read as an irregular candle-flicker
      const flicker =
        0.78 +
        0.22 * Math.sin(elapsed * 11.0) * Math.sin(elapsed * 6.7 + 1.3) +
        0.06 * Math.sin(elapsed * 23.0);
      this.fireLight.intensity = Math.max(0, 80.0 * flicker);
    } else {
      this.fireLight.intensity = 0;
    }
  }

  /** True once the grass around the player has finished its initial stream-in. */
  isNearContentReady(): boolean {
    return this.chunkManager.grassStreamingIdle();
  }

  getCollidersNear(pos: THREE.Vector3): CylinderCollider[] {
    return this.chunkManager.collectCollidersNear(pos);
  }

  getInteractablesNear(pos: THREE.Vector3): Interactable[] {
    return this.chunkManager.collectInteractablesNear(pos);
  }

  debugLodSummary(pos: THREE.Vector3): string {
    return this.chunkManager.debugLodSummary(pos);
  }

  randomizeAtmosphere(): void {
    this.environment.randomizeConditions();
  }

  getGrassSettings(): Readonly<GrassSettings> {
    return this.grassSettings;
  }

  setGrassSetting<K extends keyof GrassSettings>(key: K, value: GrassSettings[K]): void {
    this.grassSettings[key] = value;
    // LOD-only settings are applied live by updateGrassLod; rebuilding every
    // tile for them would just re-trigger streaming churn.
    if (
      key === 'edgeDensityMultiplier' ||
      key === 'nearLodDistance' ||
      key === 'midLodDistance' ||
      key === 'renderDistance'
    ) {
      this.vegetation.markGrassLodDirty();
      return;
    }
    this.scheduleGrassRefresh();
  }

  resetGrassSettings(): void {
    Object.assign(this.grassSettings, GRASS_DEFAULTS);
    this.scheduleGrassRefresh();
  }

  private scheduleGrassRefresh(): void {
    if (this.grassRefreshTimer !== null) window.clearTimeout(this.grassRefreshTimer);
    this.grassRefreshTimer = window.setTimeout(() => {
      this.grassRefreshTimer = null;
      this.chunkManager.invalidateVegetation();
    }, 120);
  }
}
