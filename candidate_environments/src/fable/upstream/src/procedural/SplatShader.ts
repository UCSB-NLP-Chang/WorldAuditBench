/**
 * Benchmark additions (v2): real PBR surfaces on top of the procedural world.
 *  - terrain: four-way texture splat (grass / forest dirt / cliff rock / snow) blended by a per-vertex
 *    weight attribute (`aSplat`, from Biomes.getSplatWeights) and tinted by the biome vertex colours,
 *    with normal-map detail and the snow-trail deformation kept from the original material;
 *  - rock: world-space triplanar diffuse + normal for boulders, stones and ruins (no UV seams);
 *  - textures are Poly Haven CC0 sets embedded as JPEG data URLs (assets/textures.ts).
 */
import * as THREE from 'three';
import { TEXTURE_SETS } from '../assets/textures';
import type { SnowTrail } from '../world/SnowTrail';

const loader = new THREE.TextureLoader();
const cache = new Map<string, THREE.Texture>();

/** Mean linear luminance of a set's diffuse map (textures are normalised to mean 1 in the shaders). */
export function texMean(id: string): number {
  return TEXTURE_SETS[id]?.meanLum ?? 0.25;
}

/** Uncached instance (own repeat / wrap settings). */
export function loadTexInstance(id: string, kind: 'diff' | 'nor', repeat: [number, number]): THREE.Texture {
  const set = TEXTURE_SETS[id];
  if (!set) throw new Error(`texture set missing: ${id}`);
  const t = loader.load(set[kind]);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 8;
  t.repeat.set(repeat[0], repeat[1]);
  t.colorSpace = THREE.NoColorSpace;
  return t;
}

export function loadTex(id: string, kind: 'diff' | 'nor'): THREE.Texture {
  const key = `${id}:${kind}`;
  let t = cache.get(key);
  if (t) return t;
  const set = TEXTURE_SETS[id];
  if (!set) throw new Error(`texture set missing: ${id}`);
  t = loader.load(set[kind]);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 8;
  // uploaded raw and decoded in the shaders (splatDecode) so the brightness maths is exact
  t.colorSpace = THREE.NoColorSpace;
  cache.set(key, t);
  return t;
}

const TRIPLANAR_GLSL = /* glsl */ `
vec3 splatDecode(vec3 c) { return pow(c, vec3(2.2)); }   // sRGB photo -> linear
vec3 splatWeights3(vec3 n) {
  vec3 bw = abs(n);
  bw = bw * bw * bw * bw;
  return bw / (bw.x + bw.y + bw.z + 1e-4);
}
vec3 splatTriplanar(sampler2D tex, vec3 p, vec3 bw, float scale) {
  return splatDecode(texture2D(tex, p.yz * scale).rgb) * bw.x
       + splatDecode(texture2D(tex, p.xz * scale).rgb) * bw.y
       + splatDecode(texture2D(tex, p.xy * scale).rgb) * bw.z;
}
`;

/** Terrain material: splat textures + biome tint + snow trail. */
export function createTerrainMaterial(snowTrail?: SnowTrail): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.96, metalness: 0 });
  const uniforms = {
    uGrassD: { value: loadTex('leafy_grass', 'diff') },
    uGrassN: { value: loadTex('leafy_grass', 'nor') },
    uDirtD: { value: loadTex('forest_ground_04', 'diff') },
    uDirtN: { value: loadTex('forest_ground_04', 'nor') },
    uRockD: { value: loadTex('rock_face_03', 'diff') },
    uRockN: { value: loadTex('rock_face_03', 'nor') },
    uSnowD: { value: loadTex('snow_02', 'diff') },
    uSnowN: { value: loadTex('snow_02', 'nor') },
    // 1 / mean luminance per set: the textures become mean-1 detail over the biome vertex colours
    uInvMean: { value: new THREE.Vector4(1 / texMean('leafy_grass'), 1 / texMean('forest_ground_04'), 1 / texMean('rock_face_03'), 1 / texMean('snow_02')) },
  };
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    if (snowTrail) {
      shader.uniforms.uTrailMap = snowTrail.uniforms.uTrailMap;
      shader.uniforms.uTrailRegion = snowTrail.uniforms.uTrailRegion;
    }
    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        `#include <common>
attribute vec4 aSplat;
attribute float aSnow;
uniform sampler2D uTrailMap;
uniform vec4 uTrailRegion; // origin x, origin z, 1/size, strength
varying vec4 vSplat;
varying vec3 vWPos;
varying vec3 vWNormal;
varying float vTrail;`,
      )
      .replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
{
  vec4 trailWp = modelMatrix * vec4(transformed, 1.0);
  vec2 trailUv = (trailWp.xz - uTrailRegion.xy) * uTrailRegion.z;
  float inWindow = step(abs(trailUv.x - 0.5), 0.5) * step(abs(trailUv.y - 0.5), 0.5);
  float depression = ${snowTrail ? 'texture2D(uTrailMap, clamp(trailUv, 0.0, 1.0)).a' : '0.0'};
  vTrail = depression * inWindow * aSnow * uTrailRegion.w;
  transformed.y -= vTrail * 0.22;
  vSplat = aSplat;
  vWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;
  vWNormal = normalize(mat3(modelMatrix) * objectNormal);
}`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        `#include <common>
uniform sampler2D uGrassD; uniform sampler2D uGrassN;
uniform sampler2D uDirtD;  uniform sampler2D uDirtN;
uniform sampler2D uRockD;  uniform sampler2D uRockN;
uniform sampler2D uSnowD;  uniform sampler2D uSnowN;
uniform vec4 uInvMean;
varying vec4 vSplat;
varying vec3 vWPos;
varying vec3 vWNormal;
varying float vTrail;
${TRIPLANAR_GLSL}`,
      )
      .replace(
        '#include <map_fragment>',
        `{
  vec4 w = vSplat;
  vec3 bw = splatWeights3(normalize(vWNormal));
  vec2 uvG = vWPos.xz * (1.0 / 2.6);
  vec2 uvD = vWPos.xz * (1.0 / 3.2);
  vec2 uvS = vWPos.xz * (1.0 / 4.5);
  // second, coarser sample breaks up the tiling of the big open meadows
  vec3 g = mix(splatDecode(texture2D(uGrassD, uvG).rgb), splatDecode(texture2D(uGrassD, uvG * 0.23 + 0.37).rgb), 0.35);
  vec3 d = splatDecode(texture2D(uDirtD, uvD).rgb);
  vec3 r = splatTriplanar(uRockD, vWPos, bw, 1.0 / 4.0);
  vec3 s = splatDecode(texture2D(uSnowD, uvS).rgb);
  // mean-1 texture detail modulating the biome vertex colour (which carries the scene's brightness design);
  // the grass photo's own hue is partly desaturated so the lush/dry biome colours stay in charge
  const vec3 lumW = vec3(0.2126, 0.7152, 0.0722);
  g *= uInvMean.x; g = mix(vec3(dot(g, lumW)), g, 0.45);
  d *= uInvMean.y; d = mix(vec3(dot(d, lumW)), d, 0.7);
  r *= uInvMean.z;
  s *= uInvMean.w;
  vec3 tex = clamp(g * w.x + d * w.y + r * w.z + s * w.w, 0.0, 3.0);
  // 0.62 restores the darkening the original grey detail map applied (mean ~0.6 linear)
  diffuseColor.rgb *= vColor.rgb * mix(vec3(1.0), tex, 0.85) * 0.62;
  diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * vec3(0.62, 0.68, 0.84), vTrail);
}`,
      )
      .replace('#include <color_fragment>', '')
      .replace(
        '#include <normal_fragment_maps>',
        `{
  vec4 w = vSplat;
  vec2 uvG = vWPos.xz * (1.0 / 2.6);
  vec2 uvD = vWPos.xz * (1.0 / 3.2);
  vec2 uvS = vWPos.xz * (1.0 / 4.5);
  vec3 nG = texture2D(uGrassN, uvG).xyz * 2.0 - 1.0;
  vec3 nD = texture2D(uDirtN, uvD).xyz * 2.0 - 1.0;
  vec3 nR = texture2D(uRockN, vWPos.xz * 0.25).xyz * 2.0 - 1.0;
  vec3 nS = texture2D(uSnowN, uvS).xyz * 2.0 - 1.0;
  vec3 nt = nG * w.x + nD * w.y + nR * w.z + nS * w.w;
  vec3 gN = normalize(vWNormal);
  vec3 nW = normalize(vec3(gN.x + nt.x * 0.9, gN.y, gN.z + nt.y * 0.9));
  normal = normalize((viewMatrix * vec4(nW, 0.0)).xyz);
}`,
      );
  };
  material.customProgramCacheKey = () => 'terrainSplatV2';
  return material;
}

/** Triplanar PBR material for rocks / ruins: world-space projection, no UVs needed. */
export function createTriplanarMaterial(
  texId: string,
  metresPerTile: number,
  params: THREE.MeshStandardMaterialParameters = {},
): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ roughness: 0.94, metalness: 0, ...params });
  const scale = 1 / metresPerTile;
  // normalised to the albedo level the scene's lighting was designed for (~0.09 linear for rock; measured)
  const uniforms = { uTriD: { value: loadTex(texId, 'diff') }, uTriN: { value: loadTex(texId, 'nor') }, uTriGain: { value: 0.09 / texMean(texId) } };
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>\nvarying vec3 vWPos;\nvarying vec3 vWNormal;`)
      .replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
{
  #ifdef USE_INSTANCING
    mat4 triModel = modelMatrix * instanceMatrix;
  #else
    mat4 triModel = modelMatrix;
  #endif
  vWPos = (triModel * vec4(transformed, 1.0)).xyz;
  vWNormal = normalize(mat3(triModel) * objectNormal);
}`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        `#include <common>
uniform sampler2D uTriD; uniform sampler2D uTriN; uniform float uTriGain;
varying vec3 vWPos; varying vec3 vWNormal;
${TRIPLANAR_GLSL}`,
      )
      .replace(
        '#include <map_fragment>',
        `{
  vec3 bw = splatWeights3(normalize(vWNormal));
  diffuseColor.rgb *= splatTriplanar(uTriD, vWPos, bw, ${scale.toFixed(5)}) * uTriGain;
}`,
      )
      .replace(
        '#include <normal_fragment_maps>',
        `{
  vec3 gN = normalize(vWNormal);
  vec3 bw = splatWeights3(gN);
  vec3 nx = texture2D(uTriN, vWPos.yz * ${scale.toFixed(5)}).xyz * 2.0 - 1.0;
  vec3 ny = texture2D(uTriN, vWPos.xz * ${scale.toFixed(5)}).xyz * 2.0 - 1.0;
  vec3 nz = texture2D(uTriN, vWPos.xy * ${scale.toFixed(5)}).xyz * 2.0 - 1.0;
  // whiteout blend per projection axis
  vec3 pert = vec3(0.0, nx.x, nx.y) * bw.x + vec3(ny.x, 0.0, ny.y) * bw.y + vec3(nz.x, nz.y, 0.0) * bw.z;
  vec3 nW = normalize(gN + pert * 0.85);
  normal = normalize((viewMatrix * vec4(nW, 0.0)).xyz);
}`,
      );
  };
  material.customProgramCacheKey = () => `triplanar:${texId}:${metresPerTile}`;
  return material;
}

/** MeshStandardMaterial `map` sampled raw (NoColorSpace) and decoded in the shader (same convention as the splats). */
export function applyManualSRGBMap(material: THREE.MeshStandardMaterial, cacheKey: string): THREE.MeshStandardMaterial {
  const prev = material.onBeforeCompile;
  material.onBeforeCompile = (shader, renderer) => {
    prev?.(shader, renderer);
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <map_fragment>',
      `#ifdef USE_MAP
  vec4 sampledDiffuseColor = texture2D(map, vMapUv);
  sampledDiffuseColor.rgb = pow(sampledDiffuseColor.rgb, vec3(2.2));
  diffuseColor *= sampledDiffuseColor;
#endif`,
    );
  };
  material.customProgramCacheKey = () => cacheKey;
  return material;
}
