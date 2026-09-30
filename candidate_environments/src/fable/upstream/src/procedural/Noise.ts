import { SeededRandom } from '../utils/Random';

/**
 * Seeded 2D simplex noise plus fractal helpers (fBm, ridged, domain warp).
 * Deterministic for a given seed; the same (x, y) always returns the same
 * value, which is what makes chunked terrain seamless.
 */

const GRAD2: ReadonlyArray<readonly [number, number]> = [
  [1, 1], [-1, 1], [1, -1], [-1, -1],
  [1, 0], [-1, 0], [0, 1], [0, -1],
];

const F2 = 0.5 * (Math.sqrt(3) - 1);
const G2 = (3 - Math.sqrt(3)) / 6;

export class Noise2D {
  private perm: Uint8Array;

  constructor(seed: number) {
    // Build a seeded permutation table.
    const rng = new SeededRandom(seed);
    const p = new Uint8Array(256);
    for (let i = 0; i < 256; i++) p[i] = i;
    for (let i = 255; i > 0; i--) {
      const j = Math.floor(rng.next() * (i + 1));
      const tmp = p[i];
      p[i] = p[j];
      p[j] = tmp;
    }
    this.perm = new Uint8Array(512);
    for (let i = 0; i < 512; i++) this.perm[i] = p[i & 255];
  }

  /** Raw simplex noise in roughly [-1, 1]. */
  noise(x: number, y: number): number {
    const perm = this.perm;
    const s = (x + y) * F2;
    const i = Math.floor(x + s);
    const j = Math.floor(y + s);
    const t = (i + j) * G2;
    const x0 = x - (i - t);
    const y0 = y - (j - t);

    const i1 = x0 > y0 ? 1 : 0;
    const j1 = x0 > y0 ? 0 : 1;

    const x1 = x0 - i1 + G2;
    const y1 = y0 - j1 + G2;
    const x2 = x0 - 1 + 2 * G2;
    const y2 = y0 - 1 + 2 * G2;

    const ii = i & 255;
    const jj = j & 255;

    let n0 = 0;
    let n1 = 0;
    let n2 = 0;

    let t0 = 0.5 - x0 * x0 - y0 * y0;
    if (t0 > 0) {
      t0 *= t0;
      const g = GRAD2[perm[ii + perm[jj]] & 7];
      n0 = t0 * t0 * (g[0] * x0 + g[1] * y0);
    }

    let t1 = 0.5 - x1 * x1 - y1 * y1;
    if (t1 > 0) {
      t1 *= t1;
      const g = GRAD2[perm[ii + i1 + perm[jj + j1]] & 7];
      n1 = t1 * t1 * (g[0] * x1 + g[1] * y1);
    }

    let t2 = 0.5 - x2 * x2 - y2 * y2;
    if (t2 > 0) {
      t2 *= t2;
      const g = GRAD2[perm[ii + 1 + perm[jj + 1]] & 7];
      n2 = t2 * t2 * (g[0] * x2 + g[1] * y2);
    }

    return 70.14 * (n0 + n1 + n2);
  }

  /** Fractal Brownian motion, roughly [-1, 1]. */
  fbm(x: number, y: number, octaves: number, lacunarity = 2.0, gain = 0.5): number {
    let amp = 1;
    let freq = 1;
    let sum = 0;
    let norm = 0;
    for (let o = 0; o < octaves; o++) {
      sum += amp * this.noise(x * freq, y * freq);
      norm += amp;
      amp *= gain;
      freq *= lacunarity;
    }
    return sum / norm;
  }

  /**
   * Ridged multifractal, roughly [0, 1]. Produces mountain crests.
   *
   * `softness` rounds the ridgeline. Plain ridged noise is `1 - |noise|`,
   * which has a sharp C1 kink at every crest; on a regular mesh that kink
   * samples inconsistently and triangulates into jagged staircase edges with
   * faceted shading. Replacing `|n|` with the smooth-abs `sqrt(n² + softness)`
   * rounds the crease into a continuous curve the mesh can represent cleanly,
   * and `peak` renormalizes so the rounding doesn't lower the overall relief.
   */
  ridged(
    x: number,
    y: number,
    octaves: number,
    lacunarity = 2.0,
    gain = 0.5,
    softness = 0,
  ): number {
    let amp = 0.5;
    let freq = 1;
    let sum = 0;
    let norm = 0;
    const peak = softness > 0 ? 1 - Math.sqrt(softness) : 1;
    for (let o = 0; o < octaves; o++) {
      const v = this.noise(x * freq, y * freq);
      const a = softness > 0 ? Math.sqrt(v * v + softness) : Math.abs(v);
      let n = (1 - a) / peak;
      if (n < 0) n = 0;
      sum += amp * n * n;
      norm += amp;
      amp *= gain;
      freq *= lacunarity;
    }
    return sum / norm;
  }
}
