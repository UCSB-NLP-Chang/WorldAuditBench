import * as THREE from 'three';
import { NIGHT_SKY } from '../config';
import { SKY_VERTEX, SKY_FRAGMENT, STAR_VERTEX, STAR_FRAGMENT } from '../shaders/sky';

/**
 * Sky dome plus a stable procedural point-star sphere. The dome owns smooth
 * atmosphere/galaxy gradients; stars are real circular sprites so they never
 * form patched cells or rings.
 */
export class Sky {
  readonly dome: THREE.Mesh;
  readonly material: THREE.ShaderMaterial;
  readonly starField: THREE.Points;
  readonly starMaterial: THREE.ShaderMaterial;

  constructor(scene: THREE.Scene) {
    this.material = new THREE.ShaderMaterial({
      vertexShader: SKY_VERTEX,
      fragmentShader: SKY_FRAGMENT,
      uniforms: {
        uSunDir: { value: new THREE.Vector3(0, 1, 0) },
        uMoonDir: { value: new THREE.Vector3(0, -1, 0) },
        uZenithColor: { value: new THREE.Color(0x3a6ea8) },
        uHorizonColor: { value: new THREE.Color(0x9fb8c8) },
        uHazeColor: { value: new THREE.Color(0xb9c6cf) },
        uSunColor: { value: new THREE.Color(0xfff1d6) },
        uTime: { value: 0 },
        uNight: { value: 0 },
        uCloudCover: { value: 0.35 },
        uCloudDark: { value: 0 },
        uWind: { value: new THREE.Vector2(1, 0.3) },
        uStarAngle: { value: 0 },
        uGalaxyStrength: { value: NIGHT_SKY.galaxyStrength },
        uNebulaStrength: { value: NIGHT_SKY.nebulaStrength },
      },
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
    });

    const geo = new THREE.SphereGeometry(2600, 64, 32);
    this.dome = new THREE.Mesh(geo, this.material);
    this.dome.frustumCulled = false;
    this.dome.renderOrder = -10;
    scene.add(this.dome);

    const stars = this.buildStars();
    this.starMaterial = stars.material;
    this.starField = stars.points;
    scene.add(this.starField);
  }

  private buildStars(): { points: THREE.Points; material: THREE.ShaderMaterial } {
    const count = NIGHT_SKY.starCount;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    const phases = new Float32Array(count);
    let state = 0x8a5cd789;
    const random = (): number => {
      state = (state * 1664525 + 1013904223) >>> 0;
      return state / 4294967296;
    };
    const color = new THREE.Color();
    const direction = new THREE.Vector3();
    const galaxyNormal = new THREE.Vector3(0.42, 0.32, 0.85).normalize();
    const galaxyTangent = new THREE.Vector3().crossVectors(
      galaxyNormal,
      new THREE.Vector3(0, 1, 0),
    ).normalize();
    const galaxyBitangent = new THREE.Vector3().crossVectors(galaxyNormal, galaxyTangent);

    // Longitude of the galactic-centre bulge; must match the dome shader.
    const coreLongitude = 0.85;
    for (let i = 0; i < count; i++) {
      const population = random();
      if (population < 0.5) {
        // Milky Way stars in two disc populations: a tight thin disc that
        // draws the bright edge and a wider thick disc that feathers it.
        const thin = population < 0.3;
        const longitude = random() < 0.4
          ? coreLongitude + (random() + random() + random() + random() - 2) * 1.6
          : random() * Math.PI * 2;
        const spread = thin ? 0.1 : 0.3;
        const latitude = (random() + random() + random() - 1.5) * spread;
        const cosLat = Math.cos(latitude);
        direction
          .copy(galaxyTangent)
          .multiplyScalar(Math.cos(longitude) * cosLat)
          .addScaledVector(galaxyBitangent, Math.sin(longitude) * cosLat)
          .addScaledVector(galaxyNormal, Math.sin(latitude))
          .normalize();
      } else {
        // Uniform background stars across the rest of the celestial sphere.
        const y = random() * 2 - 1;
        const angle = random() * Math.PI * 2;
        const radial = Math.sqrt(Math.max(0, 1 - y * y));
        direction.set(Math.cos(angle) * radial, y, Math.sin(angle) * radial);
      }
      const radius = NIGHT_SKY.starSphereRadius;
      positions[i * 3] = direction.x * radius;
      positions[i * 3 + 1] = direction.y * radius;
      positions[i * 3 + 2] = direction.z * radius;

      // Magnitude distribution: many pin-sharp faint stars, very few bright.
      const magnitude = Math.pow(random(), 5.2);
      sizes[i] = THREE.MathUtils.lerp(
        NIGHT_SKY.starMinSize,
        NIGHT_SKY.starMaxSize,
        magnitude,
      );

      const temperature = random();
      if (temperature < 0.12) color.setRGB(1.0, 0.72, 0.5);
      else if (temperature < 0.36) color.setRGB(1.0, 0.9, 0.72);
      else if (temperature < 0.82) color.setRGB(0.86, 0.92, 1.0);
      else color.setRGB(0.58, 0.76, 1.0);
      color.multiplyScalar(0.55 + magnitude * 0.7 + random() * 0.18);
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
      phases[i] = random();
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aColor', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
    geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1));
    geometry.computeBoundingSphere();

    const material = new THREE.ShaderMaterial({
      vertexShader: STAR_VERTEX,
      fragmentShader: STAR_FRAGMENT,
      uniforms: {
        uTime: { value: 0 },
        uNight: { value: 0 },
        uCloudCover: { value: 0 },
        uStarAngle: { value: 0 },
        uStarBrightness: { value: NIGHT_SKY.starBrightness },
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      fog: false,
    });

    const points = new THREE.Points(geometry, material);
    points.frustumCulled = false;
    points.renderOrder = -9;
    return { points, material };
  }

  update(time: number, playerPos: THREE.Vector3): void {
    this.material.uniforms.uTime.value = time;
    this.starMaterial.uniforms.uTime.value = time;
    this.dome.position.copy(playerPos);
    this.starField.position.copy(playerPos);
  }
}
