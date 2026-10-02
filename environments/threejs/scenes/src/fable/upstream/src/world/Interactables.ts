import * as THREE from 'three';
import { SeededRandom, combineSeed } from '../utils/Random';
import { WORLD } from '../config';
import { createGlowTexture, createScorchTexture } from '../procedural/Textures';
import type { MaterialLibrary } from '../procedural/Materials';
import type { Terrain } from './Terrain';
import type { Biomes } from './Biomes';
import type { CylinderCollider } from '../core/CameraController';
import type { SharedEnvUniforms } from './Environment';
import { clearingForChunk } from './Clearings';
import { buildCampfire, createFireKit, type Campfire, type FireKit } from './Fire';

export interface Interactable {
  object: THREE.Object3D;
  position: THREE.Vector3;
  label: string;
  messages: string[];
  radius: number;
  /** present on lightable campfires; drives the toggle interaction + fire light */
  campfire?: Campfire;
}

type InteractableKind = 'marker' | 'crystal' | 'crate' | 'signpost';

const KINDS: InteractableKind[] = ['marker', 'crystal', 'crate', 'signpost'];

/**
 * Sparse hand-feel points of interest: ancient markers, glowing crystals,
 * crates, and signposts (roughly one per few chunks), plus lightable campfires
 * that sit in their own grassland clearings.
 */
export class Interactables {
  private glowTexture: THREE.Texture;
  private fireKit: FireKit;
  private scorchMaterial: THREE.Material;
  /** lit campfires survive chunk reloads, keyed by chunk */
  private litFires = new Set<string>();

  constructor(
    private seed: number,
    private materials: MaterialLibrary,
    env: SharedEnvUniforms,
  ) {
    this.glowTexture = createGlowTexture();
    this.fireKit = createFireKit(env);
    this.scorchMaterial = new THREE.MeshStandardMaterial({
      map: createScorchTexture(seed),
      transparent: true,
      depthWrite: false,
      roughness: 1,
      metalness: 0,
      polygonOffset: true,
      polygonOffsetFactor: -2,
    });
  }

  /** Deterministically maybe-create one interactable for a chunk. */
  maybeCreateForChunk(
    cx: number,
    cz: number,
    terrain: Terrain,
    biomes: Biomes,
  ): { interactable: Interactable; colliders: CylinderCollider[] } | null {
    // A grassland clearing always takes priority and hosts a campfire.
    const clearing = clearingForChunk(this.seed, cx, cz, terrain, biomes);
    if (clearing) {
      return this.createCampfire(cx, cz, clearing.x, clearing.z, terrain);
    }

    const rng = new SeededRandom(combineSeed(this.seed, cx, cz, 9001));
    if (!rng.chance(0.22)) return null;

    const size = WORLD.chunkSize;
    const x = cx * size + rng.range(size * 0.2, size * 0.8);
    const z = cz * size + rng.range(size * 0.2, size * 0.8);
    const h = terrain.getMeshHeightAt(x, z);
    if (h < WORLD.waterLevel + 0.6 || h > WORLD.snowHeight) return null;

    const kind = rng.pick(KINDS);
    const built = this.build(kind, rng);
    built.object.position.set(x, h, z);
    built.object.rotation.y = rng.range(0, Math.PI * 2);

    const colliders: CylinderCollider[] =
      built.collisionRadius > 0 ? [{ x, z, radius: built.collisionRadius }] : [];

    return {
      interactable: {
        object: built.object,
        position: new THREE.Vector3(x, h + 1, z),
        label: built.label,
        messages: built.messages,
        radius: 3.6,
      },
      colliders,
    };
  }

  private createCampfire(
    cx: number,
    cz: number,
    x: number,
    z: number,
    terrain: Terrain,
  ): { interactable: Interactable; colliders: CylinderCollider[] } {
    const key = `${cx},${cz}`;
    const rng = new SeededRandom(combineSeed(this.seed, cx, cz, 9007));
    const h = terrain.getMeshHeightAt(x, z);
    const built = buildCampfire(
      rng, this.materials, this.fireKit, this.scorchMaterial, h, key, this.litFires,
    );
    built.object.position.set(x, h, z);
    built.object.rotation.y = rng.range(0, Math.PI * 2);
    built.campfire.firePos.set(x, h + 1.6, z);
    return {
      interactable: {
        object: built.object,
        position: new THREE.Vector3(x, h + 1, z),
        label: 'Campfire',
        messages: [],
        radius: 6.0,
        campfire: built.campfire,
      },
      colliders: [{ x, z, radius: built.collisionRadius }],
    };
  }

  private build(kind: InteractableKind, rng: SeededRandom): {
    object: THREE.Object3D;
    label: string;
    messages: string[];
    collisionRadius: number;
  } {
    const mats = this.materials;
    const group = new THREE.Group();
    const own = (mesh: THREE.Mesh, shadows = true) => {
      mesh.userData.ownsGeometry = true;
      mesh.castShadow = shadows;
      mesh.receiveShadow = true;
      group.add(mesh);
      return mesh;
    };

    switch (kind) {
      case 'marker': {
        const height = rng.range(2.2, 3.4);
        const stone = new THREE.BoxGeometry(0.9, height, 0.55);
        // Taper the top for an obelisk feel.
        const pos = stone.getAttribute('position') as THREE.BufferAttribute;
        for (let i = 0; i < pos.count; i++) {
          if (pos.getY(i) > 0) {
            pos.setX(i, pos.getX(i) * 0.6);
            pos.setZ(i, pos.getZ(i) * 0.6);
          }
        }
        stone.computeVertexNormals();
        stone.translate(0, height / 2 - 0.15, 0);
        own(new THREE.Mesh(stone, mats.ancientStone));
        group.rotation.z = rng.range(-0.06, 0.06);
        return {
          object: group,
          label: 'Ancient Marker',
          messages: [
            'Weathered runes spiral down the stone. They predate any kingdom you know.',
            'The marker hums faintly when you touch it. Or perhaps that was the wind.',
            'Someone carved a warning here long ago. The words have worn away.',
          ],
          collisionRadius: 0.7,
        };
      }
      case 'crystal': {
        const cluster = new THREE.Group();
        const count = rng.int(3, 5);
        for (let i = 0; i < count; i++) {
          const s = rng.range(0.25, 0.7);
          const geo = new THREE.ConeGeometry(s * 0.32, s * 1.6, 5);
          geo.translate(0, s * 0.7, 0);
          const mesh = new THREE.Mesh(geo, mats.crystal);
          mesh.userData.ownsGeometry = true;
          mesh.position.set(rng.range(-0.4, 0.4), 0, rng.range(-0.4, 0.4));
          mesh.rotation.set(rng.range(-0.4, 0.4), rng.range(0, Math.PI * 2), rng.range(-0.4, 0.4));
          mesh.castShadow = true;
          cluster.add(mesh);
        }
        group.add(cluster);
        // Soft sprite glow instead of a real point light (cheaper).
        const glow = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: this.glowTexture,
            color: 0x6fc8ff,
            transparent: true,
            opacity: 0.5,
            depthWrite: false,
          }),
        );
        glow.scale.setScalar(3.2);
        glow.position.y = 0.6;
        group.add(glow);
        return {
          object: group,
          label: 'Glowing Crystal',
          messages: [
            'Cold blue light pulses inside the crystal, slow as a sleeping heartbeat.',
            'The crystal is warm despite its icy glow. Curious.',
            'For a moment you see your reflection in the facets — older, somehow.',
          ],
          collisionRadius: 0.6,
        };
      }
      case 'crate': {
        const s = rng.range(0.7, 0.95);
        const crate = new THREE.BoxGeometry(s, s, s);
        crate.translate(0, s / 2, 0);
        own(new THREE.Mesh(crate, mats.crate));
        if (rng.chance(0.6)) {
          const s2 = s * 0.7;
          const crate2 = new THREE.BoxGeometry(s2, s2, s2);
          crate2.translate(s * 0.8, s2 / 2, s * 0.2);
          own(new THREE.Mesh(crate2, mats.crate));
        }
        return {
          object: group,
          label: 'Abandoned Crate',
          messages: [
            'Empty, save for a handful of dried herbs and a rusted buckle.',
            'The crate bears a merchant\u2019s brand from a city you\u2019ve never heard of.',
            'Whoever left this meant to come back for it. They never did.',
          ],
          collisionRadius: 0.7,
        };
      }
      case 'signpost': {
        const post = new THREE.CylinderGeometry(0.06, 0.08, 2.1, 6);
        post.translate(0, 1.05, 0);
        own(new THREE.Mesh(post, mats.log));
        const plank = new THREE.BoxGeometry(1.1, 0.24, 0.05);
        plank.translate(0.2, 1.75, 0);
        const plankMesh = own(new THREE.Mesh(plank, mats.crate));
        plankMesh.rotation.y = rng.range(-0.3, 0.3);
        return {
          object: group,
          label: 'Old Signpost',
          messages: [
            'The carved arrow points toward hills that have long since changed.',
            '\u201cTwo days to the crossing\u201d \u2014 but which crossing, it does not say.',
            'The paint is gone. Only the grain of the wood remembers the words.',
          ],
          collisionRadius: 0.25,
        };
      }
    }
  }
}

/**
 * Per-frame interaction logic: find the nearest interactable in front of the
 * player, drive the HUD prompt, and emit flavor text on E.
 */
export class InteractionSystem {
  private current: Interactable | null = null;
  private messageTimer = 0;
  private toCam = new THREE.Vector3();
  private camDir = new THREE.Vector3();
  private messageIndex = new Map<Interactable, number>();

  constructor(
    private promptEl: HTMLElement,
    private messageEl: HTMLElement,
  ) {
    document.addEventListener('keydown', (e) => {
      if (e.code === 'KeyE') this.interact();
    });
  }

  update(dt: number, camera: THREE.Camera, candidates: Interactable[]): void {
    camera.getWorldDirection(this.camDir);
    let best: Interactable | null = null;
    let bestScore = Infinity;

    for (const item of candidates) {
      this.toCam.copy(item.position).sub(camera.position);
      const dist = this.toCam.length();
      if (dist > item.radius) continue;
      this.toCam.normalize();
      // Must be roughly in front of the player.
      const facing = this.toCam.dot(this.camDir);
      if (facing < 0.45) continue;
      const score = dist * (2 - facing);
      if (score < bestScore) {
        bestScore = score;
        best = item;
      }
    }

    if (best !== this.current) {
      this.current = best;
      if (best) {
        this.promptEl.textContent = this.promptFor(best);
        this.promptEl.classList.add('visible');
      } else {
        this.promptEl.classList.remove('visible');
      }
    }

    if (this.messageTimer > 0) {
      this.messageTimer -= dt;
      if (this.messageTimer <= 0) {
        this.messageEl.classList.remove('visible');
      }
    }
  }

  private promptFor(item: Interactable): string {
    if (item.campfire) {
      return item.campfire.lit ? 'Press E to douse the fire' : 'Press E to light the fire';
    }
    return `Press E to inspect — ${item.label}`;
  }

  private interact(): void {
    if (!this.current) return;
    if (this.current.campfire) {
      const lit = this.current.campfire.toggle();
      this.promptEl.textContent = this.promptFor(this.current);
      this.showMessage(
        lit
          ? 'You set the kindling alight. Flames catch and climb, crackling.'
          : 'You scatter the embers. The fire gutters out into smoke.',
      );
      return;
    }
    const idx = this.messageIndex.get(this.current) ?? 0;
    const msg = this.current.messages[idx % this.current.messages.length];
    this.messageIndex.set(this.current, idx + 1);
    this.showMessage(msg);
  }

  private showMessage(msg: string): void {
    this.messageEl.textContent = msg;
    this.messageEl.classList.add('visible');
    this.messageTimer = 4.5;
  }
}
