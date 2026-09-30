import { NOISE_GLSL } from './noiseGLSL';

/**
 * Water surface shader:
 * - wind-driven vertex waves + fBm-perturbed normals
 * - Fresnel mixing between depth tint and an analytic sky reflection that
 *   tracks the time-of-day palette
 * - shoreline foam from a baked per-vertex depth attribute
 * - player ripples: expanding rings broken up by angular + radial noise so
 *   they read as churned water, biased in the direction of movement
 * - double-sided: seen from below, the surface shows a refracted-looking
 *   bright "Snell window" toward the sky and darker water elsewhere
 */

export const WATER_VERTEX = /* glsl */ `
#include <common>
#include <fog_pars_vertex>

uniform float uTime;
uniform vec2 uWindDir;
uniform float uWindStrength;

attribute float aDepth;

varying vec3 vWorldPos;
varying float vDepth;

void main() {
  vec3 transformed = position;

  vec4 wp = modelMatrix * vec4(transformed, 1.0);

  // Three-component trochoidal-style swell. Wind raises wave height (calm
  // ponds stay near-flat); phase speeds stay fixed so strong gusts don't
  // turn into a fast periodic shimmer. Depth damps waves near shore.
  float windAmp = clamp(uWindStrength, 0.0, 2.2);
  float amp = 0.07 * (0.18 + windAmp * windAmp * 0.55) * clamp(aDepth * 2.0, 0.15, 1.0);
  vec2 d1 = uWindDir;
  vec2 d2 = normalize(uWindDir + vec2(-0.55, 0.42));
  vec2 d3 = vec2(-uWindDir.y, uWindDir.x);
  float p1 = dot(wp.xz, d1) * 0.30 + uTime * 0.85;
  float p2 = dot(wp.xz, d2) * 0.17 + uTime * 0.55;
  float p3 = dot(wp.xz, d3) * 0.43 + uTime * 1.15;
  wp.y += sin(p1) * amp + sin(p2) * amp * 0.65 + sin(p3) * amp * 0.3;
  // Slight horizontal crest sharpening along the main wind direction.
  wp.xz += d1 * cos(p1) * amp * 0.6;

  vWorldPos = wp.xyz;
  vDepth = aDepth;

  vec4 mvPosition = viewMatrix * wp;
  gl_Position = projectionMatrix * mvPosition;

  #include <fog_vertex>
}
`;

export const WATER_FRAGMENT = /* glsl */ `
#include <common>
#include <fog_pars_fragment>

uniform float uTime;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uZenithColor;
uniform vec3 uHorizonColor;
uniform vec3 uShallowColor;
uniform vec3 uDeepColor;
uniform vec3 uPlayerPos;
uniform vec2 uPlayerVel;
uniform float uPlayerRipple;
uniform vec2 uWindDir;
uniform float uWindStrength;
uniform float uNight;
uniform float uCloudCover;
uniform float uStarAngle;

varying vec3 vWorldPos;
varying float vDepth;

${NOISE_GLSL}

float nhash3(vec3 p) {
  p = fract(p * vec3(443.897, 441.423, 437.195));
  p += dot(p, p.zxy + 31.31);
  return fract((p.x + p.y) * p.z);
}

// Analytic sky reflection matching the dome's current palette. On calm
// clear nights the reflected sky carries stars and the Milky Way band
// (sharp on still ponds, washed out as wind churns the surface).
vec3 skyReflection(vec3 dir) {
  float h = clamp(dir.y, 0.0, 1.0);
  vec3 sky = mix(uHorizonColor, uZenithColor, pow(h, 0.55));
  float sunDot = clamp(dot(dir, uSunDir), 0.0, 1.0);
  sky += uSunColor * (pow(sunDot, 250.0) * 3.0 + pow(sunDot, 24.0) * 0.25);

  float calm = 1.0 - clamp(uWindStrength * 0.85, 0.0, 1.0);
  float starVis = uNight * (1.0 - uCloudCover * 0.9) * calm;
  if (starVis > 0.03 && dir.y > 0.02) {
    // Inverse of the star-sprite rotation (same as the dome) so the
    // reflected band drifts with the real stars.
    vec3 axis = normalize(vec3(0.2, 0.78, 0.35));
    float ca = cos(uStarAngle);
    float sa = -sin(uStarAngle);
    vec3 sdir = dir * ca + cross(axis, dir) * sa + axis * dot(axis, dir) * (1.0 - ca);

    vec3 p = sdir * 56.0;
    vec3 cell = floor(p);
    float sel = nhash3(cell);
    if (sel > 0.985) {
      vec3 f = fract(p) - 0.5;
      vec3 jit = vec3(nhash3(cell + 11.0), nhash3(cell + 27.0), nhash3(cell + 43.0)) - 0.5;
      float dd = length(f - jit * 0.55);
      float mag = (sel - 0.985) / 0.015;
      sky += vec3(0.8, 0.87, 1.0) * smoothstep(0.3, 0.0, dd) * (0.3 + mag * 1.2) * starVis;
    }
    // Faint Milky Way band.
    vec3 galN = normalize(vec3(0.42, 0.32, 0.85));
    float bandDist = dot(sdir, galN);
    float band = exp(-bandDist * bandDist * 38.0);
    sky += vec3(0.5, 0.58, 0.78) * band * 0.1 * starVis;
  }
  return sky;
}

void main() {
  vec2 p = vWorldPos.xz;
  // Scroll speed fixed; wind only adds a little extra normal roughness.
  vec2 drift1 = uWindDir * uTime * 0.038;
  vec2 drift2 = uWindDir * uTime * -0.032 + vec2(0.0, uTime * 0.018);
  float n1 = fbm(p * 0.45 + drift1);
  float n2 = fbm(p * 0.95 + drift2);
  float hgt = n1 * 0.7 + n2 * 0.3;

  // --- Player ripples: noisy, irregular rings around the wading player ---
  vec2 toP = p - uPlayerPos.xz;
  float playerDist = length(toP);
  float rip = 0.0;
  vec2 rippleDir = vec2(0.0);
  if (uPlayerRipple > 0.001 && playerDist < 8.0) {
    // Direction coordinates are periodic around the player. Feeding atan()
    // directly into noise creates a visible seam where its angle wraps.
    vec2 radialDir = toP / max(playerDist, 0.001);
    rippleDir = radialDir;
    float angN = fbm(
      radialDir * 2.2 +
      vec2(playerDist * 0.34 - uTime * 0.22, playerDist * -0.27 + uTime * 0.16)
    );
    float radN = fbm(toP * 1.3 + uTime * 0.4);
    // Movement bias: stronger wake behind/around the direction of travel.
    float moveBias = 1.0 + 0.8 * clamp(dot(normalize(toP + 1e-4), -normalize(uPlayerVel + 1e-4)), 0.0, 1.0) * min(length(uPlayerVel), 1.0);
    float ring = sin(playerDist * (6.0 + radN * 3.5) - uTime * 6.5 + angN * 4.0);
    rip = ring * exp(-playerDist * (0.55 + radN * 0.2)) * uPlayerRipple * (0.55 + angN * 0.9) * moveBias;
  }

  // Normal from finite differences.
  float e = 0.35;
  float hx = fbm((p + vec2(e, 0.0)) * 0.45 + drift1) * 0.7 + fbm((p + vec2(e, 0.0)) * 0.95 + drift2) * 0.3;
  float hz = fbm((p + vec2(0.0, e)) * 0.45 + drift1) * 0.7 + fbm((p + vec2(0.0, e)) * 0.95 + drift2) * 0.3;
  // Calm water is near-mirror; wind roughens the micro-normals.
  float bump = 0.5 + clamp(uWindStrength, 0.0, 2.2) * 1.05;
  vec3 normal = normalize(vec3(-(hx - hgt) * bump, 1.0, -(hz - hgt) * bump));
  // Ripple slope follows its radial direction instead of biasing both finite
  // difference axes equally, which produced a diagonal lighting streak.
  normal = normalize(normal + vec3(-rippleDir.x * rip * 1.4, 0.0, -rippleDir.y * rip * 1.4));

  vec3 viewDir = normalize(cameraPosition - vWorldPos);
  bool above = cameraPosition.y > vWorldPos.y;

  vec3 color;
  float alpha;

  if (above) {
    vec3 reflDir = reflect(-viewDir, normal);
    reflDir.y = abs(reflDir.y);

    float fresnel = pow(1.0 - clamp(dot(viewDir, normal), 0.0, 1.0), 5.0);
    fresnel = mix(0.12, 1.0, fresnel);

    float depthT = clamp(vDepth / 7.0, 0.0, 1.0);
    vec3 waterColor = mix(uShallowColor, uDeepColor, depthT) * (1.0 - uNight * 0.7);

    vec3 reflection = skyReflection(reflDir);
    color = mix(waterColor, reflection * 1.18, fresnel);

    // Sun glints.
    vec3 halfDir = normalize(uSunDir + viewDir);
    float spec = pow(clamp(dot(normal, halfDir), 0.0, 1.0), 180.0);
    color += uSunColor * spec * 1.6;

    // Shoreline foam + churned foam around the player.
    float foamNoise = fbm(p * 1.7 + uWindDir * uTime * 0.12);
    float shoreFoam = smoothstep(0.7, 0.0, vDepth) * smoothstep(0.35, 0.75, foamNoise);
    float ringFoam = clamp(abs(rip) * 2.2, 0.0, 1.0);
    float foam = clamp(shoreFoam * 0.8 + ringFoam * 0.6, 0.0, 1.0);
    color = mix(color, vec3(0.92, 0.95, 0.94) * (1.0 - uNight * 0.6), foam);

    alpha = clamp(0.6 + fresnel * 0.35 + depthT * 0.2, 0.0, 0.96);
    alpha = max(alpha, foam * 0.9);
  } else {
    // Underside: total internal reflection outside the Snell window. Inside
    // the window the sky shows through, refracted and wobbled by the waves.
    vec3 upDir = vec3(0.0, 1.0, 0.0);
    float cosUp = clamp(dot(viewDir, upDir), 0.0, 1.0);
    float window = smoothstep(0.62, 0.78, cosUp + hgt * 0.12);

    vec3 refr = refract(-viewDir, -normal, 0.752);
    vec3 skyThrough = skyReflection(refr.y > 0.0 ? refr : upDir);
    vec3 tir = mix(uDeepColor * 0.6, uShallowColor * 0.5, hgt) * (1.0 - uNight * 0.6);

    color = mix(tir, skyThrough * 1.05, window);
    // Caustic-ish shimmer.
    color += uSunColor * pow(clamp(hgt, 0.0, 1.0), 3.0) * 0.25 * window;
    alpha = mix(0.85, 0.55, window);
  }

  gl_FragColor = vec4(color, alpha);

  #include <fog_fragment>
}
`;
