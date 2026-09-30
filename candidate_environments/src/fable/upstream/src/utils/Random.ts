/**
 * Deterministic, seedable PRNG utilities. All world generation flows through
 * these so a given seed always produces the same world.
 */

/** 32-bit string/number hash (FNV-1a style) used to derive sub-seeds. */
export function hashString(str: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** Combine a base seed with extra integers into a new 32-bit seed. */
export function combineSeed(seed: number, ...parts: number[]): number {
  let h = seed >>> 0;
  for (const p of parts) {
    h = Math.imul(h ^ (p | 0), 0x9e3779b1);
    h = (h << 13) | (h >>> 19);
  }
  return h >>> 0;
}

/** Fast deterministic PRNG (mulberry32). */
export class SeededRandom {
  private state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
  }

  /** Re-seed without allocating a new RNG (hot loops over grid cells, etc.). */
  reseed(seed: number): void {
    this.state = seed >>> 0;
  }

  /** Uniform float in [0, 1). */
  next(): number {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let t = this.state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  /** Uniform float in [min, max). */
  range(min: number, max: number): number {
    return min + this.next() * (max - min);
  }

  /** Uniform integer in [min, max] inclusive. */
  int(min: number, max: number): number {
    return min + Math.floor(this.next() * (max - min + 1));
  }

  /** Pick a random element from an array. */
  pick<T>(arr: readonly T[]): T {
    return arr[Math.floor(this.next() * arr.length)];
  }

  /** Returns true with the given probability. */
  chance(p: number): boolean {
    return this.next() < p;
  }
}

/** Generate a fresh random seed (used when no ?seed= URL param is given). */
export function generateRandomSeed(): number {
  return (Math.random() * 0xffffffff) >>> 0;
}

/** Parse a seed from the URL (?seed=12345 or ?seed=anyString). */
export function getSeedFromUrl(): number | null {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get('seed');
  if (raw === null || raw === '') return null;
  const asNumber = Number(raw);
  if (Number.isFinite(asNumber)) return asNumber >>> 0;
  return hashString(raw);
}
