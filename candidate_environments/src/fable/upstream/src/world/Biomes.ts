import * as THREE from 'three';
import { Noise2D } from '../procedural/Noise';
import { combineSeed } from '../utils/Random';
import { WORLD } from '../config';
import { clamp, smoothstep } from '../utils/MathUtils';

/**
 * Biome sampling: moisture field + rules deciding ground color, grass
 * density and tree species mix from (height, slope, moisture).
 */
export class Biomes {
  private moistureNoise: Noise2D;
  private colorJitterNoise: Noise2D;
  private forestNoise: Noise2D;
  private snowDriftNoise: Noise2D;

  // Palette (kept earthy / desaturated; linear-space colors for vertex data).
  private grassLush = new THREE.Color(0x6d9444).convertSRGBToLinear();
  private grassDry = new THREE.Color(0x9c9456).convertSRGBToLinear();
  private dirt = new THREE.Color(0x8a6b46).convertSRGBToLinear();
  private rock = new THREE.Color(0x8d8880).convertSRGBToLinear();
  private rockDark = new THREE.Color(0x6a6660).convertSRGBToLinear();
  private wet = new THREE.Color(0x564f3a).convertSRGBToLinear();
  private sand = new THREE.Color(0xa89876).convertSRGBToLinear();
  private snow = new THREE.Color(0xe6eaec).convertSRGBToLinear();
  private snowBlue = new THREE.Color(0xaebdca).convertSRGBToLinear();
  private snowSun = new THREE.Color(0xf6f3e8).convertSRGBToLinear();

  private tmp = new THREE.Color();

  constructor(seed: number) {
    this.moistureNoise = new Noise2D(combineSeed(seed, 201));
    this.colorJitterNoise = new Noise2D(combineSeed(seed, 202));
    this.forestNoise = new Noise2D(combineSeed(seed, 203));
    this.snowDriftNoise = new Noise2D(combineSeed(seed, 204));
  }

  /** Moisture in [0, 1]: drives lush-vs-dry grass and forest density. */
  getMoisture(x: number, z: number): number {
    return clamp(this.moistureNoise.fbm(x * 0.0012, z * 0.0012, 3) * 0.5 + 0.5, 0, 1);
  }

  /** Forest mask in [0, 1]: clusters trees into woods and clearings. */
  getForestMask(x: number, z: number): number {
    return clamp(this.forestNoise.fbm(x * 0.0026, z * 0.0026, 3) * 0.5 + 0.5, 0, 1);
  }

  /**
   * Ground color from height / slope / moisture. Written into terrain
   * vertex colors, multiplied by a detail texture in the material.
   */
  getGroundColor(x: number, z: number, h: number, normalY: number, out: THREE.Color): THREE.Color {
    const moisture = this.getMoisture(x, z);
    const waterLevel = WORLD.waterLevel;

    // Base grass tone from moisture.
    out.copy(this.grassDry).lerp(this.grassLush, moisture);

    // Dirt patches in dry exposed spots.
    const dirtMask = smoothstep(0.45, 0.2, moisture) * smoothstep(0.95, 0.78, normalY);
    out.lerp(this.dirt, dirtMask * 0.7);

    // Rock on steep slopes; darker rock on very steep. The same mid-frequency
    // wobble used by the snow line breaks the rock/grass and rock/snow edges
    // into organic tongues so they don't read as clean jagged iso-contours,
    // and a wider band spreads the transition across several triangles.
    const slopeWobble = this.snowDriftNoise.fbm(x * 0.05 + 5, z * 0.05 - 9, 2) * 0.1;
    const rockMask = smoothstep(
      WORLD.rockSlope + 0.3 + slopeWobble,
      WORLD.rockSlope - 0.02 + slopeWobble,
      normalY,
    );
    this.tmp.copy(this.rock).lerp(this.rockDark, smoothstep(0.5, 0.3, normalY));
    out.lerp(this.tmp, rockMask);

    // Shoreline: sandy band just above water, dark wet ground at the edge.
    const shore = smoothstep(waterLevel + WORLD.shoreBand, waterLevel + 0.25, h);
    out.lerp(this.sand, shore * (1 - rockMask) * 0.75);
    const wetMask = smoothstep(waterLevel + 0.45, waterLevel - 0.5, h);
    out.lerp(this.wet, wetMask * 0.85);

    // Snow accumulates in broad drifts on gentler faces while steep ridges
    // remain exposed. Blue troughs and warm wind-scoured caps give distant
    // mountains readable snow relief without extra geometry or draw calls.
    const snowMask = this.getSnowFactor(x, z, h, normalY);
    if (snowMask > 0.001) {
      const windScour = this.snowDriftNoise.fbm(x * 0.0025 + 31, z * 0.009 - 17, 2) * 0.5 + 0.5;
      this.tmp
        .copy(this.snowBlue)
        .lerp(this.snow, smoothstep(0.56, 0.92, normalY))
        .lerp(this.snowSun, smoothstep(0.62, 0.95, windScour) * 0.42);
      out.lerp(this.tmp, snowMask);
    }

    // Large-scale hue jitter so plains aren't one flat green.
    const jitter = this.colorJitterNoise.fbm(x * 0.015, z * 0.015, 2) * 0.07;
    out.r = clamp(out.r * (1 + jitter), 0, 1);
    out.g = clamp(out.g * (1 + jitter * 0.6), 0, 1);
    out.b = clamp(out.b * (1 - jitter * 0.4), 0, 1);

    return out;
  }

  /**
   * Texture blend weights for the terrain splat shader: [grass, dirt, rock, snow], normalised.
   * Same masks as getGroundColor so textures and vertex tint agree.
   */
  getSplatWeights(x: number, z: number, h: number, normalY: number, out: Float32Array, offset: number): void {
    const moisture = this.getMoisture(x, z);
    const waterLevel = WORLD.waterLevel;
    const dirtMask = smoothstep(0.45, 0.2, moisture) * smoothstep(0.95, 0.78, normalY);
    const slopeWobble = this.snowDriftNoise.fbm(x * 0.05 + 5, z * 0.05 - 9, 2) * 0.1;
    const rockMask = smoothstep(WORLD.rockSlope + 0.3 + slopeWobble, WORLD.rockSlope - 0.02 + slopeWobble, normalY);
    const shore = smoothstep(waterLevel + WORLD.shoreBand, waterLevel + 0.25, h);
    const wetMask = smoothstep(waterLevel + 0.45, waterLevel - 0.5, h);
    const snowMask = this.getSnowFactor(x, z, h, normalY);
    let rock = rockMask;
    let dirt = Math.max(dirtMask * 0.85, shore, wetMask) * (1 - rock);
    let grass = Math.max(0, 1 - rock - dirt);
    const snow = snowMask;
    grass *= 1 - snow;
    dirt *= 1 - snow;
    rock *= 1 - snow * 0.85;
    const sum = grass + dirt + rock + snow || 1;
    out[offset] = grass / sum;
    out[offset + 1] = dirt / sum;
    out[offset + 2] = rock / sum;
    out[offset + 3] = snow / sum;
  }

  /**
   * Snow coverage in [0, 1]: altitude band modulated by wind drifts and
   * slope. Shared by terrain vertex colors, the aSnow vertex attribute
   * (snow trail deformation), and prop placement rules.
   */
  getSnowFactor(x: number, z: number, h: number, normalY: number): number {
    if (h < WORLD.snowHeight - 16) return 0;
    const drift = this.snowDriftNoise.fbm(x * 0.008, z * 0.008, 3) * 0.5 + 0.5;
    const localSnowLine = WORLD.snowHeight + (0.5 - drift) * 13;
    // Mid-frequency wobble on the slope cutoff so snow interfingers with bare
    // rock in organic tongues instead of along a clean slope iso-contour,
    // which the triangle mesh renders as a jagged staircase edge. Wider bands
    // (altitude + slope) also spread the transition over several triangles so
    // the vertex-colour gradient interpolates smoothly rather than snapping.
    const wobble = this.snowDriftNoise.fbm(x * 0.05 + 5, z * 0.05 - 9, 2) * 0.13;
    const altitude = smoothstep(localSnowLine, localSnowLine + 14, h);
    const slope = smoothstep(0.44 + wobble, 0.82 + wobble, normalY);
    return altitude * slope;
  }

  /** 0..1 grass coverage at a point (0 on rock, underwater, snow). */
  getGrassFactor(x: number, z: number, h: number, normalY: number): number {
    if (h < WORLD.waterLevel + 0.35) return 0;
    let f = smoothstep(WORLD.rockSlope, WORLD.rockSlope + 0.25, normalY);
    f *= smoothstep(WORLD.snowHeight + 4, WORLD.snowHeight - 6, h);
    const moisture = this.getMoisture(x, z);
    f *= 0.35 + 0.65 * moisture;
    return clamp(f, 0, 1);
  }

  /** Trees per square metre at a point (before quality scaling). */
  getTreeDensity(x: number, z: number, h: number, normalY: number): number {
    if (h < WORLD.waterLevel + 0.9) return 0; // none underwater / at water edge
    if (normalY < 0.62) return 0; // none on steep slopes
    if (h > WORLD.treeLine) return 0; // none above treeline

    const forest = this.getForestMask(x, z);
    const moisture = this.getMoisture(x, z);
    // Concentrate the same broad tree budget into forest interiors. The core
    // reads as a real woodland while sparse transition bands keep it fast.
    const core = smoothstep(0.53, 0.77, forest) * (0.55 + 0.6 * moisture);
    const woodland = smoothstep(0.38, 0.7, forest);
    const scatter = smoothstep(0.2, 0.48, forest);
    // Trees thin out approaching the treeline.
    const alt = smoothstep(WORLD.treeLine, WORLD.treeLine - 25, h);
    return (core * 0.024 + woodland * 0.0025 + scatter * 0.00035) * alt;
  }

}
