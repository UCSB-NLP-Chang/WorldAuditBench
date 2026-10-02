/**
 * Instanced grass shader. Blades bend by an amount proportional to uv.y so
 * roots stay planted. Wind is a global field: a large travelling wave moving
 * along the wind direction (whole meadows flow together) plus local jitter,
 * all scaled by the gusting wind strength from the Environment.
 * Per-instance color arrives via instanceColor (THREE.InstancedMesh).
 */

export const GRASS_VERTEX = /* glsl */ `
#include <common>
#include <fog_pars_vertex>

uniform float uTime;
uniform vec2 uWindDir;
uniform float uWindStrength;

varying vec3 vColor;
varying float vHeight;

void main() {
  #ifdef USE_INSTANCING_COLOR
    vColor = instanceColor;
  #else
    vColor = vec3(1.0);
  #endif

  vec3 transformed = position;

  #ifdef USE_INSTANCING
    vec4 worldOrigin = modelMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);
  #else
    vec4 worldOrigin = modelMatrix * vec4(0.0, 0.0, 0.0, 1.0);
  #endif

  // Bend factor: tips move, roots stay planted.
  float bend = uv.y * uv.y;

  // Large travelling wave: meadows flow in the wind direction.
  float along = dot(worldOrigin.xz, uWindDir);
  float wave = sin(along * 0.12 - uTime * 2.1) * 0.55
             + sin(along * 0.043 - uTime * 1.13 + 1.3) * 0.45;

  // Subtle fixed-rate flutter — not scaled by wind (that caused periodic shake in gusts).
  float phase = worldOrigin.x * 0.71 + worldOrigin.z * 0.53;
  float jitter = sin(uTime * 1.6 + phase) * 0.14 + sin(uTime * 2.4 + phase * 1.7) * 0.06;

  float sway = wave * uWindStrength * 0.55 + jitter;
  transformed.x += uWindDir.x * sway * bend;
  transformed.z += uWindDir.y * sway * bend;
  // Blades crouch slightly in strong gusts.
  transformed.y -= abs(sway) * bend * 0.25;

  vHeight = uv.y;

  #ifdef USE_INSTANCING
    vec4 mvPosition = modelViewMatrix * instanceMatrix * vec4(transformed, 1.0);
  #else
    vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
  #endif

  gl_Position = projectionMatrix * mvPosition;

  #include <fog_vertex>
}
`;

export const GRASS_FRAGMENT = /* glsl */ `
#include <common>
#include <fog_pars_fragment>

uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uAmbientColor;
uniform vec3 uGroundBounceColor;
uniform float uNight;

varying vec3 vColor;
varying float vHeight;

void main() {
  // Fake lighting: blades brighter toward the tip and lit by the key light.
  // Boosted to match MeshStandardMaterial terrain lit by the same sun.
  float keyAmount = clamp(uSunDir.y, 0.0, 1.0);
  vec3 light = uAmbientColor * 2.0
             + uGroundBounceColor * (0.16 + (1.0 - vHeight) * 0.18)
             + uSunColor * keyAmount * (1.1 + vHeight * 1.2);
  // At night the moon light is already dim; keep grass from glowing.
  light *= 1.0 - uNight * 0.45;
  vec3 color = vColor * light;

  // Darken roots for grounded look (cheap ambient occlusion).
  color *= mix(0.5, 1.06, vHeight);

  gl_FragColor = vec4(color, 1.0);

  #include <fog_fragment>
}
`;
