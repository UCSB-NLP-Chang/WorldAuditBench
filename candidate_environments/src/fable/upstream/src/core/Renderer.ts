import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js';
import { FXAAShader } from 'three/examples/jsm/shaders/FXAAShader.js';
import { AerialFogPass } from '../render/AerialFogPass';
import type { SharedEnvUniforms } from '../world/Environment';
import { RENDERER, type QualitySettings } from '../config';
import { logGpuInfo, type GpuInfo } from '../utils/GpuInfo';

const BLOOM_OUTPUT_FRAGMENT = /* glsl */ `
  precision highp float;

  uniform sampler2D tDiffuse;
  uniform vec2 uTexelSize;
  uniform float uBloomStrength;
  uniform float uBloomThreshold;

  #include <tonemapping_pars_fragment>
  #include <colorspace_pars_fragment>

  varying vec2 vUv;

  vec3 brightSample(vec2 uv) {
    vec3 color = texture2D(tDiffuse, uv).rgb;
    float peak = max(max(color.r, color.g), color.b);
    return color * smoothstep(uBloomThreshold, uBloomThreshold + 0.55, peak);
  }

  void main() {
    vec4 base = texture2D(tDiffuse, vUv);
    // Two rings of taps — a tight inner cross plus a wider diagonal ring — give
    // a softer, further-reaching scatter around bright sources (e.g. fire).
    vec2 o1 = uTexelSize * 3.0;
    vec2 o2 = uTexelSize * 6.5;
    vec3 glow =
      brightSample(vUv + vec2(o1.x, 0.0)) +
      brightSample(vUv - vec2(o1.x, 0.0)) +
      brightSample(vUv + vec2(0.0, o1.y)) +
      brightSample(vUv - vec2(0.0, o1.y)) +
      brightSample(vUv + vec2(o2.x, o2.y)) +
      brightSample(vUv - vec2(o2.x, o2.y)) +
      brightSample(vUv + vec2(o2.x, -o2.y)) +
      brightSample(vUv - vec2(o2.x, -o2.y));
    gl_FragColor = vec4(base.rgb + glow * (uBloomStrength * 0.14), base.a);

    #ifdef LINEAR_TONE_MAPPING
      gl_FragColor.rgb = LinearToneMapping(gl_FragColor.rgb);
    #elif defined(REINHARD_TONE_MAPPING)
      gl_FragColor.rgb = ReinhardToneMapping(gl_FragColor.rgb);
    #elif defined(CINEON_TONE_MAPPING)
      gl_FragColor.rgb = OptimizedCineonToneMapping(gl_FragColor.rgb);
    #elif defined(ACES_FILMIC_TONE_MAPPING)
      gl_FragColor.rgb = ACESFilmicToneMapping(gl_FragColor.rgb);
    #elif defined(AGX_TONE_MAPPING)
      gl_FragColor.rgb = AgXToneMapping(gl_FragColor.rgb);
    #elif defined(NEUTRAL_TONE_MAPPING)
      gl_FragColor.rgb = NeutralToneMapping(gl_FragColor.rgb);
    #endif

    #ifdef SRGB_TRANSFER
      gl_FragColor = sRGBTransferOETF(gl_FragColor);
    #endif
  }
`;

/**
 * WebGLRenderer wrapper: color management, ACES tone mapping, capped pixel
 * ratio, soft shadows, and resize handling.
 */
export class Renderer {
  readonly webgl: THREE.WebGLRenderer;
  readonly gpuInfo: GpuInfo;
  private maxPixelRatio: number;
  private pixelRatioScale = 1;
  private composer: EffectComposer | null = null;
  private outputPass: OutputPass | null = null;
  private fxaaPass: ShaderPass | null = null;
  private drawingBufferSize = new THREE.Vector2();

  constructor(container: HTMLElement, quality: QualitySettings) {
    this.maxPixelRatio = quality.maxPixelRatio;

    this.webgl = new THREE.WebGLRenderer({
      antialias: quality.antialias,
      powerPreference: 'high-performance',
    });
    this.webgl.setSize(window.innerWidth, window.innerHeight);
    this.webgl.setPixelRatio(Math.min(window.devicePixelRatio, this.maxPixelRatio));

    // Cinematic, filmic look with correct color pipeline.
    this.webgl.outputColorSpace = THREE.SRGBColorSpace;
    this.webgl.toneMapping = THREE.ACESFilmicToneMapping;
    this.webgl.toneMappingExposure = RENDERER.exposure;

    this.webgl.shadowMap.enabled = quality.shadowsEnabled;
    this.webgl.shadowMap.type = THREE.PCFSoftShadowMap;
    // EffectComposer performs multiple renderer calls. Reset once per game
    // frame so debug stats report cumulative scene + output-pass work.
    this.webgl.info.autoReset = false;

    container.appendChild(this.webgl.domElement);
    this.gpuInfo = logGpuInfo(this.webgl.getContext()!);
  }

  handleResize(camera: THREE.PerspectiveCamera): void {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    this.webgl.setSize(window.innerWidth, window.innerHeight);
    this.composer?.setSize(window.innerWidth, window.innerHeight);
    this.updatePostResolution();
  }

  /**
   * Post chain: scene (with depth) → aerial distance fog → tone map + bloom
   * → FXAA. Bloom stays folded into the output pass; the fog pass dissolves
   * far geometry into the horizon haze using the depth buffer.
   */
  configureOutput(
    scene: THREE.Scene,
    camera: THREE.PerspectiveCamera,
    envUniforms: SharedEnvUniforms,
  ): void {
    this.webgl.getDrawingBufferSize(this.drawingBufferSize);
    const composer = new EffectComposer(this.webgl);
    composer.setPixelRatio(Math.min(window.devicePixelRatio, this.maxPixelRatio));
    // The fog pass renders the scene itself into a private depth-textured
    // target, so the composer's ping-pong buffers stay depth-free.
    composer.addPass(
      new AerialFogPass(
        scene,
        camera,
        envUniforms,
        this.drawingBufferSize.x,
        this.drawingBufferSize.y,
      ),
    );
    const outputPass = new OutputPass();
    const uniforms = outputPass.uniforms as Record<string, THREE.IUniform>;
    uniforms.uTexelSize = { value: new THREE.Vector2(1, 1) };
    uniforms.uBloomStrength = { value: RENDERER.bloomStrength };
    uniforms.uBloomThreshold = { value: RENDERER.bloomThreshold };
    outputPass.material.fragmentShader = BLOOM_OUTPUT_FRAGMENT;
    outputPass.material.needsUpdate = true;
    composer.addPass(outputPass);
    // FXAA on the LDR output (the composer path bypasses canvas MSAA).
    const fxaaPass = new ShaderPass(FXAAShader);
    composer.addPass(fxaaPass);
    this.composer = composer;
    this.outputPass = outputPass;
    this.fxaaPass = fxaaPass;
    this.updatePostResolution();
  }

  /** Used by the adaptive-quality fallback when FPS drops. */
  setPixelRatioScale(scale: number): void {
    this.pixelRatioScale = scale;
    const ratio = Math.min(window.devicePixelRatio, this.maxPixelRatio) * scale;
    this.webgl.setPixelRatio(ratio);
    this.composer?.setPixelRatio(ratio);
    this.updatePostResolution();
  }

  getPixelRatioScale(): number {
    return this.pixelRatioScale;
  }

  getExposure(): number {
    return this.webgl.toneMappingExposure;
  }

  setExposure(value: number): void {
    this.webgl.toneMappingExposure = THREE.MathUtils.clamp(
      value,
      RENDERER.exposureMin,
      RENDERER.exposureMax,
    );
  }

  render(scene: THREE.Scene, camera: THREE.Camera): void {
    this.webgl.info.reset();
    if (this.composer) {
      this.composer.render();
    } else {
      this.webgl.render(scene, camera);
    }
  }

  private updatePostResolution(): void {
    if (!this.outputPass) return;
    this.webgl.getDrawingBufferSize(this.drawingBufferSize);
    const invW = 1 / Math.max(this.drawingBufferSize.x, 1);
    const invH = 1 / Math.max(this.drawingBufferSize.y, 1);
    const uniforms = this.outputPass.uniforms as Record<string, THREE.IUniform>;
    (uniforms.uTexelSize.value as THREE.Vector2).set(invW, invH);
    if (this.fxaaPass) {
      (this.fxaaPass.material.uniforms.resolution.value as THREE.Vector2).set(invW, invH);
    }
  }

  dispose(): void {
    this.webgl.dispose();
    this.composer?.dispose();
  }
}
