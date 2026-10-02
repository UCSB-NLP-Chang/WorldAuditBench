/**
 * Leaf-card foliage shader (instanced). Each canopy is a cloud of small
 * alpha-tested quads ("cards"). Normals point outward from the canopy
 * centre, which gives soft, rounded foliage shading instead of flat facets.
 * Wind: whole-tree bend from the trunk base (shared with bark) + subtle
 * tangential card flutter.
 */

import { TREE_WIND_APPLY, TREE_WIND_FN, TREE_WIND_UNIFORMS } from './treeWind';

export const LEAVES_VERTEX = /* glsl */ `
#include <common>
#include <fog_pars_vertex>

${TREE_WIND_UNIFORMS}

varying vec2 vUv;
varying vec3 vColor;
varying vec3 vNormalW;
varying vec3 vWorldPos;

${TREE_WIND_FN}

void main() {
  vUv = uv;

  #ifdef USE_COLOR
    vColor = color;
  #else
    vColor = vec3(1.0);
  #endif
  #ifdef USE_INSTANCING_COLOR
    vColor *= instanceColor;
  #endif

  vec3 transformed = position;
  ${TREE_WIND_APPLY}

  // Subtle tangential flutter — kept small so cards stay on the canopy shell.
  float flutterPhase = dot(position, vec3(12.9, 78.2, 37.7));
  float flutter = sin(uTime * 2.8 + flutterPhase) * min(uWindStrength, 1.0) * 0.006;
  vec3 flutterDir = cross(normal, vec3(0.0, 1.0, 0.0));
  if (dot(flutterDir, flutterDir) < 1e-4) {
    flutterDir = cross(normal, vec3(1.0, 0.0, 0.0));
  }
  flutterDir = normalize(flutterDir);
  transformed += flutterDir * flutter;

  #ifdef USE_INSTANCING
    vec4 wp = modelMatrix * instanceMatrix * vec4(transformed, 1.0);
    vNormalW = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * normal);
  #else
    vec4 wp = modelMatrix * vec4(transformed, 1.0);
    vNormalW = normalize(mat3(modelMatrix) * normal);
  #endif

  vWorldPos = wp.xyz;
  vec4 mvPosition = viewMatrix * wp;
  gl_Position = projectionMatrix * mvPosition;

  #include <fog_vertex>
}
`;

export const LEAVES_FRAGMENT = /* glsl */ `
#include <common>
#include <fog_pars_fragment>

uniform sampler2D uMap;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uAmbientColor;
uniform vec3 uGroundBounceColor;
uniform float uNight;

varying vec2 vUv;
varying vec3 vColor;
varying vec3 vNormalW;
varying vec3 vWorldPos;

void main() {
  vec4 tex = texture2D(uMap, vUv);
  if (tex.a < 0.5) discard;

  vec3 N = normalize(vNormalW);
  // Half-Lambert wrap lighting: foliage scatters light, so shadow sides
  // stay luminous instead of going black.
  float ndl = dot(N, uSunDir) * 0.5 + 0.5;
  float keyAmount = clamp(uSunDir.y + 0.15, 0.0, 1.0);
  float underside = clamp(-N.y, 0.0, 1.0);
  float horizonFacing = 1.0 - abs(N.y);

  // Translucency: sun shining through the canopy toward the viewer.
  vec3 V = normalize(cameraPosition - vWorldPos);
  float backlit = pow(clamp(dot(-V, uSunDir), 0.0, 1.0), 3.0) * 0.6;

  // Boosted to match MeshStandardMaterial surfaces lit by the same sun.
  vec3 light = uAmbientColor * 2.1
             + uGroundBounceColor * (underside * 0.75 + horizonFacing * 0.18)
             + uSunColor * keyAmount * (ndl * ndl * 3.2 + backlit * 2.4);
  light *= 1.0 - uNight * 0.45;

  vec3 color = tex.rgb * vColor * light;
  gl_FragColor = vec4(color, 1.0);

  #include <fog_fragment>
}
`;
