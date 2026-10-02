import { SeededRandom, combineSeed, hashString } from '../utils/Random';

/**
 * Deterministic random source for the flora kit. `derive(tag)` splits off an
 * independent child stream keyed by a label, so adding draws to one part of the
 * grammar can never shift the numbers another part sees — that keeps every
 * plant reproducible from its seed alone.
 */
export class SeedStream {
  private readonly source: SeededRandom;

  constructor(private readonly seed: number) {
    this.source = new SeededRandom(seed);
  }

  /** uniform [0, 1) */
  unit(): number {
    return this.source.next();
  }

  /** uniform integer in [0, n) */
  index(n: number): number {
    return Math.floor(this.source.next() * n);
  }

  /** uniform real in [lo, hi) */
  span(lo: number, hi: number): number {
    return lo + this.source.next() * (hi - lo);
  }

  /** true with probability p */
  roll(p: number): boolean {
    return this.source.next() < p;
  }

  /** a fresh, label-keyed child stream */
  derive(tag: string): SeedStream {
    return new SeedStream(combineSeed(this.seed, hashString(tag)));
  }
}
