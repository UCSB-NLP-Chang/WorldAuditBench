// Seabed height field shared by the buoy mooring, the fish and the diver.
// The rest of the upstream environment (procedural sand shader, dodecahedron
// rocks, cone "grass") is replaced by app/seabed.js and app/reef.js.
const TAU = Math.PI * 2;

function smoothstep(a, b, x) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

export const SEABED_BASE = -6.2;

export function seabedHeight(x, z) {
  const r = Math.hypot(x, z);
  // gentle sand dunes and ripples
  let h = SEABED_BASE
    + Math.sin(x * 0.21 + z * 0.07) * 0.42
    + Math.sin(z * 0.17 - x * 0.05 + 1.3) * 0.30
    + Math.sin((x + z) * 0.55 + 0.7) * 0.10;
  // a shallow bowl of sand around the buoy anchor
  h -= 0.5 * Math.exp(-(r * r) / 45);
  // the reef ridge: an arc north-east of the buoy, 9..16 m out
  const angle = Math.atan2(z, x);
  const arc = smoothstep(-2.6, -1.9, angle) * (1 - smoothstep(0.9, 1.6, angle));
  const band = 1 - smoothstep(0, 3.6, Math.abs(r - 12.5));
  h += 2.4 * band * arc * (0.75 + 0.25 * Math.sin(angle * 5 + 1.2));
  // second, lower rise to the south-west so the far side is not empty
  const arc2 = smoothstep(1.9, 2.5, angle) + (1 - smoothstep(-3.0, -2.6, angle));
  const band2 = 1 - smoothstep(0, 4.0, Math.abs(r - 17));
  h += 1.3 * Math.min(1, arc2) * band2;
  // beyond the constrained area the floor drops away into deeper water
  h -= 3.0 * smoothstep(34, 90, r);
  return h;
}

export function seabedNormal(x, z, eps = 0.35) {
  const hx = seabedHeight(x + eps, z) - seabedHeight(x - eps, z);
  const hz = seabedHeight(x, z + eps) - seabedHeight(x, z - eps);
  const len = Math.hypot(hx, 2 * eps, hz);
  return { x: -hx / len, y: (2 * eps) / len, z: -hz / len };
}

export { TAU };
