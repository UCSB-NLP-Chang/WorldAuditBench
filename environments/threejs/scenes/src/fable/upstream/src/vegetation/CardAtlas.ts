/**
 * CardAtlas — turns thousands of tiny leaves into a handful of triangles.
 *
 * A lush twig (dozens of real leaf/needle meshes from Foliage.ts) is rendered
 * ONCE per species into a 2×2 variant atlas via an offscreen render target.
 * The tree then drops big alpha-tested "cards" at its foliage anchors — one
 * card is a whole spray at 2–4 tris, and that is where canopy fullness comes
 * from with almost no triangle cost.
 *
 * Atlas albedo is stored sqrt-encoded (plain 8-bit linear crushes dark greens),
 * its transparent margin is flood-filled on the CPU so mip chains never bleed
 * dark halos, and the card material squares it back on sample.
 */

import {
  DataTexture,
  DoubleSide,
  LinearFilter,
  LinearMipmapLinearFilter,
  Matrix4,
  Mesh,
  NoColorSpace,
  OrthographicCamera,
  Quaternion,
  Scene,
  ShaderMaterial,
  Vector3,
  WebGLRenderTarget,
  type WebGLRenderer,
} from 'three';
import type { SeedStream } from './SeedStream';
import { appendLeaf, appendNeedleFan } from './Foliage';
import { MeshForge } from './MeshForge';
import type { Tuft, TreeProfile } from './Botany';

export const ATLAS_SIZE = 1024;

const XF = new Matrix4();
const QA = new Quaternion();
const QB = new Quaternion();
const AXIS_X = new Vector3(1, 0, 0);
const AXIS_Z = new Vector3(0, 0, 1);

/** Compose the leafy content for one atlas tile centred at (cx, cy). */
function paintTwig(
  forge: MeshForge,
  profile: TreeProfile,
  rng: SeedStream,
  cx: number,
  cy: number,
): void {
  const canopy = profile.canopy;
  if (!canopy) return;
  const half = 0.46;
  if (canopy.style === 'needleFan') {
    const bottlebrush = canopy.blade.radial > 0.5;
    const fern = canopy.bakeStyle === 'fern';
    const toTile = (2 * half) / (canopy.sizeRange[1] * 1.15);
    const blade = {
      ...canopy.blade,
      len: canopy.blade.len * toTile * (fern ? 1.45 : 1),
      width: canopy.blade.width * toTile * 1.15,
      needles: Math.round(canopy.blade.needles * (fern ? 1.5 : bottlebrush ? 1.4 : 1.2)),
    };
    const fanLen = canopy.sizeRange[1] * toTile * (fern ? 1.3 : 1);
    const sprigs = fern ? 0 : bottlebrush ? 6 : 9;
    for (let i = -1; i < sprigs; i++) {
      const t = i < 0 ? 0 : (i + 0.6) / sprigs;
      const along = -half + t * fanLen * 0.8;
      const side = i < 0 ? 0 : i % 2 === 0 ? 1 : -1;
      const ang = i < 0 ? 0 : side * (0.75 + rng.unit() * 0.65) * (bottlebrush ? 1.1 : 1);
      QA.setFromAxisAngle(AXIS_Z, ang);
      QB.setFromAxisAngle(AXIS_X, -Math.PI / 2);
      QA.multiply(QB);
      const s = i < 0 ? 1 : (0.5 + rng.unit() * 0.32) * (1.1 - t * 0.35);
      XF.compose(
        new Vector3(cx + (i < 0 ? 0 : Math.sin(ang) * 0.06), cy + along, 0),
        QA,
        new Vector3(s, s, s),
      );
      appendNeedleFan(
        forge, XF, blade, fanLen * (i < 0 ? 1 : s * 0.8), rng,
        rng.unit() * 2 - 1, 0.5, rng.unit() * 6.28,
        0.72 + rng.unit() * 0.28,
      );
    }
  } else {
    const leaves = 14 + rng.index(7);
    const toTile = (2 * half) / (canopy.blade.len * 2.1);
    for (let i = 0; i < leaves; i++) {
      const t = i / (leaves - 1);
      const spread = 0.5 + t * 0.6;
      const ang = (rng.unit() - 0.5) * 3.0 * spread;
      const r = (0.15 + t * 0.85) * half * (0.75 + rng.unit() * 0.45);
      const px = cx + Math.sin(ang) * r;
      const py = cy - half * 0.82 + (t * 1.45 + rng.unit() * 0.3) * half;
      QA.setFromAxisAngle(AXIS_Z, ang * 0.8 + (rng.unit() - 0.5) * 0.5);
      QB.setFromAxisAngle(AXIS_X, -Math.PI / 2 + 0.45 + (rng.unit() - 0.3) * 0.7);
      QA.multiply(QB);
      const s = toTile * (0.75 + rng.unit() * 0.5);
      XF.compose(new Vector3(px, py, (rng.unit() - 0.5) * 0.05), QA, new Vector3(s, s, s));
      appendLeaf(
        forge, XF, canopy.blade,
        rng.unit() * 2 - 1, 0.5, rng.unit() * 6.28,
        0.65 + rng.unit() * 0.35,
      );
    }
  }
}

/** Unlit, sqrt-encoded albedo shader used only while baking the atlas. */
function bakeShader(profile: TreeProfile): ShaderMaterial {
  const c = profile.leafColor;
  const bl = profile.bloom;
  return new ShaderMaterial({
    vertexShader: /* glsl */ `
      attribute vec4 vdata;
      varying vec2 vUv;
      varying vec4 vData;
      void main() {
        vUv = uv;
        vData = vdata;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec2 vUv;
      varying vec4 vData;
      void main() {
        vec3 base = vec3(${c.r}, ${c.g}, ${c.b});
        float k = vData.x * float(${c.hueVar});
        // per-leaf hue: warm toward +k, cool toward -k
        vec3 toned = base
          * mix(vec3(1.0), vec3(1.25, 1.05, 0.5), clamp(k, 0.0, 1.0))
          * mix(vec3(1.0), vec3(0.72, 0.95, 1.2), clamp(-k, 0.0, 1.0));
        float midrib = smoothstep(0.0, 0.05, abs(vUv.x - 0.5));
        float edge = smoothstep(0.5, 0.34, abs(vUv.x - 0.5)); // subtle rim darkening
        float tipLight = mix(0.9, 1.2, vUv.y);
        vec3 albedo = toned * vData.w * (midrib * 0.2 + 0.8) * (0.86 + 0.14 * edge) * tipLight;
        ${
          bl
            ? `// leaves whose hue jitter clears the threshold flip to bloom
        float isBloom = step(${(1 - bl.frac * 2).toFixed(4)}, vData.x);
        vec3 bloom = vec3(${bl.r}, ${bl.g}, ${bl.b}) * mix(0.78, 1.16, vUv.y) * (vData.w * 0.4 + 0.6);
        albedo = mix(albedo, bloom, isBloom);`
            : ''
        }
        gl_FragColor = vec4(sqrt(clamp(albedo, 0.0, 1.0)), 1.0);
      }
    `,
    side: DoubleSide,
  });
}

/**
 * Flood cluster colour outward into the transparent margin using a ping-pong
 * pair of buffers (one allocation total instead of one per pass), so the mip
 * chain never samples black where a leaf edge meets empty space.
 */
function bleedEdges(px: Uint8Array, res: number, passes: number): void {
  const at = (x: number, y: number): number => (y * res + x) * 4;
  let read: Uint8Array = px;
  let write: Uint8Array = new Uint8Array(px.length);
  for (let p = 0; p < passes; p++) {
    write.set(read);
    for (let y = 0; y < res; y++) {
      for (let x = 0; x < res; x++) {
        const i = at(x, y);
        if ((read[i + 3] as number) > 8) continue;
        let r = 0, g = 0, b = 0, n = 0;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            if (dx === 0 && dy === 0) continue;
            const xx = x + dx, yy = y + dy;
            if (xx < 0 || yy < 0 || xx >= res || yy >= res) continue;
            const j = at(xx, yy);
            if ((read[j + 3] as number) > 8) {
              r += read[j] as number; g += read[j + 1] as number; b += read[j + 2] as number;
              n++;
            }
          }
        }
        if (n > 0) {
          write[i] = Math.round(r / n);
          write[i + 1] = Math.round(g / n);
          write[i + 2] = Math.round(b / n);
          write[i + 3] = 9; // mark filled so the next pass can spread further
        }
      }
    }
    const t = read; read = write; write = t;
  }
  // land the final state back in the caller's buffer if it ended in the scratch
  if (read !== px) px.set(read);
  // bleed markers must never pass the alpha test
  for (let i = 3; i < px.length; i += 4) {
    if ((px[i] as number) <= 9) px[i] = 0;
  }
}

/**
 * Bake a species' 2×2 twig atlas and return a mipmapped texture. Costs tens of
 * ms once per species; fully deterministic for a given seed stream.
 */
export function bakeFoliageAtlas(
  renderer: WebGLRenderer,
  profile: TreeProfile,
  rng: SeedStream,
): DataTexture {
  const scene = new Scene();
  const forge = new MeshForge();
  for (let v = 0; v < 4; v++) {
    paintTwig(forge, profile, rng.derive(`tile${v}`), (v % 2) - 0.5, Math.floor(v / 2) - 0.5);
  }
  const material = bakeShader(profile);
  const mesh = new Mesh(forge.finish(), material);
  mesh.frustumCulled = false;
  scene.add(mesh);

  const cam = new OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
  cam.position.set(0, 0, 5);
  cam.lookAt(0, 0, 0);

  const rt = new WebGLRenderTarget(ATLAS_SIZE, ATLAS_SIZE, { depthBuffer: true });
  rt.texture.colorSpace = NoColorSpace;

  const prevTarget = renderer.getRenderTarget();
  const prevAlpha = renderer.getClearAlpha();
  const prevAutoReset = renderer.info.autoReset;
  renderer.info.autoReset = false;
  renderer.setClearColor(0x000000, 0);
  renderer.setRenderTarget(rt);
  renderer.clear();
  renderer.render(scene, cam);

  const px = new Uint8Array(ATLAS_SIZE * ATLAS_SIZE * 4);
  renderer.readRenderTargetPixels(rt, 0, 0, ATLAS_SIZE, ATLAS_SIZE, px);
  renderer.setRenderTarget(prevTarget);
  renderer.setClearAlpha(prevAlpha);
  renderer.info.autoReset = prevAutoReset;
  rt.dispose();
  material.dispose();
  mesh.geometry.dispose();

  bleedEdges(px, ATLAS_SIZE, 6);

  const tex = new DataTexture(px, ATLAS_SIZE, ATLAS_SIZE);
  tex.colorSpace = NoColorSpace;
  tex.generateMipmaps = true;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.magFilter = LinearFilter;
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return tex;
}

/**
 * Drop a card at every anchor: the length axis follows the anchor's +z (atlas
 * v); 'flat' lays one plate in the bough plane, 'cross' adds a perpendicular
 * plate for a volumetric read. An optional bend arches the card along its spine.
 */
export function scatterCards(
  forge: MeshForge,
  anchors: readonly Tuft[],
  opts: { mode: 'flat' | 'cross'; scale: number; bend?: number },
  rng: SeedStream,
): void {
  const width = new Vector3();
  const up = new Vector3();
  const out = new Vector3();
  const at = new Vector3();
  const spine = new Vector3();
  const dirRow = new Vector3();
  const nrmRow = new Vector3();
  const bend = opts.bend ?? 0;
  const rows = bend !== 0 ? 3 : 1;
  for (const a of anchors) {
    const tile = rng.index(4);
    const u0 = (tile % 2) * 0.5;
    const v0 = Math.floor(tile / 2) * 0.5;
    const s = a.scale * opts.scale;
    const roll = (rng.unit() - 0.5) * 0.7;
    QA.copy(a.orient);
    QB.setFromAxisAngle(AXIS_Z, roll);
    QA.multiply(QB);
    width.set(1, 0, 0).applyQuaternion(QA);
    up.set(0, 1, 0).applyQuaternion(QA);
    out.set(0, 0, 1).applyQuaternion(QA);
    const flex = 0.45 + rng.unit() * 0.35;
    const phase = rng.unit() * Math.PI * 2;
    const planes = opts.mode === 'cross' ? 2 : 1;
    const arch = bend * (0.75 + rng.unit() * 0.5);
    for (let pl = 0; pl < planes; pl++) {
      const w = pl === 0 ? width : up;
      const nrm = pl === 0 ? up : width;
      const base = forge.count;
      spine.copy(a.position).addScaledVector(out, -0.08 * s);
      for (let iv = 0; iv <= rows; iv++) {
        const t = iv / rows;
        const ang = arch * t;
        dirRow.copy(out).multiplyScalar(Math.cos(ang)).addScaledVector(nrm, -Math.sin(ang));
        nrmRow.copy(nrm).multiplyScalar(Math.cos(ang)).addScaledVector(out, Math.sin(ang));
        for (let iu = 0; iu <= 1; iu++) {
          at.copy(spine).addScaledVector(w, (iu - 0.5) * s);
          forge.emit(
            at.x, at.y, at.z,
            nrmRow.x, nrmRow.y, nrmRow.z,
            u0 + iu * 0.5, v0 + t * 0.5,
            a.tintJitter, flex, phase, 1 - a.dryness * 0.25,
          );
        }
        if (iv < rows) spine.addScaledVector(dirRow, s / rows);
      }
      for (let iv = 0; iv < rows; iv++) {
        const r0 = base + iv * 2;
        forge.face4(r0, r0 + 1, r0 + 3, r0 + 2);
      }
    }
  }
}
