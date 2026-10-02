/**
 * Small shared GLSL noise library (hash-based value noise + fBm). Cheap
 * enough to run per-fragment for water and sky clouds.
 */
export const NOISE_GLSL = /* glsl */ `
float nhash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = nhash(i);
  float b = nhash(i + vec2(1.0, 0.0));
  float c = nhash(i + vec2(0.0, 1.0));
  float d = nhash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 4; i++) {
    v += a * vnoise(p);
    p = p * 2.07 + vec2(13.7, 7.1);
    a *= 0.5;
  }
  return v;
}
`;
