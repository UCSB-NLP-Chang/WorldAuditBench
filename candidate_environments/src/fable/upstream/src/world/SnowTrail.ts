import * as THREE from 'three';
import { SNOW_TRAIL } from '../config';

const TEX_SIZE = SNOW_TRAIL.textureSize;
/** Metres covered by the moving trail window around the player. */
const REGION_SIZE = SNOW_TRAIL.regionSize;
/** Stay this far from the window edge before recentring. */
const RECENTER_MARGIN = SNOW_TRAIL.recenterMargin;
/** Trail fades out over roughly this many seconds (snowfall refills it). */
const FADE_SECONDS = SNOW_TRAIL.fadeSeconds;

/**
 * Temporary snow deformation: a small canvas "depression map" window that
 * follows the player. Footsteps stamp into it, snowfall slowly refills it.
 * The terrain material samples the map in its vertex stage (depress the
 * surface) and fragment stage (shade the compacted trough) — see
 * MaterialLibrary's terrain onBeforeCompile.
 */
export class SnowTrail {
  readonly texture: THREE.CanvasTexture;
  /** Shared with the terrain material: window origin xz, 1/size, strength. */
  readonly uniforms: {
    uTrailMap: { value: THREE.Texture };
    uTrailRegion: { value: THREE.Vector4 };
  };

  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private originX = 0;
  private originZ = 0;
  private fadeAccum = 0;
  private lastStamp = new THREE.Vector2(1e9, 1e9);

  constructor() {
    this.canvas = document.createElement('canvas');
    this.canvas.width = TEX_SIZE;
    this.canvas.height = TEX_SIZE;
    // The canvas starts fully transparent; depression lives in the ALPHA
    // channel (stamps add alpha, snowfall erases it via destination-out).
    this.ctx = this.canvas.getContext('2d')!;

    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.generateMipmaps = false;
    this.texture.minFilter = THREE.LinearFilter;
    this.texture.magFilter = THREE.LinearFilter;
    this.texture.wrapS = THREE.ClampToEdgeWrapping;
    this.texture.wrapT = THREE.ClampToEdgeWrapping;

    this.uniforms = {
      uTrailMap: { value: this.texture },
      uTrailRegion: { value: new THREE.Vector4(0, 0, 1 / REGION_SIZE, 1) },
    };
    this.recenter(0, 0);
  }

  private recenter(x: number, z: number): void {
    const newOx = x - REGION_SIZE / 2;
    const newOz = z - REGION_SIZE / 2;
    const dxPx = Math.round(((this.originX - newOx) / REGION_SIZE) * TEX_SIZE);
    const dzPx = Math.round(((this.originZ - newOz) / REGION_SIZE) * TEX_SIZE);
    // Shift existing trail content so it stays world-anchored.
    this.ctx.globalCompositeOperation = 'copy';
    this.ctx.drawImage(this.canvas, dxPx, dzPx);
    this.ctx.globalCompositeOperation = 'source-over';
    this.originX = newOx;
    this.originZ = newOz;
    (this.uniforms.uTrailRegion.value as THREE.Vector4).set(newOx, newOz, 1 / REGION_SIZE, 1);
    this.texture.needsUpdate = true;
  }

  /**
   * @param onSnow true while the player stands on snowy ground
   * @param moving true while the player is walking
   */
  update(dt: number, playerX: number, playerZ: number, onSnow: boolean, moving: boolean): void {
    // Recenter when the player approaches the window edge.
    if (
      playerX < this.originX + RECENTER_MARGIN ||
      playerX > this.originX + REGION_SIZE - RECENTER_MARGIN ||
      playerZ < this.originZ + RECENTER_MARGIN ||
      playerZ > this.originZ + REGION_SIZE - RECENTER_MARGIN
    ) {
      this.recenter(playerX, playerZ);
    }

    let dirty = false;

    // Refill: erase a small alpha amount at a fixed cadence (cheaper and
    // more uniform than per-frame fades at variable dt).
    this.fadeAccum += dt;
    if (this.fadeAccum > 0.35) {
      const amount = Math.min(this.fadeAccum / FADE_SECONDS, 0.2);
      this.fadeAccum = 0;
      this.ctx.globalCompositeOperation = 'destination-out';
      this.ctx.globalAlpha = amount;
      this.ctx.fillStyle = '#fff';
      this.ctx.fillRect(0, 0, TEX_SIZE, TEX_SIZE);
      this.ctx.globalAlpha = 1;
      this.ctx.globalCompositeOperation = 'source-over';
      dirty = true;
    }

    // Stamp footsteps while moving on snow (spaced so trails read as steps).
    if (onSnow && moving) {
      const dx = playerX - this.lastStamp.x;
      const dz = playerZ - this.lastStamp.y;
      if (dx * dx + dz * dz > 0.55 * 0.55) {
        this.lastStamp.set(playerX, playerZ);
        const px = ((playerX - this.originX) / REGION_SIZE) * TEX_SIZE;
        const pz = ((playerZ - this.originZ) / REGION_SIZE) * TEX_SIZE;
        const r = (0.45 / REGION_SIZE) * TEX_SIZE;
        const grad = this.ctx.createRadialGradient(px, pz, 0, px, pz, r * 2.2);
        grad.addColorStop(0, 'rgba(255,255,255,0.85)');
        grad.addColorStop(0.5, 'rgba(255,255,255,0.35)');
        grad.addColorStop(1, 'rgba(255,255,255,0)');
        this.ctx.fillStyle = grad;
        this.ctx.beginPath();
        this.ctx.arc(px, pz, r * 2.2, 0, Math.PI * 2);
        this.ctx.fill();
        dirty = true;
      }
    }

    if (dirty) this.texture.needsUpdate = true;
  }
}
