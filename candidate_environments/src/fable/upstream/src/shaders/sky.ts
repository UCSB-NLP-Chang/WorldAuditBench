import { NOISE_GLSL } from './noiseGLSL';

/**
 * Procedural atmosphere and deep-sky gradients. Individual stars are rendered
 * as real point sprites by Sky.ts; keeping them out of the dome shader avoids
 * cell/ring artifacts and gives every star a stable circular shape.
 */

export const SKY_VERTEX = /* glsl */ `
varying vec3 vDir;

void main() {
  vDir = normalize(position);
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mvPosition;
  gl_Position.z = gl_Position.w * 0.99999;
}
`;

export const SKY_FRAGMENT = /* glsl */ `
uniform vec3 uSunDir;
uniform vec3 uMoonDir;
uniform vec3 uZenithColor;
uniform vec3 uHorizonColor;
uniform vec3 uHazeColor;
uniform vec3 uSunColor;
uniform float uTime;
uniform float uNight;
uniform float uCloudCover;
uniform float uCloudDark;
uniform vec2 uWind;
uniform float uStarAngle;
uniform float uGalaxyStrength;
uniform float uNebulaStrength;

varying vec3 vDir;

${NOISE_GLSL}

vec3 rotateAroundAxis(vec3 p, vec3 axis, float angle) {
  float c = cos(angle);
  float s = sin(angle);
  return p * c + cross(axis, p) * s + axis * dot(axis, p) * (1.0 - c);
}

float hash3(vec3 p) {
  p = fract(p * 0.1031);
  p += dot(p, p.yzx + 33.33);
  return fract((p.x + p.y) * p.z);
}

float noise3(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(mix(hash3(i), hash3(i + vec3(1, 0, 0)), f.x),
        mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
    mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x),
        mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y),
    f.z
  );
}

float fbm3(vec3 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 4; i++) {
    value += noise3(p) * amplitude;
    p = p * 2.03 + vec3(7.1, 13.7, 5.9);
    amplitude *= 0.5;
  }
  return value;
}

void main() {
  vec3 dir = normalize(vDir);
  float h = clamp(dir.y, -1.0, 1.0);

  float zenithMix = pow(clamp(h, 0.0, 1.0), 0.5);
  vec3 sky = mix(uHorizonColor, uZenithColor, zenithMix);
  float haze = pow(1.0 - clamp(h, 0.0, 1.0), 5.0);
  sky = mix(sky, uHazeColor, haze * 0.85);

  float sunDot = clamp(dot(dir, uSunDir), 0.0, 1.0);
  float horizonBoost = 1.0 + (1.0 - clamp(uSunDir.y * 3.0, 0.0, 1.0)) * 2.2;
  float halo = pow(sunDot, 24.0) * 0.3 * horizonBoost + pow(sunDot, 300.0) * 0.7;
  float disc = smoothstep(0.9995, 0.9999, sunDot);
  float sunVis = smoothstep(-0.12, 0.02, uSunDir.y);
  sky += uSunColor * (halo + disc * 5.0) * sunVis;

  float moonDot = clamp(dot(dir, uMoonDir), 0.0, 1.0);
  float moonDisc = smoothstep(0.99995, 0.999985, moonDot);
  float moonGlow = pow(moonDot, 280.0) * 0.1;
  sky += vec3(0.82, 0.88, 1.0) * (moonDisc * 1.15 + moonGlow) * uNight;

  float clearNight = uNight * (1.0 - uCloudCover * 0.88);
  if (clearNight > 0.01 && h > -0.08) {
    vec3 axis = normalize(vec3(0.2, 0.78, 0.35));
    // Inverse of the star-sprite rotation so the band tracks the stars.
    vec3 celestial = rotateAroundAxis(dir, axis, -uStarAngle);

    // A broad great-circle Milky Way. Every layer is a continuous gradient;
    // noise only modulates opacity, never creates hard patches.
    vec3 galaxyNormal = normalize(vec3(0.42, 0.32, 0.85));
    vec3 galaxyTangent = normalize(cross(galaxyNormal, vec3(0.0, 1.0, 0.0)));
    vec3 galaxyBitangent = cross(galaxyNormal, galaxyTangent);
    float latitude = dot(celestial, galaxyNormal);
    float longitude = atan(dot(celestial, galaxyBitangent), dot(celestial, galaxyTangent));

    // Galactic-centre bulge: the band runs brighter, wider, and warmer
    // toward one longitude and tapers to a thin cold edge opposite it.
    float toCore = cos(longitude - 0.85) * 0.5 + 0.5;
    float bulge = toCore * toCore * toCore;
    float widthK = mix(1.45, 0.6, bulge);
    float broadBand = exp(-latitude * latitude * 4.0 * widthK);
    float mainBand = exp(-latitude * latitude * 12.5 * widthK);
    float coreBand = exp(-latitude * latitude * 36.0 * widthK);
    float bandGain = mix(0.55, 1.6, bulge);

    // Direction-space noise gives soft celestial clouds without projected
    // streaks, seams, square cells, or repeated ring patterns.
    float macroCloud = fbm3(celestial * 2.2 + vec3(4.2, 8.7, 1.4));
    float smoke = fbm3(celestial * 5.0 + vec3(18.1, 2.4, 11.7));
    float fineSmoke = fbm3(celestial * 10.0 + vec3(2.7, 31.4, 8.3));

    float cloudy = smoothstep(0.16, 0.8, macroCloud) * 0.5
                 + smoothstep(0.3, 0.78, smoke) * 0.34
                 + smoothstep(0.42, 0.76, fineSmoke) * 0.16;

    // Unresolved-starlight grain keeps the band from looking airbrushed.
    float grain = noise3(celestial * 26.0) * 0.6 + noise3(celestial * 54.0) * 0.4;

    float galaxy = (broadBand * (0.025 + cloudy * 0.32)
                  + mainBand * (0.05 + cloudy * 0.52)
                  + coreBand * (0.11 + smoothstep(0.2, 0.8, macroCloud) * 0.26)) * bandGain;
    galaxy *= 0.8 + grain * 0.4;

    // The Great Rift: a meandering, broken dust lane that splits the bright
    // band lengthwise and sells the edge-on-galaxy silhouette.
    float laneShift = (fbm3(celestial * 1.7 + vec3(7.7, 19.2, 3.1)) - 0.5) * 0.24;
    float laneDelta = (latitude - laneShift) * 13.0;
    float rift = exp(-laneDelta * laneDelta);
    float riftBreaks = smoothstep(0.3, 0.62, fbm3(celestial * 3.4 + vec3(29.0, 5.5, 13.8)));
    galaxy *= 1.0 - rift * riftBreaks * mainBand * 0.92;

    // Colour ramp: cold blue outskirts, dusty violet mid, golden core.
    vec3 coldSmoke = vec3(0.16, 0.32, 0.78);
    vec3 violetSmoke = vec3(0.5, 0.26, 0.68);
    vec3 warmCore = vec3(0.95, 0.66, 0.38);
    vec3 galaxyColor = mix(coldSmoke, violetSmoke, smoothstep(0.2, 0.85, smoke));
    galaxyColor = mix(galaxyColor, warmCore, coreBand * bulge * 0.85);

    float horizonFade = smoothstep(-0.06, 0.18, h);
    sky += galaxyColor * galaxy * uGalaxyStrength * clearNight * horizonFade;

    // Distinct emission nebulae: sparse regions picked by low-frequency
    // noise, shaped by ridged filaments, in rose and teal palettes.
    float nebRegion = smoothstep(0.6, 0.82, fbm3(celestial * 1.6 + vec3(23.1, 7.7, 15.3)));
    float nebDetail = fbm3(celestial * 6.0 + vec3(9.2, 27.3, 4.4));
    float filament = pow(smoothstep(0.5, 0.95, 1.0 - abs(2.0 * nebDetail - 1.0)), 1.7);
    float nebula = nebRegion * (smoothstep(0.35, 0.8, nebDetail) * 0.5 + filament * 0.9);
    nebula *= mix(0.3, 1.0, broadBand) * (1.0 - rift * riftBreaks * 0.6);
    vec3 nebColor = mix(vec3(0.85, 0.26, 0.4), vec3(0.2, 0.55, 0.62),
                        smoothstep(0.3, 0.7, fbm3(celestial * 2.4 + vec3(31.0, 3.0, 19.0))));
    sky += nebColor * nebula * uNebulaStrength * clearNight * horizonFade;
  }

  if (h > 0.015) {
    vec2 cuv = dir.xz / (dir.y + 0.12) * 1.5;
    cuv += uWind * uTime * 0.004;
    float c = fbm(cuv * 1.3 + fbm(cuv * 3.1) * 0.5);
    float lo = mix(0.66, 0.30, uCloudCover);
    float hi = mix(0.92, 0.52, uCloudCover);
    c = smoothstep(lo, hi, c);
    c *= smoothstep(0.015, 0.18, h);

    float dayLight = 1.0 - uNight * 0.82;
    vec3 cloudBright = mix(vec3(0.92, 0.92, 0.94), vec3(0.38, 0.4, 0.45), uCloudDark) * dayLight;
    vec3 cloudShade = mix(vec3(0.62, 0.64, 0.7), vec3(0.2, 0.21, 0.25), uCloudDark) * dayLight;
    vec3 cloudCol = mix(cloudBright, cloudShade, c * 0.85);
    cloudCol += uSunColor * pow(sunDot, 6.0) * 0.3 * (1.0 - uCloudDark) * sunVis;
    float cloudOpacity = mix(0.55 + uCloudCover * 0.4, 0.08 + uCloudCover * 0.55, uNight);
    sky = mix(sky, cloudCol, c * cloudOpacity);
  }

  sky = mix(sky, uHazeColor, smoothstep(0.0, -0.25, h));
  gl_FragColor = vec4(sky, 1.0);
}
`;

export const STAR_VERTEX = /* glsl */ `
attribute float aSize;
attribute vec3 aColor;
attribute float aPhase;
uniform float uTime;
uniform float uNight;
uniform float uCloudCover;
uniform float uStarBrightness;
uniform float uStarAngle;
varying vec3 vColor;
varying float vAlpha;

void main() {
  vec3 axis = normalize(vec3(0.2, 0.78, 0.35));
  float c = cos(uStarAngle);
  float s = sin(uStarAngle);
  vec3 rotated = position * c + cross(axis, position) * s + axis * dot(axis, position) * (1.0 - c);
  vec4 mv = modelViewMatrix * vec4(rotated, 1.0);
  gl_Position = projectionMatrix * mv;
  float twinkle = 0.9 + sin(uTime * (0.35 + aPhase * 0.5) + aPhase * 41.0) * 0.1;
  gl_PointSize = aSize * twinkle;
  vColor = aColor;
  float horizonFade = smoothstep(-0.06, 0.14, normalize(rotated).y);
  vAlpha = uNight * (1.0 - uCloudCover * 0.9) * uStarBrightness * horizonFade;
}
`;

export const STAR_FRAGMENT = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;

void main() {
  vec2 p = gl_PointCoord - 0.5;
  float r = length(p);
  float core = 1.0 - smoothstep(0.05, 0.24, r);
  float glow = (1.0 - smoothstep(0.08, 0.5, r)) * 0.28;
  float alpha = (core + glow) * vAlpha;
  if (alpha < 0.01) discard;
  gl_FragColor = vec4(vColor * (core * 1.35 + glow), alpha);
}
`;
