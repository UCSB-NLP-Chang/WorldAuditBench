import * as THREE from 'three';
import { Noise2D } from './Noise';
import { combineSeed } from '../utils/Random';
import { clamp } from '../utils/MathUtils';

/**
 * All textures in the game are generated in code on small canvases:
 * no downloaded assets. Each generator is seeded so worlds are reproducible.
 */

function makeCanvas(size: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  return [canvas, ctx];
}

function finalize(canvas: HTMLCanvasElement, repeat = true): THREE.CanvasTexture {
  const tex = new THREE.CanvasTexture(canvas);
  if (repeat) {
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
  }
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return tex;
}

/**
 * Neutral mottled detail map multiplied over terrain vertex colors so the
 * ground has fine-grain variation instead of smooth gradients.
 */
export function createGroundDetailTexture(seed: number, size = 256): THREE.CanvasTexture {
  const [canvas, ctx] = makeCanvas(size);
  const noise = new Noise2D(combineSeed(seed, 11));
  const img = ctx.createImageData(size, size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      // Tileable-ish: sample noise on a torus via two frequencies.
      const n1 = noise.fbm(x * 0.045, y * 0.045, 4);
      const n2 = noise.noise(x * 0.18, y * 0.18);
      const v = clamp(205 + n1 * 38 + n2 * 14, 0, 255);
      const i = (y * size + x) * 4;
      img.data[i] = v;
      img.data[i + 1] = v;
      img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return finalize(canvas);
}

/**
 * Bark: vertical plates split by deep wandering fissures, a fine cross-grain of
 * horizontal lenticels, and sparse pale lichen flecks. Drawn as a value/tint
 * map around the species' base color.
 */
export function createBarkTexture(seed: number, base: THREE.Color, size = 256): THREE.CanvasTexture {
  const [canvas, ctx] = makeCanvas(size);
  const noise = new Noise2D(combineSeed(seed, 23));
  const img = ctx.createImageData(size, size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      // Plates: vertically stretched ridged noise — bright raised plate
      // centres, dark crevices between them.
      const wander = noise.noise(x * 0.02, y * 0.008) * 9;
      const plate = 1 - Math.abs(noise.noise((x + wander) * 0.085, y * 0.012));
      const fissure = Math.pow(clamp(plate, 0, 1), 6.5); // sharp dark line at plate joins
      const streak = noise.fbm(x * 0.2, y * 0.028, 3);
      const grain = noise.noise(x * 0.55, y * 0.14);
      // Faint horizontal lenticels crossing the plates (a stretched band).
      const lenticel = noise.noise(x * 0.05, y * 0.34 + 60);
      const cross = clamp(Math.abs(lenticel) - 0.62, 0, 1) * 0.22;

      let shade = clamp(0.78 + streak * 0.28 + grain * 0.12, 0.3, 1.28);
      shade *= 1 - fissure * 0.6;
      shade *= 1 - cross;

      // Lichen: pale green-grey flecks on the weather side.
      const lichen = noise.fbm(x * 0.05 + 41, y * 0.05 - 13, 2);
      const lichenMask = clamp((lichen - 0.42) * 3, 0, 1) * 0.5;

      const i = (y * size + x) * 4;
      const r = base.r * shade;
      const g = base.g * shade;
      const b = base.b * shade;
      img.data[i] = clamp((r + (0.55 - r) * lichenMask) * 255, 0, 255);
      img.data[i + 1] = clamp((g + (0.6 - g) * lichenMask) * 255, 0, 255);
      img.data[i + 2] = clamp((b + (0.5 - b) * lichenMask) * 255, 0, 255);
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return finalize(canvas);
}

/** Grey/brown mottled rock with cracks. */
export function createRockTexture(seed: number, size = 128): THREE.CanvasTexture {
  const [canvas, ctx] = makeCanvas(size);
  const noise = new Noise2D(combineSeed(seed, 53));
  const img = ctx.createImageData(size, size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const body = noise.fbm(x * 0.05, y * 0.05, 4);
      const crack = Math.abs(noise.noise(x * 0.12, y * 0.12));
      const crackDark = crack < 0.06 ? 0.72 : 1.0;
      const shade = clamp((0.62 + body * 0.28) * crackDark, 0.2, 1.1);
      const warm = noise.noise(x * 0.02 + 80, y * 0.02) * 0.08;
      const i = (y * size + x) * 4;
      img.data[i] = clamp((0.55 + warm) * 255 * shade, 0, 255);
      img.data[i + 1] = clamp(0.53 * 255 * shade, 0, 255);
      img.data[i + 2] = clamp((0.5 - warm * 0.5) * 255 * shade, 0, 255);
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return finalize(canvas);
}

/**
 * Scorched-earth decal for a campfire clearing: a charred dark centre easing
 * out to bare dirt, with a soft transparent edge so it blends into grass. The
 * alpha channel does the feathering; grain keeps the rim from looking stamped.
 */
export function createScorchTexture(seed: number, size = 128): THREE.CanvasTexture {
  const [canvas, ctx] = makeCanvas(size);
  const noise = new Noise2D(combineSeed(seed, 71));
  const img = ctx.createImageData(size, size);
  const c = size / 2;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = (x - c) / c;
      const dy = (y - c) / c;
      const d = Math.hypot(dx, dy);
      const grain = noise.fbm(x * 0.08, y * 0.08, 3) * 0.5 + 0.5;
      // ragged feathered edge
      let a = clamp(1 - d * (0.92 + grain * 0.22), 0, 1);
      a = Math.pow(a, 1.5) * (0.7 + grain * 0.4);
      const burn = clamp(1 - d * 1.7, 0, 1); // charred core
      const r = clamp(0.32 - burn * 0.25 + (grain - 0.5) * 0.08, 0, 1);
      const g = clamp(0.24 - burn * 0.19 + (grain - 0.5) * 0.06, 0, 1);
      const b = clamp(0.17 - burn * 0.13 + (grain - 0.5) * 0.04, 0, 1);
      const i = (y * size + x) * 4;
      img.data[i] = r * 255;
      img.data[i + 1] = g * 255;
      img.data[i + 2] = b * 255;
      img.data[i + 3] = clamp(a, 0, 1) * 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return tex;
}

/** Simple radial glow sprite for crystals / embers. */
export function createGlowTexture(size = 64): THREE.CanvasTexture {
  const [canvas, ctx] = makeCanvas(size);
  const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, 'rgba(255,255,255,0.9)');
  grad.addColorStop(0.35, 'rgba(255,255,255,0.32)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
