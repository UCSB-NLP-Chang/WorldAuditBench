import * as THREE from 'three';
import { Pass, FullScreenQuad } from 'three/examples/jsm/postprocessing/Pass.js';
import { ATMOSPHERE } from '../config';
import type { SharedEnvUniforms } from '../world/Environment';

const FOG_VERTEX = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FOG_FRAGMENT = /* glsl */ `
precision highp float;

uniform sampler2D tDiffuse;
uniform sampler2D tDepth;
uniform mat4 uProjInv;
uniform mat4 uViewInv;
uniform vec3 uHorizonColor;
uniform vec3 uZenithColor;
uniform float uFalloffDist;
uniform float uMaxAmount;
uniform float uNight;

varying vec2 vUv;

void main() {
  vec4 base = texture2D(tDiffuse, vUv);
  float depth = texture2D(tDepth, vUv).x;

  // Sky pixels keep the dome's own haze; only fog real geometry.
  if (depth >= 0.99999) {
    gl_FragColor = base;
    return;
  }

  // Reconstruct view-space position for true euclidean distance.
  vec4 ndc = vec4(vUv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
  vec4 viewPos = uProjInv * ndc;
  viewPos /= viewPos.w;
  float dist = length(viewPos.xyz);

  // Aerial perspective: distance haze toward the horizon palette. The view
  // ray's world elevation picks between horizon and zenith tint so high
  // peaks fade into slightly bluer air than valley floors.
  vec3 worldDir = normalize((uViewInv * vec4(viewPos.xyz, 0.0)).xyz);
  float elev = clamp(worldDir.y * 2.2 + 0.25, 0.0, 1.0);
  vec3 hazeColor = mix(uHorizonColor, uZenithColor, elev * 0.45);

  float f = 1.0 - exp(-dist / uFalloffDist);
  f = f * f * (3.0 - 2.0 * f); // soften onset so mid-range stays crisp
  float amount = f * uMaxAmount * (1.0 - uNight * 0.35);

  gl_FragColor = vec4(mix(base.rgb, hazeColor, amount), base.a);
}
`;

/**
 * Scene render + compositor distance fog in one pass (separate from the
 * weather FogExp2). The scene is drawn into a private target with a depth
 * texture, then a depth-based aerial-perspective composite dissolves far
 * terrain into the horizon haze, hiding coarse distant geometry the way
 * real air does. Owning the scene render avoids sampling depth from the
 * composer's ping-pong buffers (a feedback-loop hazard).
 */
export class AerialFogPass extends Pass {
  private material: THREE.ShaderMaterial;
  private fsQuad: FullScreenQuad;
  private sceneRT: THREE.WebGLRenderTarget;
  private projInv = new THREE.Matrix4();

  constructor(
    private scene: THREE.Scene,
    private camera: THREE.PerspectiveCamera,
    env: SharedEnvUniforms,
    width: number,
    height: number,
  ) {
    super();

    this.sceneRT = new THREE.WebGLRenderTarget(Math.max(width, 1), Math.max(height, 1), {
      type: THREE.HalfFloatType,
      depthTexture: new THREE.DepthTexture(Math.max(width, 1), Math.max(height, 1)),
    });

    this.material = new THREE.ShaderMaterial({
      vertexShader: FOG_VERTEX,
      fragmentShader: FOG_FRAGMENT,
      uniforms: {
        tDiffuse: { value: this.sceneRT.texture },
        tDepth: { value: this.sceneRT.depthTexture },
        uProjInv: { value: new THREE.Matrix4() },
        uViewInv: { value: new THREE.Matrix4() },
        uHorizonColor: env.uHorizonColor,
        uZenithColor: env.uZenithColor,
        uNight: env.uNight,
        uFalloffDist: { value: ATMOSPHERE.aerial.falloffDistance },
        uMaxAmount: { value: ATMOSPHERE.aerial.maxAmount },
      },
      depthTest: false,
      depthWrite: false,
    });
    this.fsQuad = new FullScreenQuad(this.material);
    this.needsSwap = true;
  }

  override setSize(width: number, height: number): void {
    this.sceneRT.setSize(width, height);
  }

  override render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget): void {
    // 1. Scene (with depth) into the private target.
    renderer.setRenderTarget(this.sceneRT);
    renderer.clear();
    renderer.render(this.scene, this.camera);

    // 2. Composite with distance fog into the composer chain.
    const u = this.material.uniforms;
    u.tDiffuse.value = this.sceneRT.texture;
    u.tDepth.value = this.sceneRT.depthTexture;
    (u.uProjInv.value as THREE.Matrix4).copy(this.projInv.copy(this.camera.projectionMatrix).invert());
    (u.uViewInv.value as THREE.Matrix4).copy(this.camera.matrixWorld);

    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.fsQuad.render(renderer);
  }

  override dispose(): void {
    this.sceneRT.dispose();
    this.material.dispose();
    this.fsQuad.dispose();
  }
}
