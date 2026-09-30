// Shader patches shared by the underwater materials:
//   applyUnderwater(material, opts)  -> animated caustics on up-facing surfaces + world-space fog tint
//   applySway(material, opts)        -> vertex sway for grass/kelp/soft corals (uses uv.y as height)
// All patched materials share one uniform set so main.js updates time/underwater once per frame.
import * as THREE from 'three';

export const shared = {
  uTime: { value: 0 },
  uUnderwater: { value: 0 },
  uSway: { value: 1 },
};

const CAUSTIC_GLSL = /* glsl */ `
  float causticHash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }
  float causticEdge(vec2 p, float phase) {
    vec2 cell = floor(p);
    vec2 local = fract(p);
    float closest = 10.0;
    float second = 10.0;
    for (int y = -1; y <= 1; y++) {
      for (int x = -1; x <= 1; x++) {
        vec2 offset = vec2(float(x), float(y));
        vec2 id = cell + offset;
        vec2 seed = vec2(causticHash(id + vec2(17.1, 3.7)), causticHash(id + vec2(5.3, 29.9)));
        vec2 feature = 0.5 + 0.34 * sin(seed * 6.2831853 + vec2(phase, -phase * 0.83));
        vec2 delta = offset + feature - local;
        float d = dot(delta, delta);
        if (d < closest) { second = closest; closest = d; }
        else if (d < second) { second = d; }
      }
    }
    return 1.0 - smoothstep(0.02, 0.10, sqrt(second) - sqrt(closest));
  }
  float caustic(vec2 p, float t) {
    float a = causticEdge(p, t * 0.34);
    float b = causticEdge(mat2(0.76, -0.65, 0.65, 0.76) * p * 1.27 + 9.4, -t * 0.27);
    return pow(a, 1.6) * mix(0.25, 1.0, b);
  }
`;

export function applyUnderwater(material, { strength = 0.9, scale = 0.55, tint = true } = {}) {
  material.userData.causticStrength = strength;
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = shared.uTime;
    shader.uniforms.uUnderwater = shared.uUnderwater;
    shader.uniforms.uCausticStrength = { value: strength };
    shader.uniforms.uCausticScale = { value: scale };
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vCausticPos;\nvarying vec3 vCausticNormal;')
      .replace('#include <worldpos_vertex>', `#include <worldpos_vertex>
        {
          vec4 cp = vec4( transformed, 1.0 );
          vec3 cn = objectNormal;
          #ifdef USE_INSTANCING
            cp = instanceMatrix * cp;
            cn = mat3( instanceMatrix ) * cn;
          #endif
          cp = modelMatrix * cp;
          vCausticPos = cp.xyz;
          vCausticNormal = normalize( mat3( modelMatrix ) * cn );
        }`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float uTime;\nuniform float uUnderwater;\nuniform float uCausticStrength;\nuniform float uCausticScale;\nvarying vec3 vCausticPos;\nvarying vec3 vCausticNormal;\n' + CAUSTIC_GLSL)
      .replace('#include <fog_fragment>', `
        {
          float up = clamp( vCausticNormal.y * 0.8 + 0.2, 0.0, 1.0 );
          float c = caustic( vCausticPos.xz * uCausticScale, uTime ) * up;
          gl_FragColor.rgb *= 1.0 + c * uCausticStrength * uUnderwater;
          ${tint ? 'gl_FragColor.rgb = mix( gl_FragColor.rgb, gl_FragColor.rgb * vec3( 0.8, 0.96, 1.0 ), uUnderwater * 0.22 );' : ''}
        }
        #include <fog_fragment>`);
  };
  material.customProgramCacheKey = () => `underwater-${strength}-${scale}-${tint}`;
  return material;
}

export function applySway(material, { amplitude = 0.16, frequency = 1.1, height = 1.0 } = {}) {
  const prev = material.onBeforeCompile;
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = shared.uTime;
    shader.uniforms.uSway = shared.uSway;
    shader.uniforms.uSwayAmp = { value: amplitude };
    shader.uniforms.uSwayFreq = { value: frequency };
    shader.uniforms.uSwayHeight = { value: height };
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float uTime;\nuniform float uSway;\nuniform float uSwayAmp;\nuniform float uSwayFreq;\nuniform float uSwayHeight;')
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        {
          vec3 anchor = vec3( 0.0 );
          #ifdef USE_INSTANCING
            anchor = instanceMatrix[3].xyz;
          #endif
          float phase = anchor.x * 0.7 + anchor.z * 0.5;
          float k = clamp( position.y / uSwayHeight, 0.0, 1.0 );
          k = k * k;
          float s1 = sin( uTime * uSwayFreq + phase );
          float s2 = sin( uTime * uSwayFreq * 2.3 + phase * 1.7 + 1.0 );
          transformed.x += ( s1 * 0.8 + s2 * 0.25 ) * uSwayAmp * k * uSway;
          transformed.z += ( cos( uTime * uSwayFreq * 0.8 + phase ) * 0.5 ) * uSwayAmp * k * uSway;
        }`);
    if (prev) prev(shader);
  };
  const prevKey = material.customProgramCacheKey;
  material.customProgramCacheKey = () => `sway-${amplitude}-${frequency}-${height}-` + (prevKey ? prevKey.call(material) : '');
  return material;
}

// Fish swim: bend the body along its length (local z) with a per-instance phase attribute.
export function applySwim(material, { amplitude = 0.08, frequency = 6.5, length = 0.64 } = {}) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = shared.uTime;
    shader.uniforms.uSwimAmp = { value: amplitude };
    shader.uniforms.uSwimFreq = { value: frequency };
    shader.uniforms.uSwimLen = { value: length };
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float uTime;\nuniform float uSwimAmp;\nuniform float uSwimFreq;\nuniform float uSwimLen;\nattribute float aPhase;\nattribute float aSpeed;')
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        {
          // tail (negative z) wags most; head stays still
          float t = clamp( ( -position.z / uSwimLen ) + 0.5, 0.0, 1.0 );
          float bend = sin( uTime * uSwimFreq * aSpeed + aPhase - t * 3.2 ) * uSwimAmp * ( 0.08 + t * t );
          transformed.x += bend;
        }`);
  };
  material.customProgramCacheKey = () => `swim-${amplitude}-${frequency}-${length}`;
  return material;
}
