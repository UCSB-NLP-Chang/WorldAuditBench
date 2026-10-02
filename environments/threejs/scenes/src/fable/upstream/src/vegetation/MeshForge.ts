/**
 * MeshForge — a tiny append-only geometry accumulator.
 *
 * Every flora builder writes into one shared forge, so a finished plant lands
 * in a single indexed buffer (one or two draw calls total). Vertices carry a
 * packed `vdata` vec4 the foliage / bark materials decode:
 *
 *   x: hue jitter (−1..1)   y: sway flex (0 stiff .. 1 whippy)
 *   z: sway phase (0..2π)   w: baked shade (0 dark .. 1 lit)
 */

import { BufferAttribute, BufferGeometry, Vector3 } from 'three';

export class MeshForge {
  private readonly p: number[] = [];
  private readonly n: number[] = [];
  private readonly t: number[] = [];
  private readonly d: number[] = [];
  private readonly tris: number[] = [];
  count = 0;

  emit(
    px: number, py: number, pz: number,
    nx: number, ny: number, nz: number,
    u: number, v: number,
    d0: number, d1: number, d2: number, d3: number,
  ): number {
    this.p.push(px, py, pz);
    this.n.push(nx, ny, nz);
    this.t.push(u, v);
    this.d.push(d0, d1, d2, d3);
    return this.count++;
  }

  face(a: number, b: number, c: number): void {
    this.tris.push(a, b, c);
  }

  face4(a: number, b: number, c: number, d: number): void {
    this.tris.push(a, b, c, a, c, d);
  }

  get faceCount(): number {
    return this.tris.length / 3;
  }

  /**
   * Lerp every recent normal toward a sphere centred on `center`. This is the
   * trick that makes scattered foliage read as one soft canopy mass instead of
   * a thousand independently-lit cards.
   */
  blendToSphere(center: Vector3, radius: number, amount: number, from = 0): void {
    const inv = 1 / Math.max(0.001, radius);
    for (let i = from; i < this.count; i++) {
      const b = i * 3;
      let sx = ((this.p[b] as number) - center.x) * inv;
      let sy = ((this.p[b + 1] as number) - center.y) * inv;
      let sz = ((this.p[b + 2] as number) - center.z) * inv;
      const sl = Math.hypot(sx, sy, sz) || 1;
      sx /= sl; sy /= sl; sz /= sl;
      const nx = (this.n[b] as number) * (1 - amount) + sx * amount;
      const ny = (this.n[b + 1] as number) * (1 - amount) + sy * amount;
      const nz = (this.n[b + 2] as number) * (1 - amount) + sz * amount;
      const l = Math.hypot(nx, ny, nz) || 1;
      this.n[b] = nx / l;
      this.n[b + 1] = ny / l;
      this.n[b + 2] = nz / l;
    }
  }

  /** Darken vdata.w for verts buried deep inside the crown hull (cheap AO). */
  bakeCrownShade(center: Vector3, radius: number, strength: number, from = 0): void {
    const inv = 1 / Math.max(0.001, radius);
    for (let i = from; i < this.count; i++) {
      const b = i * 3;
      const dx = ((this.p[b] as number) - center.x) * inv;
      const dy = ((this.p[b + 1] as number) - center.y) * inv;
      const dz = ((this.p[b + 2] as number) - center.z) * inv;
      const reach = Math.min(1, Math.hypot(dx, dy, dz));
      const shade = 1 - strength * (1 - reach) * (1 - reach);
      const w = i * 4 + 3;
      this.d[w] = (this.d[w] as number) * shade;
    }
  }

  finish(): BufferGeometry {
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(new Float32Array(this.p), 3));
    g.setAttribute('normal', new BufferAttribute(new Float32Array(this.n), 3));
    g.setAttribute('uv', new BufferAttribute(new Float32Array(this.t), 2));
    g.setAttribute('vdata', new BufferAttribute(new Float32Array(this.d), 4));
    g.setIndex(
      this.count > 65535
        ? new BufferAttribute(new Uint32Array(this.tris), 1)
        : new BufferAttribute(new Uint16Array(this.tris), 1),
    );
    g.computeBoundingSphere();
    return g;
  }
}
