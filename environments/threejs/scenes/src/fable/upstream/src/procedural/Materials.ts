import * as THREE from 'three';
import { createBarkTexture, createRockTexture } from './Textures';
import type { SnowTrail } from '../world/SnowTrail';
import { applyManualSRGBMap, createTerrainMaterial, createTriplanarMaterial, loadTexInstance, texMean } from './SplatShader';

/**
 * Shared, procedurally textured PBR materials. Built once per world and
 * reused by every chunk so material count stays tiny.
 */
export class MaterialLibrary {
  readonly terrain: THREE.MeshStandardMaterial;
  readonly bark: THREE.MeshStandardMaterial;
  readonly barkBirch: THREE.MeshStandardMaterial;
  readonly deadWood: THREE.MeshStandardMaterial;
  readonly rock: THREE.MeshStandardMaterial;
  readonly stone: THREE.MeshStandardMaterial;
  readonly log: THREE.MeshStandardMaterial;
  readonly crate: THREE.MeshStandardMaterial;
  readonly charcoal: THREE.MeshStandardMaterial;
  readonly ancientStone: THREE.MeshStandardMaterial;
  readonly crystal: THREE.MeshStandardMaterial;
  readonly bone: THREE.MeshStandardMaterial;
  readonly mossStone: THREE.MeshStandardMaterial;

  private disposables: Array<{ dispose(): void }> = [];

  constructor(seed: number, snowTrail?: SnowTrail) {
    // v2: PBR texture splat (grass / dirt / rock / snow) + normal detail; the snow trail is folded in.
    this.terrain = createTerrainMaterial(snowTrail);

    const barkTex = loadTexInstance('pine_bark', 'diff', [1.6, 2.5]);
    const barkNor = loadTexInstance('pine_bark', 'nor', [1.6, 2.5]);
    // scale the photo bark to a dark bark albedo (~0.045 linear; the scene lighting is strong)
    const barkGain = Math.min(1.6, 0.045 / texMean('pine_bark'));
    this.bark = new THREE.MeshStandardMaterial({ map: barkTex, normalMap: barkNor, roughness: 0.92,
      color: new THREE.Color(barkGain, barkGain * 0.96, barkGain * 0.9) });
    this.bark.normalScale.set(0.8, 0.8);
    applyManualSRGBMap(this.bark, 'barkPhoto');

    const birchTex = createBarkTexture(seed + 1, new THREE.Color(0x8d8678));
    birchTex.repeat.set(1.6, 2.5);
    this.barkBirch = new THREE.MeshStandardMaterial({ map: birchTex, roughness: 0.9 });

    const deadTex = createBarkTexture(seed + 2, new THREE.Color(0x6d6357));
    this.deadWood = new THREE.MeshStandardMaterial({ map: deadTex, roughness: 0.95 });

    const rockTex = createRockTexture(seed);
    this.rock = createTriplanarMaterial('rock_surface', 2.8, { roughness: 0.94 });
    this.stone = createTriplanarMaterial('rock_surface', 1.2, { roughness: 0.92 });

    const logTex = createBarkTexture(seed + 5, new THREE.Color(0x4f4334));
    this.log = new THREE.MeshStandardMaterial({ map: logTex, roughness: 0.95 });

    const crateTex = createBarkTexture(seed + 6, new THREE.Color(0x7a6244));
    crateTex.repeat.set(2, 2);
    this.crate = new THREE.MeshStandardMaterial({ map: crateTex, roughness: 0.85 });

    this.charcoal = new THREE.MeshStandardMaterial({ color: 0x1d1a18, roughness: 1.0 });

    const ancientTex = createRockTexture(seed + 7);
    this.ancientStone = createTriplanarMaterial('rock_face_03', 2.2, { color: 0xb8b2a4, roughness: 0.9 });

    this.bone = new THREE.MeshStandardMaterial({
      color: 0xcfc4ad,
      roughness: 0.78,
    });

    const mossTex = createRockTexture(seed + 8);
    this.mossStone = createTriplanarMaterial('rock_surface', 2.4, { color: 0x9db08a, roughness: 0.96 });

    this.crystal = new THREE.MeshStandardMaterial({
      color: 0x7fd4ff,
      emissive: 0x3fa8e0,
      emissiveIntensity: 1.4,
      roughness: 0.25,
      metalness: 0.1,
      transparent: true,
      opacity: 0.92,
    });

    this.disposables.push(
      barkTex, birchTex, deadTex, rockTex, logTex, crateTex, ancientTex, mossTex,
      this.terrain, this.bark, this.barkBirch, this.deadWood,
      this.rock, this.stone, this.log,
      this.crate, this.charcoal, this.ancientStone, this.crystal,
      this.bone, this.mossStone,
    );
  }

  dispose(): void {
    for (const d of this.disposables) d.dispose();
    this.disposables.length = 0;
  }
}
